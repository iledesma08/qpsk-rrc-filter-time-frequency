`timescale 1ns/1ps
// Test vehicle of the shared testbench (T03 mechanics), not a filter: the elastic
// transport-only rrc_stream_shell behind the frequency block parameters. It was
// the body of freq_opt until T42 replaced it with the unfolded datapath; the TB
// mechanics tests (test_rtl_stream.py, test_rtl_config.py) still need a DUT whose
// output is its input. Never synthesized, never a PPA row.
module transport_filter #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK,
  parameter integer FFT_LEN = rrc_pkg::FFT_LEN,
  parameter integer HOP = rrc_pkg::HOP,
  parameter integer DISCARD_PREFIX = rrc_pkg::DISCARD_PREFIX,
  parameter integer EMIT_START = DISCARD_PREFIX,
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX
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
  // The block parameters are accepted so the shared testbench can drive this
  // wrapper like a frequency filter; this shell has no FFT engine, so the check
  // below is structural only. The real framing predicate (including
  // DISCARD_PREFIX >= 7 for the 8-tap RRC) is rrc_freq_pkg::valid_framing, used
  // by freq_serial and freq_opt.
  generate
    if (FFT_LEN <= 0 || (FFT_LEN & (FFT_LEN - 1)) != 0 ||
        DISCARD_PREFIX < 0 || DISCARD_PREFIX >= FFT_LEN ||
        HOP <= 0 || HOP > FFT_LEN || EMIT_START != DISCARD_PREFIX ||
        EMIT_LEN != FFT_LEN - DISCARD_PREFIX || EMIT_LEN != HOP) begin : invalid_params
      initial $fatal(1, "Invalid frequency parameters");
    end
  endgenerate

  wire rst_sync_n;
  rrc_reset_sync reset_sync (
    .clk(clk), .rst_n(rst_n), .rst_sync_n(rst_sync_n)
  );

  rrc_stream_shell #(
    .DATA_WIDTH(DATA_WIDTH), .SAMPLES_PER_CLOCK(SAMPLES_PER_CLOCK)
  ) shell (
    .clk(clk),
    .rst_sync_n(rst_sync_n),
    .valid_i(valid_i),
    .ready_o(ready_o),
    .sample_i(sample_i),
    .valid_o(valid_o),
    .ready_i(ready_i),
    .sample_o(sample_o)
  );
endmodule
