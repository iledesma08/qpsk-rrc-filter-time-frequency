`timescale 1ns/1ps
// T30 serial time-domain RRC filter (T-serial: S=1, P=1, SPC=1, II=8).
// One complex-by-real MAC (two signed 16x16 multipliers, I and Q) computes
// y[n] = sum_k c[k] * x[n-k] over eight cycles in ascending tap order.
// Accepting x[n] shifts the history; taps 0..7 then run on the next eight
// edges, and tap 7 writes the RNE/saturated result to the output register.
// The next sample is accepted on that same edge, so ready_o is high one cycle
// in eight under continuous traffic. The final MAC waits while the previous
// output is still pending, which holds ready_o low until the sink drains it.
module time_serial_filter #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK
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

  // Largest accumulator magnitude for any input code: 2^(W-1) * sum|c[k]|.
  // Reads the slices directly: Icarus 11 cannot call package functions here.
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

  // Only production Q2.14 at one sample per beat is implemented. The bound
  // proves that no input code can overflow the accumulator, so no runtime
  // overflow flag or extra port is needed.
  generate
    if (DATA_WIDTH != rrc_pkg::DATA_WIDTH || SAMPLES_PER_CLOCK != 1 || TAPS != 8 ||
        MAX_ABS_ACC >= (64'd1 << (W_ACC - 1))) begin : invalid_params
      initial $fatal(1, "time_serial_filter requires DATA_WIDTH=16 (Q2.14), SPC=1, 8 taps and a non-overflowing accumulator");
    end
  endgenerate

  wire rst_sync_n;
  rrc_reset_sync reset_sync (
    .clk(clk), .rst_n(rst_n), .rst_sync_n(rst_sync_n)
  );

  // history[k] holds the packed {Q,I} code of x[n-k] after accepting x[n].
  logic [TAPS-1:0][2*DATA_WIDTH-1:0] history;
  logic busy;
  logic [2:0] tap;
  logic signed [W_ACC-1:0] acc_i, acc_q;

  logic last_tap, out_load, mac_en, sample_en;
  logic [2*DATA_WIDTH-1:0] tap_sample;
  logic signed [DATA_WIDTH-1:0] x_i, x_q, coef;
  logic signed [W_PRODUCT-1:0] product_i, product_q;
  logic signed [W_ACC-1:0] base_i, base_q, addend_i, addend_q, sum_i, sum_q;

  assign last_tap = busy && &tap;  // tap 7 of 8
  assign out_load = last_tap && !valid_o;
  assign mac_en = busy && (!last_tap || out_load);
  // Registered terms only: no combinational path from valid_i or ready_i.
  assign ready_o = rst_sync_n && (!busy || out_load);
  assign sample_en = valid_i && ready_o;

  assign tap_sample = history[tap];
  assign x_i = $signed(tap_sample[DATA_WIDTH-1:0]);
  assign x_q = $signed(tap_sample[2*DATA_WIDTH-1:DATA_WIDTH]);
  assign coef = rrc_pkg::rrc_coef(tap);
  // Full-precision 2W-bit products of signed operands.
  assign product_i = x_i * coef;
  assign product_q = x_q * coef;
  // Tap 0 starts a new sum; explicit sign extension before every addition.
  assign base_i = tap == 3'd0 ? '0 : acc_i;
  assign base_q = tap == 3'd0 ? '0 : acc_q;
  assign addend_i = {{(W_ACC-W_PRODUCT){product_i[W_PRODUCT-1]}}, product_i};
  assign addend_q = {{(W_ACC-W_PRODUCT){product_q[W_PRODUCT-1]}}, product_q};
  assign sum_i = base_i + addend_i;
  assign sum_q = base_q + addend_q;

  always_ff @(posedge clk or negedge rst_sync_n) begin
    if (!rst_sync_n) begin
      history <= '0;
      busy <= 1'b0;
      tap <= '0;
      acc_i <= '0;
      acc_q <= '0;
      valid_o <= 1'b0;
      sample_o <= '0;
    end else begin
      if (sample_en) history <= {history[TAPS-2:0], sample_i[0]};
      if (mac_en) begin
        acc_i <= sum_i;
        acc_q <= sum_q;
        tap <= tap + 3'd1;
      end
      if (sample_en) busy <= 1'b1;
      else if (out_load) busy <= 1'b0;
      if (out_load) begin
        valid_o <= 1'b1;
        sample_o[0] <= {rrc_pkg::time_output_cast(sum_q), rrc_pkg::time_output_cast(sum_i)};
      end else if (ready_i) begin
        valid_o <= 1'b0;
      end
    end
  end
endmodule
