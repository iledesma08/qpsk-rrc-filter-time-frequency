`timescale 1ns/1ps
// T40 optimized time-domain RRC filter: rows T-S4P1 and T-S8P1 of one source
// (SYSTOLIC_PES = S tap PEs, PIPELINE_DEPTH = P = 1, SPC=1, II = 8/S).
// Folded transposed form (Parhi design B1): the accepted sample x[n] is
// broadcast to the PEs, partial sums move one tap per sample and the
// coefficients stay. Tap k = t*S + p runs in slot t on PE p and computes
// s[k] = c[k]*x[n] + s[k+1] (tap 7 has no s[8]); tap 0 closes
// y[n] = c[0]*x[n] + s[1] and casts it. The 8/S slots run in ascending order,
// so every tap reads the s[k+1] the previous sample left before this sample
// overwrites it, and the next sample is accepted on the last slot's edge.
// Each output adds the eight products in the order k = 7..0 instead of the
// T20 model's 0..7: no partial sum can leave the 35-bit accumulator (bound
// below), so the integer sum and the codes are the same (fxp-policy-16,
// time accumulation-order clarification).
module time_opt_filter #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK,
  // Defaults elaborate T-S8P1 for lint and source-list checks; matching runs
  // set both explicitly (rtl_parameters of the rtl_matching manifest).
  parameter integer SYSTOLIC_PES = 8,
  parameter integer PIPELINE_DEPTH = 1
) (
  input  logic clk,
  input  logic rst_n,
  input  logic valid_i,
  output logic ready_o,
  input  logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_i,
  output logic valid_o,
  input  logic ready_i,
  output logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_o
);
  localparam integer TAPS = rrc_pkg::RRC_TAPS;
  localparam integer W_PRODUCT = rrc_pkg::W_PRODUCT;
  localparam integer W_ACC = rrc_pkg::W_ACC_TIME;
  // Issue slots per accepted sample (8/S) and the width of their counter.
  localparam integer SLOTS = SYSTOLIC_PES > 0 ? TAPS / SYSTOLIC_PES : 1;
  localparam integer SLOT_W = SLOTS > 1 ? $clog2(SLOTS) : 1;

  // Largest accumulator magnitude for any input code: 2^(W-1) * sum|c[k]|.
  // Every partial sum s[k] is a sum over a subset of the taps, so the same
  // bound covers all of them. Reads the slices directly: Icarus 11 cannot call
  // package functions here.
  function automatic logic [63:0] max_abs_accumulator();
    logic [DATA_WIDTH-1:0] magnitude;
    logic [63:0] total;
    integer k;
    begin
      total = '0;
      for (k = 0; k < TAPS; k = k + 1) begin
        magnitude = rrc_pkg::RRC_COEFS[k*DATA_WIDTH +: DATA_WIDTH];
        if (magnitude[DATA_WIDTH-1]) magnitude = -magnitude;
        total = total + {{(64-DATA_WIDTH){1'b0}}, magnitude};
      end
      max_abs_accumulator = total << (DATA_WIDTH - 1);
    end
  endfunction
  localparam logic [63:0] MAX_ABS_ACC = max_abs_accumulator();

  // Only production Q2.14 at one sample per beat is implemented, and only the
  // base rows. Other S values and P=2 return by configuration on extension
  // (ppa-matrix-18); the datapath below is written for any S that divides 8.
  generate
    if (DATA_WIDTH != rrc_pkg::DATA_WIDTH || SAMPLES_PER_CLOCK != 1 || TAPS != 8 ||
        MAX_ABS_ACC >= (64'd1 << (W_ACC - 1))) begin : invalid_params
      initial $fatal(1, "time_opt_filter requires DATA_WIDTH=16 (Q2.14), SPC=1, 8 taps and a non-overflowing accumulator");
    end
    if ((SYSTOLIC_PES != 4 && SYSTOLIC_PES != 8) || PIPELINE_DEPTH != 1) begin : invalid_row
      initial $fatal(1, "time_opt_filter implements the base rows SYSTOLIC_PES=4/8 at PIPELINE_DEPTH=1; other values are extension-only");
    end
  endgenerate

  wire rst_sync_n;
  rrc_reset_sync reset_sync (
    .clk(clk), .rst_n(rst_n), .rst_sync_n(rst_sync_n)
  );

  // x_reg holds the packed {Q,I} code of x[n] for its 8/S slots.
  // partial_*[k] holds s[k]: after x[n], s[k] = sum_{j=k..7} c[j]*x[n-j+k].
  logic [2*DATA_WIDTH-1:0] x_reg;
  logic busy;
  logic [SLOT_W-1:0] slot;
  logic signed [W_ACC-1:0] partial_i [1:TAPS-1];
  logic signed [W_ACC-1:0] partial_q [1:TAPS-1];
  // Second output entry, behind sample_o; out_full says both entries are taken.
  logic [2*DATA_WIDTH-1:0] out_spare;
  logic out_full;

  logic last_slot, step, out_load, out_pop, sample_en;
  logic signed [DATA_WIDTH-1:0] x_i, x_q;
  logic [2*DATA_WIDTH-1:0] result;

  assign last_slot = slot == SLOT_W'(SLOTS - 1);
  // Slot 0 holds tap 0, which needs a free output entry.
  assign step = busy && (slot != '0 || !out_full);
  assign out_load = step && slot == '0;
  assign out_pop = valid_o && ready_i;
  // Registered terms only: no combinational path from valid_i or ready_i.
  assign ready_o = rst_sync_n && (!busy || (step && last_slot));
  assign sample_en = valid_i && ready_o;

  assign x_i = $signed(x_reg[DATA_WIDTH-1:0]);
  assign x_q = $signed(x_reg[2*DATA_WIDTH-1:DATA_WIDTH]);

  // Per tap: the coefficient through a signed signal (Icarus loses the
  // signedness of the package function result inside a product), the two
  // full-precision products of x_reg and s[k+1] (zero for tap 7). Taps with the
  // same coefficient (c[k] = c[7-k]) give identical products, which synthesis
  // may share; check that in the reports, not here.
  logic signed [DATA_WIDTH-1:0] coef [TAPS];
  logic signed [W_PRODUCT-1:0] product_i [TAPS];
  logic signed [W_PRODUCT-1:0] product_q [TAPS];
  logic signed [W_ACC-1:0] next_i [TAPS];
  logic signed [W_ACC-1:0] next_q [TAPS];
  genvar tap_g;
  generate
    for (tap_g = 0; tap_g < TAPS; tap_g = tap_g + 1) begin : g_tap
      assign coef[tap_g] = rrc_pkg::rrc_coef(3'(tap_g));
      assign product_i[tap_g] = x_i * coef[tap_g];
      assign product_q[tap_g] = x_q * coef[tap_g];
      if (tap_g == TAPS - 1) begin : g_last
        assign next_i[tap_g] = '0;
        assign next_q[tap_g] = '0;
      end else begin : g_inner
        assign next_i[tap_g] = partial_i[tap_g + 1];
        assign next_q[tap_g] = partial_q[tap_g + 1];
      end
    end
  endgenerate

  // PE p selects the operands of tap slot*S + p and adds them with an
  // explicit sign extension of the product.
  logic signed [W_ACC-1:0] pe_i [SYSTOLIC_PES];
  logic signed [W_ACC-1:0] pe_q [SYSTOLIC_PES];
  genvar pe_g;
  generate
    for (pe_g = 0; pe_g < SYSTOLIC_PES; pe_g = pe_g + 1) begin : g_pe
      logic signed [W_PRODUCT-1:0] pe_product_i, pe_product_q;
      logic signed [W_ACC-1:0] pe_next_i, pe_next_q;
      always_comb begin
        pe_product_i = product_i[pe_g];
        pe_product_q = product_q[pe_g];
        pe_next_i = next_i[pe_g];
        pe_next_q = next_q[pe_g];
        for (int t = 1; t < SLOTS; t = t + 1) begin
          if (slot == SLOT_W'(t)) begin
            pe_product_i = product_i[t*SYSTOLIC_PES + pe_g];
            pe_product_q = product_q[t*SYSTOLIC_PES + pe_g];
            pe_next_i = next_i[t*SYSTOLIC_PES + pe_g];
            pe_next_q = next_q[t*SYSTOLIC_PES + pe_g];
          end
        end
      end
      assign pe_i[pe_g] = {{(W_ACC-W_PRODUCT){pe_product_i[W_PRODUCT-1]}}, pe_product_i} + pe_next_i;
      assign pe_q[pe_g] = {{(W_ACC-W_PRODUCT){pe_product_q[W_PRODUCT-1]}}, pe_product_q} + pe_next_q;
    end
  endgenerate

  // Tap 0 of slot 0 is y[n]: the single RNE/saturating cast to Q2.14.
  assign result = {rrc_pkg::time_output_cast(pe_q[0]), rrc_pkg::time_output_cast(pe_i[0])};

  generate
    if (SLOTS > 1) begin : g_slot
      always_ff @(posedge clk or negedge rst_sync_n) begin
        if (!rst_sync_n) slot <= '0;
        else if (sample_en || (step && last_slot)) slot <= '0;
        else if (step) slot <= slot + 1'b1;
      end
    end else begin : g_one_slot
      assign slot = '0;
    end
  endgenerate

  always_ff @(posedge clk or negedge rst_sync_n) begin
    if (!rst_sync_n) begin
      x_reg <= '0;
      busy <= 1'b0;
      for (int k = 1; k < TAPS; k = k + 1) begin
        partial_i[k] <= '0;
        partial_q[k] <= '0;
      end
      out_spare <= '0;
      out_full <= 1'b0;
      valid_o <= 1'b0;
      sample_o <= '0;
    end else begin
      if (sample_en) x_reg <= sample_i[0];
      if (sample_en) busy <= 1'b1;
      else if (step && last_slot) busy <= 1'b0;
      if (step) begin
        for (int k = 1; k < TAPS; k = k + 1) begin
          if (slot == SLOT_W'(k / SYSTOLIC_PES)) begin
            partial_i[k] <= pe_i[k % SYSTOLIC_PES];
            partial_q[k] <= pe_q[k % SYSTOLIC_PES];
          end
        end
      end
      // Two-entry output buffer. A result enters only while an entry is free,
      // so a sink stall can hold both entries without losing either one and
      // continuous traffic still loads and drains one result per cycle.
      if (!valid_o) begin
        if (out_load) begin
          valid_o <= 1'b1;
          sample_o[0] <= result;
        end
      end else if (!out_full) begin
        if (out_pop && out_load) sample_o[0] <= result;
        else if (out_pop) valid_o <= 1'b0;
        else if (out_load) begin
          out_spare <= result;
          out_full <= 1'b1;
        end
      end else if (out_pop) begin
        sample_o[0] <= out_spare;
        out_full <= 1'b0;
      end
    end
  end
endmodule
