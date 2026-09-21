// Temporary stream shell used to validate the RTL toolchain before F3.
module rrc_stream_placeholder #(
  parameter integer DATA_WIDTH = 16
) (
  input  logic                         clk,
  input  logic                         rst_n,
  input  logic                         valid_i,
  input  logic signed [DATA_WIDTH-1:0] sample_i,
  output logic                         valid_o,
  output logic signed [DATA_WIDTH-1:0] sample_o
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      valid_o  <= 1'b0;
      sample_o <= '0;
    end else begin
      valid_o  <= valid_i;
      sample_o <= sample_i;
    end
  end
endmodule
