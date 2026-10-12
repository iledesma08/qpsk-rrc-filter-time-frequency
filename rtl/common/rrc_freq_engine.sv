`timescale 1ns/1ps
// Frequency-domain RRC engine: forced-50% overlap-save, FFT16 -> bin-wise
// product with H[k] -> IFFT16 (docs/contracts/frequency-block-contract-14.md),
// in the production-A integer arithmetic of fxp-policy-16.md (Q2.14).
//
// U is the number of arithmetic issue lanes (ppa-matrix-18.md). Only U=1, the
// serial baseline, is implemented: one butterfly unit with one complex
// multiplier is shared by the forward FFT, the spectral product and the IFFT.
// The framing parameters are real parameters, but only the baseline tuple
// (FFT_LEN=16, HOP=8, DISCARD_PREFIX=8, EMIT_START=8, EMIT_LEN=8) is a
// contract configuration; the transform and its tables are fixed at 16 points.
//
// Block schedule, SPC=1:
//   ACCEPT  HOP samples are accepted (ready_o high), the rest of the frame is history.
//   LOAD    the 16-sample frame is copied into the work buffer; history shifts.
//   RUN     9 passes: 4 FFT stages, 1 spectral product, 4 IFFT stages. Each
//           butterfly is fetched into operand registers one cycle and executed
//           (multiply, RNE, add/sub, write back) the next; a pass ends with one
//           drain cycle so the next pass reads fully written values.
//   EMIT    EMIT_LEN outputs z[EMIT_START +: EMIT_LEN] leave through one output
//           register, one cast per component, held while ready_i is low.
//   DRAIN   the last output waits for its consumer, then ACCEPT starts again.
module rrc_freq_engine #(
  parameter integer U = 1,
  parameter integer FFT_LEN = rrc_freq_pkg::FREQ_FFT_LEN,
  parameter integer HOP = rrc_pkg::HOP,
  parameter integer DISCARD_PREFIX = rrc_pkg::DISCARD_PREFIX,
  parameter integer EMIT_START = DISCARD_PREFIX,
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX
) (
  input  logic        clk,
  input  logic        rst_sync_n,
  input  logic        valid_i,
  output logic        ready_o,
  input  logic [31:0] sample_i,   // {Q[15:0], I[15:0]}
  output logic        valid_o,
  input  logic        ready_i,
  output logic [31:0] sample_o    // {Q[15:0], I[15:0]}
);
  import rrc_freq_pkg::*;

  generate
    if (U != 1) begin : invalid_lanes
      initial $fatal(1, "rrc_freq_engine: only U=1 is implemented");
    end
    // The 8-tap filter needs at least FILTER_TAPS-1 = 7 discarded outputs.
    if (FFT_LEN != FREQ_FFT_LEN || HOP <= 0 || HOP > FFT_LEN ||
        DISCARD_PREFIX < FREQ_FILTER_TAPS - 1 || DISCARD_PREFIX >= FFT_LEN ||
        EMIT_START != DISCARD_PREFIX || EMIT_LEN != FFT_LEN - DISCARD_PREFIX ||
        EMIT_LEN != HOP) begin : invalid_params
      initial $fatal(1, "Invalid frequency parameters");
    end
  endgenerate

  localparam integer HIST = FFT_LEN - HOP;

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
  logic signed [FREQ_IN_W-1:0] frame_re [0:FFT_LEN-1];
  logic signed [FREQ_IN_W-1:0] frame_im [0:FFT_LEN-1];

  // Work buffer and operand registers carry no reset: every entry is written by
  // LOAD before it is read, and no output is valid before that.
  logic signed [FREQ_CW-1:0] wr_re [0:FFT_LEN-1];
  logic signed [FREQ_CW-1:0] wr_im [0:FFT_LEN-1];
  logic signed [FREQ_CW-1:0] a_re_q, a_im_q, b_re_q, b_im_q;
  logic signed [FREQ_TW-1:0] t_re_q, t_im_q;
  logic [3:0] ia_q, ib_q;
  logic [1:0] mode_q;

  assign ready_o = rst_sync_n && (state == S_ACCEPT);

  // ---- Fetch addressing -------------------------------------------------
  wire is_prod = (pass == 4'd4);
  wire is_ifft = (pass >= 4'd5);
  wire [3:0] ifft_pass = pass - 4'd5;
  // log2(span): FFT spans 8,4,2,1 (ls 3..0); IFFT spans 1,2,4,8 (ls 0..3).
  wire [1:0] ls = is_ifft ? ifft_pass[1:0] : (2'd3 - pass[1:0]);
  wire [3:0] mask = (4'd1 << ls) - 4'd1;
  wire [3:0] grp = {1'b0, step[2:0]} >> ls;
  wire [3:0] pos = {1'b0, step[2:0]} & mask;
  wire [3:0] a_bf = (grp << ({1'b0, ls} + 3'd1)) | pos;
  wire [3:0] b_bf = a_bf | (4'd1 << ls);
  // T index k = j * 16 / (2 * span) = pos << (3 - ls).
  wire [3:0] k_full = pos << (3'd3 - {1'b0, ls});
  wire [2:0] k_idx = k_full[2:0];

  wire [3:0] fetch_a = is_prod ? step[3:0] : a_bf;
  wire [3:0] fetch_b = b_bf;
  wire fetch_en = (state == S_RUN) && (is_prod ? (step < 5'd16) : (step < 5'd8));
  wire last_step = (step == (is_prod ? 5'd16 : 5'd8));

  wire signed [15:0] tw_r = tw_re(k_idx);
  wire signed [15:0] tw_i = tw_im(k_idx);
  wire signed [15:0] hh_r = h_store_re(step[3:0]);
  wire signed [15:0] hh_i = h_store_im(step[3:0]);
  // Inverse butterflies multiply by conj(T[k]); the product pass uses H[k].
  wire [FREQ_TW-1:0] fetch_tr = is_prod ? {hh_r[15], hh_r} : {tw_r[15], tw_r};
  wire [FREQ_TW-1:0] fetch_ti = is_prod ? {hh_i[15], hh_i} :
                                (is_ifft ? -{tw_i[15], tw_i} : {tw_i[15], tw_i});

  always_ff @(posedge clk) begin
    if (fetch_en) begin
      a_re_q <= wr_re[fetch_a];
      a_im_q <= wr_im[fetch_a];
      b_re_q <= wr_re[fetch_b];
      b_im_q <= wr_im[fetch_b];
      t_re_q <= fetch_tr;
      t_im_q <= fetch_ti;
      ia_q <= fetch_a;
      ib_q <= fetch_b;
      mode_q <= is_prod ? M_PROD : (is_ifft ? M_IFFT : M_FFT);
    end
  end

  // ---- Execute: one shared complex multiplier ---------------------------
  wire signed [FREQ_MW-1:0] ae_re = {a_re_q[FREQ_CW-1], a_re_q};
  wire signed [FREQ_MW-1:0] ae_im = {a_im_q[FREQ_CW-1], a_im_q};
  wire signed [FREQ_MW-1:0] be_re = {b_re_q[FREQ_CW-1], b_re_q};
  wire signed [FREQ_MW-1:0] be_im = {b_im_q[FREQ_CW-1], b_im_q};
  wire signed [FREQ_MW-1:0] d_re = ae_re - be_re;
  wire signed [FREQ_MW-1:0] d_im = ae_im - be_im;
  wire signed [FREQ_MW-1:0] s_re = ae_re + be_re;
  wire signed [FREQ_MW-1:0] s_im = ae_im + be_im;

  // Multiplier operand: (a-b) for the forward butterfly, b for the inverse
  // butterfly, X[k] for the spectral product.
  wire signed [FREQ_MW-1:0] m_re = (mode_q == M_FFT) ? d_re : ((mode_q == M_IFFT) ? be_re : ae_re);
  wire signed [FREQ_MW-1:0] m_im = (mode_q == M_FFT) ? d_im : ((mode_q == M_IFFT) ? be_im : ae_im);
  wire signed [FREQ_PW-1:0] p_re = m_re * t_re_q - m_im * t_im_q;
  wire signed [FREQ_PW-1:0] p_im = m_re * t_im_q + m_im * t_re_q;

  // Butterfly twiddle product narrowed by one RNE shift by F; the spectral
  // product keeps its full precision (2F fractional bits) and is not rounded.
  wire signed [FREQ_CW-1:0] v_re = rne_shift_frac(p_re);
  wire signed [FREQ_CW-1:0] v_im = rne_shift_frac(p_im);
  wire signed [FREQ_MW-1:0] ve_re = {v_re[FREQ_CW-1], v_re};
  wire signed [FREQ_MW-1:0] ve_im = {v_im[FREQ_CW-1], v_im};
  wire signed [FREQ_MW-1:0] ps_re = ae_re + ve_re;
  wire signed [FREQ_MW-1:0] ps_im = ae_im + ve_im;
  wire signed [FREQ_MW-1:0] pd_re = ae_re - ve_re;
  wire signed [FREQ_MW-1:0] pd_im = ae_im - ve_im;

  // Forward: a <- a+b, b <- RNE((a-b)T). Inverse: a <- a+v, b <- a-v, v = RNE(b conj(T)).
  // Product: a <- X*H. The stored values fit the container (see rrc_freq_pkg).
  wire [FREQ_CW-1:0] wa_re = (mode_q == M_FFT) ? s_re[FREQ_CW-1:0] :
                             ((mode_q == M_IFFT) ? ps_re[FREQ_CW-1:0] : p_re[FREQ_CW-1:0]);
  wire [FREQ_CW-1:0] wa_im = (mode_q == M_FFT) ? s_im[FREQ_CW-1:0] :
                             ((mode_q == M_IFFT) ? ps_im[FREQ_CW-1:0] : p_im[FREQ_CW-1:0]);
  wire [FREQ_CW-1:0] wb_re = (mode_q == M_FFT) ? v_re : pd_re[FREQ_CW-1:0];
  wire [FREQ_CW-1:0] wb_im = (mode_q == M_FFT) ? v_im : pd_im[FREQ_CW-1:0];

  always_ff @(posedge clk) begin
    if (state == S_LOAD) begin
      for (integer i = 0; i < FFT_LEN; i = i + 1) begin
        wr_re[i] <= {{(FREQ_CW - FREQ_IN_W){frame_re[i][FREQ_IN_W-1]}}, frame_re[i]};
        wr_im[i] <= {{(FREQ_CW - FREQ_IN_W){frame_im[i][FREQ_IN_W-1]}}, frame_im[i]};
      end
    end else if (ex_v) begin
      wr_re[ia_q] <= wa_re;
      wr_im[ia_q] <= wa_im;
      if (mode_q != M_PROD) begin
        wr_re[ib_q] <= wb_re;
        wr_im[ib_q] <= wb_im;
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
      sample_o <= 32'd0;
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
            frame_re[HIST + cnt] <= sample_i[FREQ_IN_W-1:0];
            frame_im[HIST + cnt] <= sample_i[2*FREQ_IN_W-1:FREQ_IN_W];
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
            sample_o <= {output_cast(wr_im[EMIT_START + emit_idx]),
                         output_cast(wr_re[EMIT_START + emit_idx])};
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
