`timescale 1ns/1ps
package rrc_pkg;
  parameter integer DATA_WIDTH = 16;
  parameter integer SAMPLES_PER_CLOCK = 1;
  parameter integer FFT_LEN = 16;
  parameter integer HOP = 8;
  parameter integer DISCARD_PREFIX = 8;
  parameter integer EMIT_START = DISCARD_PREFIX;
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX;

  // Time-domain numeric policy (fxp-policy-16): production Q2.14 data and
  // coefficients, full 2W-bit products, conservative 2W+3-bit accumulator.
  parameter integer RRC_TAPS = 8;
  parameter integer FRAC_BITS = DATA_WIDTH - 2;
  parameter integer W_PRODUCT = 2 * DATA_WIDTH;
  parameter integer W_ACC_TIME = W_PRODUCT + 3;

  // Q2.14 RRC coefficient codes; slice k multiplies delay k (ascending time
  // order), so the concatenation lists c[7] first. Equal to
  // fxp.quantize_coefficients(); T22 validates the frozen export. A flat
  // vector, because Icarus 11 rejects multidimensional package parameters.
  parameter logic [RRC_TAPS*DATA_WIDTH-1:0] RRC_COEFS = {
    16'sd179, -16'sd1818, 16'sd1818, 16'sd11295,
    16'sd11295, 16'sd1818, -16'sd1818, 16'sd179
  };

  function automatic logic signed [DATA_WIDTH-1:0] rrc_coef(
    input logic [$clog2(RRC_TAPS)-1:0] k
  );
    rrc_coef = $signed(RRC_COEFS[k*DATA_WIDTH +: DATA_WIDTH]);
  endfunction

  // Single output cast of the time accumulator: RNE right shift by FRAC_BITS,
  // then saturation to DATA_WIDTH bits.
  function automatic logic signed [DATA_WIDTH-1:0] time_output_cast(
    input logic signed [W_ACC_TIME-1:0] acc
  );
    logic signed [W_ACC_TIME-FRAC_BITS-1:0] floor_code;
    logic signed [W_ACC_TIME-FRAC_BITS:0] rounded;
    logic [FRAC_BITS-1:0] dropped;
    logic round_up;
    begin
      // The arithmetic shift is a floor, so the dropped bits are a nonnegative
      // remainder: round up above half, and at exactly half only to reach an even code.
      floor_code = acc[W_ACC_TIME-1:FRAC_BITS];
      dropped = acc[FRAC_BITS-1:0];
      round_up = dropped[FRAC_BITS-1] && ((|dropped[FRAC_BITS-2:0]) || floor_code[0]);
      rounded = $signed({floor_code[W_ACC_TIME-FRAC_BITS-1], floor_code}) +
                $signed({{(W_ACC_TIME-FRAC_BITS){1'b0}}, round_up});
      // In range only when every bit above the output sign bit repeats it.
      if (rounded[W_ACC_TIME-FRAC_BITS:DATA_WIDTH-1] ==
          {(W_ACC_TIME-FRAC_BITS-DATA_WIDTH+2){rounded[W_ACC_TIME-FRAC_BITS]}})
        time_output_cast = rounded[DATA_WIDTH-1:0];
      else if (rounded[W_ACC_TIME-FRAC_BITS])
        time_output_cast = {1'b1, {(DATA_WIDTH-1){1'b0}}};
      else
        time_output_cast = {1'b0, {(DATA_WIDTH-1){1'b1}}};
    end
  endfunction
endpackage
