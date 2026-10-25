`timescale 1ns/1ps
// Frequency-domain RRC engine: forced-50% overlap-save, FFT16 -> bin-wise
// product with H[k] -> IFFT16 (docs/contracts/frequency-block-contract-14.md),
// in the production-A integer arithmetic of fxp-policy-16.md (Q2.14).
//
// U is the number of arithmetic issue lanes (ppa-matrix-18.md): the number of
// butterfly units, each with its own complex multiplier, that the forward FFT,
// the spectral product and the IFFT share. U=1 is the serial baseline (F-serial);
// U=4 and U=8 are the optimized rows F-U4 and F-U8 (U=8 runs the 8 butterflies
// of a radix-2 stage at once). One source: U only changes how many butterflies a
// pass fetches per cycle (8/U groups per FFT/IFFT stage, 16/U for the product),
// never the order of the passes, the arithmetic of a butterfly or any rounding,
// so every U is bit-exact with U=1. The butterflies of a pass touch disjoint
// pairs of the work buffer, so the lanes never write the same entry.
// The framing parameters are real parameters, but only the baseline tuple
// (FFT_LEN=16, HOP=8, DISCARD_PREFIX=8, EMIT_START=8, EMIT_LEN=8) is a
// contract configuration; the transform and its tables are fixed at 16 points.
//
// Block schedule, SPC=1:
//   ACCEPT  HOP samples are accepted (ready_o high), the rest of the frame is history.
//   LOAD    the 16-sample frame is copied into the work buffer; history shifts.
//   RUN     9 passes: 4 FFT stages, 1 spectral product, 4 IFFT stages. U
//           butterflies (U bins in the product) are fetched into operand
//           registers in one cycle and executed (multiply, RNE, add/sub, write
//           back) the next; a pass ends with one drain cycle so the next pass
//           reads fully written values. A pass takes 8/U + 1 cycles (16/U + 1
//           for the product): RUN is 89, 29 and 19 cycles for U = 1, 4, 8.
//   EMIT    EMIT_LEN outputs z[EMIT_START +: EMIT_LEN] leave through one output
//           register, one cast per component, held while ready_i is low.
//   DRAIN   the last output waits for its consumer, then ACCEPT starts again.
//
// Reset (rtl-streaming-17, "Reset behavior"): the control state, the frame
// history (zero), valid_o and sample_o are reset. The work buffer and the
// operand registers are NOT reset. This is an explicit interpretation of "all
// internal history, accumulators and valid pipelines are cleared": LOAD writes
// every work-buffer entry before anything reads it, no output is valid before
// that, and reset flops are larger in sky130. A reset in RUN, EMIT or DRAIN is
// covered by a directed test (sim/python/tests/test_rtl_freq_serial.py).
// The control signals state, cnt, pass, step and emit_idx keep their names for
// every U: the testbench VCD scope refers to them.
module rrc_freq_engine #(
  parameter integer U = 1,
  parameter integer FFT_LEN = rrc_pkg::FFT_LEN,
  parameter integer HOP = rrc_pkg::HOP,
  parameter integer DISCARD_PREFIX = rrc_pkg::DISCARD_PREFIX,
  parameter integer EMIT_START = DISCARD_PREFIX,
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX
) (
  input  logic        clk,
  input  logic        rst_sync_n,
  input  logic        valid_i,
  output logic        ready_o,
  input  logic [2*rrc_freq_pkg::FREQ_IN_W-1:0] sample_i,   // {Q, I}
  output logic        valid_o,
  input  logic        ready_i,
  output logic [2*rrc_freq_pkg::FREQ_IN_W-1:0] sample_o    // {Q, I}
);
  localparam integer IW = rrc_freq_pkg::FREQ_IN_W;   // Q2.14 word
  localparam integer CW = rrc_freq_pkg::FREQ_CW;     // work-buffer container
  localparam integer PW = rrc_freq_pkg::FREQ_PW;     // complex-multiply sum
  localparam integer HIST = FFT_LEN - HOP;
  localparam integer NBF = FFT_LEN / 2;   // butterflies in an FFT/IFFT stage
  localparam integer GB = NBF / U;        // fetch groups of a butterfly pass
  localparam integer GP = FFT_LEN / U;    // fetch groups of the product pass

  // No-wrap argument for the container, checked at elaboration instead of with
  // an overflow port (ports are fixed by rtl-streaming-17). For any full-scale
  // Q2.14 frame, |x| < 2^IW (components are at most 2^(IW-1), so |x| is
  // below sqrt(2)*2^(IW-1)); the forward FFT gains at most 16 (2^4) in
  // magnitude; |H[k]| <= |re|+|im| <= FREQ_H_L1_MAX < 2^clog2(FREQ_H_L1_MAX+1);
  // the product keeps full precision; the unscaled IFFT gains 16 again.
  // Adversarial full-scale frames in the T20 model reach about 2^34.1.
  // Unlike the T20 model, which flags any value above its stage widths (W..W+4,
  // 2(W+4)+1.., declared for the accepted stimulus), the RTL computes every
  // stage in the CW-bit container and never wraps.
  localparam integer BOUND_BITS = IW + 4 + $clog2(rrc_freq_pkg::FREQ_H_L1_MAX + 1) + 4;

  generate
    if (U != 1 && U != 4 && U != 8) begin : invalid_lanes
      initial $fatal(1, "rrc_freq_engine: only U in {1, 4, 8} is implemented");
    end
    // rrc_freq_pkg repeats the transform length and the word width of its tables
    // (see there); they must not drift from the shared rrc_pkg.
    if (rrc_pkg::FFT_LEN != rrc_freq_pkg::FREQ_FFT_LEN || rrc_pkg::DATA_WIDTH != rrc_freq_pkg::FREQ_IN_W) begin : package_drift
      initial $fatal(1, "rrc_freq_pkg disagrees with rrc_pkg on FFT_LEN or DATA_WIDTH");
    end
    if (!rrc_freq_pkg::valid_framing(FFT_LEN, HOP, DISCARD_PREFIX, EMIT_START, EMIT_LEN)) begin : invalid_params
      initial $fatal(1, "Invalid frequency parameters");
    end
    if (BOUND_BITS >= CW) begin : container_can_wrap
      initial $fatal(1, "rrc_freq_engine: the work-buffer container can wrap");
    end
  endgenerate

  localparam logic [2:0] S_ACCEPT = 3'd0;
  localparam logic [2:0] S_LOAD   = 3'd1;
  localparam logic [2:0] S_RUN    = 3'd2;
  localparam logic [2:0] S_EMIT   = 3'd3;
  localparam logic [2:0] S_DRAIN  = 3'd4;

  localparam logic [1:0] M_FFT  = 2'd0;
  localparam logic [1:0] M_PROD = 2'd1;
  localparam logic [1:0] M_IFFT = 2'd2;

  // Control and stream state; these use the synchronized reset.
  logic [2:0] state;
  logic [3:0] cnt;        // samples accepted in the current block
  logic [3:0] pass;       // 0-3 FFT stages, 4 product, 5-8 IFFT stages
  logic [4:0] step;       // fetch index inside a pass; step == N is the drain cycle
  logic [3:0] emit_idx;
  logic       ex_v;       // the operand registers hold a butterfly to execute

  // Input frame: [0, HIST) is history (zero after reset), [HIST, FFT_LEN) is new.
  logic signed [IW-1:0] frame_re [0:FFT_LEN-1];
  logic signed [IW-1:0] frame_im [0:FFT_LEN-1];

  // Work buffer and operand registers carry no reset (see the header).
  logic signed [CW-1:0] wr_re [0:FFT_LEN-1];
  logic signed [CW-1:0] wr_im [0:FFT_LEN-1];
  logic signed [CW-1:0] a_re_q [0:U-1];
  logic signed [CW-1:0] a_im_q [0:U-1];
  logic signed [CW-1:0] b_re_q [0:U-1];
  logic signed [CW-1:0] b_im_q [0:U-1];
  logic signed [IW-1:0] t_re_q [0:U-1];
  logic signed [IW-1:0] t_im_q [0:U-1];
  logic [3:0] ia_q [0:U-1];
  logic [3:0] ib_q [0:U-1];
  logic [1:0] mode_q;

  assign ready_o = rst_sync_n && (state == S_ACCEPT);

  // ---- Fetch addressing (pass-wide, shared by the lanes) ---------------
  wire is_prod = (pass == 4'd4);
  wire is_ifft = (pass >= 4'd5);
  wire [3:0] ifft_pass = pass - 4'd5;
  // log2(span): FFT spans 8,4,2,1 (ls 3..0); IFFT spans 1,2,4,8 (ls 0..3).
  wire [1:0] ls = is_ifft ? ifft_pass[1:0] : (2'd3 - pass[1:0]);
  wire [3:0] mask = (4'd1 << ls) - 4'd1;
  localparam logic [4:0] LAST_B = 5'(GB);
  localparam logic [4:0] LAST_P = 5'(GP);
  wire fetch_en = (state == S_RUN) && (is_prod ? (step < LAST_P) : (step < LAST_B));
  wire last_step = (step == (is_prod ? LAST_P : LAST_B));
  wire [1:0] next_mode = is_prod ? M_PROD : (is_ifft ? M_IFFT : M_FFT);

  always_ff @(posedge clk) begin
    if (fetch_en) mode_q <= next_mode;
  end

  // ---- Lanes: fetch into operand registers, then one multiplier each ----
  // Lane l works on butterfly (bin in the product) bi = step * U + l.
  wire signed [CW-1:0] wa_re [0:U-1];
  wire signed [CW-1:0] wa_im [0:U-1];
  wire signed [CW-1:0] wb_re [0:U-1];
  wire signed [CW-1:0] wb_im [0:U-1];

  genvar l;
  generate
    for (l = 0; l < U; l = l + 1) begin : lane
      wire [3:0] bi = 4'(step * U + l);
      wire [3:0] grp = bi >> ls;
      wire [3:0] pos = bi & mask;
      wire [3:0] a_bf = (grp << ({1'b0, ls} + 3'd1)) | pos;
      wire [3:0] b_bf = a_bf | (4'd1 << ls);
      // T index k = j * 16 / (2 * span) = pos << (3 - ls).
      wire [3:0] k_full = pos << (3'd3 - {1'b0, ls});
      wire [2:0] k_idx = k_full[2:0];

      wire [3:0] fetch_a = is_prod ? bi : a_bf;
      wire [3:0] fetch_b = b_bf;

      wire signed [IW-1:0] tw_r = rrc_freq_pkg::tw_re(k_idx);
      wire signed [IW-1:0] tw_i = rrc_freq_pkg::tw_im(k_idx);
      wire signed [IW-1:0] hh_r = rrc_freq_pkg::h_store_re(bi);
      wire signed [IW-1:0] hh_i = rrc_freq_pkg::h_store_im(bi);
      // Inverse butterflies multiply by conj(T[k]); the product pass uses H[k].
      // |tw_i| <= 2^14, so -tw_i fits the 16-bit word.
      wire [IW-1:0] fetch_tr = is_prod ? hh_r : tw_r;
      wire [IW-1:0] fetch_ti = is_prod ? hh_i : (is_ifft ? -tw_i : tw_i);

      always_ff @(posedge clk) begin
        if (fetch_en) begin
          a_re_q[l] <= wr_re[fetch_a];
          a_im_q[l] <= wr_im[fetch_a];
          b_re_q[l] <= wr_re[fetch_b];
          b_im_q[l] <= wr_im[fetch_b];
          t_re_q[l] <= fetch_tr;
          t_im_q[l] <= fetch_ti;
          ia_q[l] <= fetch_a;
          ib_q[l] <= fetch_b;
        end
      end

      // Execute: one complex multiplier per lane.
      wire signed [CW-1:0] d_re = a_re_q[l] - b_re_q[l];
      wire signed [CW-1:0] d_im = a_im_q[l] - b_im_q[l];
      wire signed [CW-1:0] s_re = a_re_q[l] + b_re_q[l];
      wire signed [CW-1:0] s_im = a_im_q[l] + b_im_q[l];

      // Multiplier operand: (a-b) for the forward butterfly, b for the inverse
      // butterfly, X[k] for the spectral product.
      wire signed [CW-1:0] m_re = (mode_q == M_FFT) ? d_re : ((mode_q == M_IFFT) ? b_re_q[l] : a_re_q[l]);
      wire signed [CW-1:0] m_im = (mode_q == M_FFT) ? d_im : ((mode_q == M_IFFT) ? b_im_q[l] : a_im_q[l]);
      wire signed [PW-1:0] p_re = m_re * t_re_q[l] - m_im * t_im_q[l];
      wire signed [PW-1:0] p_im = m_re * t_im_q[l] + m_im * t_re_q[l];

      // Butterfly twiddle product narrowed by one RNE shift by F; the spectral
      // product keeps its full precision (2F fractional bits) and is not rounded.
      wire signed [CW-1:0] v_re = rrc_freq_pkg::rne_shift_frac(p_re);
      wire signed [CW-1:0] v_im = rrc_freq_pkg::rne_shift_frac(p_im);
      wire signed [CW-1:0] ps_re = a_re_q[l] + v_re;
      wire signed [CW-1:0] ps_im = a_im_q[l] + v_im;
      wire signed [CW-1:0] pd_re = a_re_q[l] - v_re;
      wire signed [CW-1:0] pd_im = a_im_q[l] - v_im;

      // Forward: a <- a+b, b <- RNE((a-b)T). Inverse: a <- a+v, b <- a-v, v = RNE(b conj(T)).
      // Product: a <- X*H. Every stored value fits the container (BOUND_BITS above).
      assign wa_re[l] = (mode_q == M_FFT) ? s_re : ((mode_q == M_IFFT) ? ps_re : p_re[CW-1:0]);
      assign wa_im[l] = (mode_q == M_FFT) ? s_im : ((mode_q == M_IFFT) ? ps_im : p_im[CW-1:0]);
      assign wb_re[l] = (mode_q == M_FFT) ? v_re : pd_re;
      assign wb_im[l] = (mode_q == M_FFT) ? v_im : pd_im;
    end
  endgenerate

  always_ff @(posedge clk) begin
    if (state == S_LOAD) begin
      for (integer i = 0; i < FFT_LEN; i = i + 1) begin
        wr_re[i] <= {{(CW - IW){frame_re[i][IW-1]}}, frame_re[i]};
        wr_im[i] <= {{(CW - IW){frame_im[i][IW-1]}}, frame_im[i]};
      end
    end else if (ex_v) begin
      // The lanes of a pass write disjoint entries.
      for (integer i = 0; i < U; i = i + 1) begin
        wr_re[ia_q[i]] <= wa_re[i];
        wr_im[ia_q[i]] <= wa_im[i];
        if (mode_q != M_PROD) begin
          wr_re[ib_q[i]] <= wb_re[i];
          wr_im[ib_q[i]] <= wb_im[i];
        end
      end
    end
  end

  // ---- Control, frame history and the output register -------------------
  always_ff @(posedge clk or negedge rst_sync_n) begin
    if (!rst_sync_n) begin
      state <= S_ACCEPT;
      cnt <= 4'd0;
      pass <= 4'd0;
      step <= 5'd0;
      emit_idx <= 4'd0;
      ex_v <= 1'b0;
      valid_o <= 1'b0;
      sample_o <= '0;
      for (integer i = 0; i < FFT_LEN; i = i + 1) begin
        frame_re[i] <= '0;
        frame_im[i] <= '0;
      end
    end else begin
      ex_v <= fetch_en;
      case (state)
        S_ACCEPT: begin
          // ready_o is high in this state, so valid_i is an accepted transfer.
          if (valid_i) begin
            frame_re[HIST + cnt] <= sample_i[IW-1:0];
            frame_im[HIST + cnt] <= sample_i[2*IW-1:IW];
            if (cnt == HOP - 1) begin
              cnt <= 4'd0;
              state <= S_LOAD;
            end else begin
              cnt <= cnt + 4'd1;
            end
          end
        end
        S_LOAD: begin
          // The last HIST samples of this frame are the next block's history.
          for (integer i = 0; i < HIST; i = i + 1) begin
            frame_re[i] <= frame_re[i + HOP];
            frame_im[i] <= frame_im[i + HOP];
          end
          pass <= 4'd0;
          step <= 5'd0;
          state <= S_RUN;
        end
        S_RUN: begin
          if (last_step) begin
            step <= 5'd0;
            if (pass == 4'd8) begin
              emit_idx <= 4'd0;
              state <= S_EMIT;
            end else begin
              pass <= pass + 4'd1;
            end
          end else begin
            step <= step + 5'd1;
          end
        end
        S_EMIT: begin
          // Load the output register when it is empty or being consumed now.
          if (!valid_o || ready_i) begin
            valid_o <= 1'b1;
            sample_o <= {rrc_freq_pkg::output_cast(wr_im[EMIT_START + emit_idx]),
                         rrc_freq_pkg::output_cast(wr_re[EMIT_START + emit_idx])};
            if (emit_idx == EMIT_LEN - 1) state <= S_DRAIN;
            else emit_idx <= emit_idx + 4'd1;
          end
        end
        S_DRAIN: begin
          if (ready_i) begin
            valid_o <= 1'b0;
            state <= S_ACCEPT;
          end
        end
        default: state <= S_ACCEPT;
      endcase
    end
  end
endmodule
