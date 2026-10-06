`timescale 1ns/1ps
module time_opt_filter #(
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
  rrc_stream_shell #(
    .DATA_WIDTH(DATA_WIDTH), .SAMPLES_PER_CLOCK(SAMPLES_PER_CLOCK)
  ) shell (
    .clk(clk),
    .rst_n(rst_n),
    .valid_i(valid_i),
    .ready_o(ready_o),
    .sample_i(sample_i),
    .valid_o(valid_o),
    .ready_i(ready_i),
    .sample_o(sample_o)
  );
endmodule
