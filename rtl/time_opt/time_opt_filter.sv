module time_opt_filter #(
  parameter integer DATA_WIDTH = 16
) (
  input  logic                         clk,
  input  logic                         rst_n,
  input  logic                         valid_i,
  input  logic signed [DATA_WIDTH-1:0] sample_i,
  output logic                         valid_o,
  output logic signed [DATA_WIDTH-1:0] sample_o
);
  rrc_stream_placeholder #(.DATA_WIDTH(DATA_WIDTH)) placeholder (
    .clk(clk),
    .rst_n(rst_n),
    .valid_i(valid_i),
    .sample_i(sample_i),
    .valid_o(valid_o),
    .sample_o(sample_o)
  );
endmodule
