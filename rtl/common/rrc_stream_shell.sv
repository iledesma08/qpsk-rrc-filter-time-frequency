`timescale 1ns/1ps
// Transport-only T03 shell. This is not an RRC datapath or an II=8 serial filter.
module rrc_stream_shell #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK
) (
  input  logic clk,
  input  logic rst_sync_n,
  input  logic valid_i,
  output logic ready_o,
  input  logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_i,
  output logic valid_o,
  input  logic ready_i,
  output logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_o
);
  // The wrapper distributes this reset to the shell and future F3 registers.
  assign ready_o = rst_sync_n && (!valid_o || ready_i);

  always_ff @(posedge clk or negedge rst_sync_n) begin
    if (!rst_sync_n) begin
      valid_o <= 1'b0;
      sample_o <= '0;
    end else if (ready_o) begin
      valid_o <= valid_i;
      if (valid_i) sample_o <= sample_i;
    end
  end
endmodule
