`timescale 1ns/1ps
// One asynchronous-assert, two-flop synchronous-release reset per variant.
module rrc_reset_sync (
  input  logic clk,
  input  logic rst_n,
  output wire rst_sync_n
);
  // Tool-dependent synchronizer intent; not a physical preservation guarantee.
  (* async_reg = "true" *) logic [1:0] reset_pipe;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) reset_pipe <= '0;
    else reset_pipe <= {reset_pipe[0], 1'b1};
  end

  assign rst_sync_n = reset_pipe[1];
endmodule
