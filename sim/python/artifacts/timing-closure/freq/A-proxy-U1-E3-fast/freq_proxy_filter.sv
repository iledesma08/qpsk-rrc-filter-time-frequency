`timescale 1ns/1ps
// Timing proxy only (#55 iteration, never committed): freq_opt_filter without the U in {4,8}
// row check, so the pipelined lane can be synthesized at U=1. Same reset synchronizer, same
// stream interface, same engine source.
module freq_proxy_filter #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK,
  parameter integer FFT_LEN = rrc_pkg::FFT_LEN,
  parameter integer HOP = rrc_pkg::HOP,
  parameter integer DISCARD_PREFIX = rrc_pkg::DISCARD_PREFIX,
  parameter integer EMIT_START = DISCARD_PREFIX,
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX,
  parameter integer U = 1,
  parameter integer EXEC_STAGES = 1
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
  wire rst_sync_n;
  rrc_reset_sync reset_sync (
    .clk(clk), .rst_n(rst_n), .rst_sync_n(rst_sync_n)
  );
  rrc_freq_engine #(
    .U(U), .EXEC_STAGES(EXEC_STAGES), .FFT_LEN(FFT_LEN), .HOP(HOP), .DISCARD_PREFIX(DISCARD_PREFIX),
    .EMIT_START(EMIT_START), .EMIT_LEN(EMIT_LEN)
  ) engine (
    .clk(clk),
    .rst_sync_n(rst_sync_n),
    .valid_i(valid_i),
    .ready_o(ready_o),
    .sample_i(sample_i[0]),
    .valid_o(valid_o),
    .ready_i(ready_i),
    .sample_o(sample_o[0])
  );
endmodule
