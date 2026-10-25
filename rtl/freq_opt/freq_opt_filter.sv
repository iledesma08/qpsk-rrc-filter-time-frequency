`timescale 1ns/1ps
// freq_opt: frequency-domain RRC filter, optimized rows F-U4 and F-U8 (T42).
// Wrapper over the shared rrc_freq_engine, like freq_serial_filter, with the
// lane count U as the matrix row: one source, never an edited copy per row
// (ppa-matrix-18.md, Production Practice). U=1 is freq_serial. The datapath is
// rtl/common/rrc_freq_engine.sv; see rtl/freq_opt/README.md.
module freq_opt_filter #(
  parameter integer DATA_WIDTH = rrc_pkg::DATA_WIDTH,
  parameter integer SAMPLES_PER_CLOCK = rrc_pkg::SAMPLES_PER_CLOCK,
  parameter integer FFT_LEN = rrc_pkg::FFT_LEN,
  parameter integer HOP = rrc_pkg::HOP,
  parameter integer DISCARD_PREFIX = rrc_pkg::DISCARD_PREFIX,
  parameter integer EMIT_START = DISCARD_PREFIX,
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX,
  parameter integer U = 8   // frequency issue lanes: 4 (F-U4) or 8 (F-U8)
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
  // Production Q2.14 interface only (fxp-policy-16.md): narrower widths and
  // wider beats belong to transport fixtures, not to this datapath.
  localparam bit VALID_FRAMING =
      rrc_freq_pkg::valid_framing(FFT_LEN, HOP, DISCARD_PREFIX, EMIT_START, EMIT_LEN);

  generate
    if (DATA_WIDTH != rrc_freq_pkg::FREQ_IN_W || SAMPLES_PER_CLOCK != 1) begin : invalid_interface
      initial $fatal(1, "freq_opt_filter implements only production DATA_WIDTH=16 at SPC=1");
    end
    if (U != 4 && U != 8) begin : invalid_row
      initial $fatal(1, "freq_opt_filter implements only the rows F-U4 and F-U8 (U = 4 or 8)");
    end
    if (!VALID_FRAMING) begin : invalid_params
      initial $fatal(1, "Invalid frequency parameters");
    end
  endgenerate

  wire rst_sync_n;
  rrc_reset_sync reset_sync (
    .clk(clk), .rst_n(rst_n), .rst_sync_n(rst_sync_n)
  );

  // An invalid tuple has already failed at time zero; keep it from reaching
  // the engine's array declarations.
  generate
    if (VALID_FRAMING) begin : datapath
      rrc_freq_engine #(
        .U(U), .FFT_LEN(FFT_LEN), .HOP(HOP), .DISCARD_PREFIX(DISCARD_PREFIX),
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
    end
  endgenerate
endmodule
