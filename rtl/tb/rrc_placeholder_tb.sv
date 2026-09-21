`ifndef DUT_MODULE
  `error "DUT_MODULE must name the RTL placeholder under test"
`endif

module rrc_placeholder_tb;
  localparam integer DATA_WIDTH = 16;

  logic clk = 1'b0;
  logic rst_n = 1'b0;
  logic valid_i = 1'b0;
  logic signed [DATA_WIDTH-1:0] sample_i = '0;
  logic valid_o;
  logic signed [DATA_WIDTH-1:0] sample_o;
  integer vectors_fd;
  reg [8*256-1:0] manifest_line;

  always #5 clk = ~clk;

  `DUT_MODULE #(.DATA_WIDTH(DATA_WIDTH)) dut (
    .clk(clk),
    .rst_n(rst_n),
    .valid_i(valid_i),
    .sample_i(sample_i),
    .valid_o(valid_o),
    .sample_o(sample_o)
  );

  initial begin
    vectors_fd = $fopen("sim/vectors/README.md", "r");
    if (vectors_fd == 0) begin
      $fatal(1, "Cannot open sim/vectors/README.md");
    end
    if ($fgets(manifest_line, vectors_fd) == 0) begin
      $fatal(1, "Cannot read sim/vectors/README.md");
    end
    $fclose(vectors_fd);

    repeat (2) @(posedge clk);
    #1;
    if (valid_o !== 1'b0) begin
      $fatal(1, "Output valid must be low during reset");
    end

    rst_n = 1'b1;
    @(negedge clk);
    valid_i = 1'b1;
    sample_i = 16'sh1234;
    @(posedge clk);
    #1;
    if (valid_o !== 1'b0 || sample_o !== '0) begin
      $fatal(1, "Placeholder must remain idle until the RTL contract is defined");
    end

    @(negedge clk);
    valid_i = 1'b0;
    sample_i = '0;
    @(posedge clk);
    #1;
    if (valid_o !== 1'b0) begin
      $fatal(1, "Output valid must clear after the transaction");
    end

    $display("PASS: placeholder stream smoke test");
    $finish;
  end
endmodule
