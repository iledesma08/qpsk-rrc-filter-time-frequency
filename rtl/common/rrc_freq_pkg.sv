`timescale 1ns/1ps
// Frozen production-A integer arithmetic of the frequency-domain filter
// (docs/contracts/fxp-policy-16.md, production-A integer freeze, W=16/Q2.14).
//
// The tables and widths mirror sim/python/fxp.py. They are not a second
// definition: sim/python/tests/test_rtl_freq_tables.py parses this file and
// compares the tables with fxp.twiddle_codes(), fxp.h_spectrum_codes() and the
// T22 coefficient export, and checks FREQ_H_L1_MAX against the H[k] table.
package rrc_freq_pkg;
  // Facts of the tables below: 16-point transform, Q2.14 words of 16 bits.
  // They repeat rrc_pkg::FFT_LEN and rrc_pkg::DATA_WIDTH on purpose: the Yosys of
  // OpenLane 2.3.10 (0.46) cannot parse a package parameter that references
  // another package, so rrc_freq_engine.sv cross-checks them against rrc_pkg at
  // elaboration (a mismatch is a fatal error) instead of importing them here.
  parameter integer FREQ_FFT_LEN = 16;
  parameter integer FREQ_IN_W = 16;

  // Declared deviation from "no duplicated constants" (CONTRIBUTING section 7):
  // rrc_pkg does not carry the tap count or the fraction bits yet. T30 (#79) adds
  // RRC_TAPS and FRAC_BITS there; switch these two to them when it merges.
  parameter integer FREQ_FILTER_TAPS = 8;
  parameter integer FREQ_FRAC = 14;

  // Work-buffer container: W_acc_freq = 2*(W+4)+5 = 45 bits per component. Every
  // FFT/IFFT stage width of the freeze (W..W+4 and 2(W+4)+1..2(W+4)+5) fits it.
  parameter integer FREQ_CW = 2 * (FREQ_IN_W + 4) + 5;
  // Complex multiplier: container x word operands (45 x 16), 61-bit products, 62-bit sum.
  parameter integer FREQ_PW = FREQ_CW + FREQ_IN_W + 1;
  // Output cast: divide by 16 (binary-point move) then RNE by F, i.e. F+4.
  parameter integer FREQ_OUT_SHIFT = FREQ_FRAC + 4;

  // Largest |re|+|im| over the H[k] table (checked against the table by pytest).
  // It bounds |H[k]| and therefore the spectral product in the no-wrap argument
  // made at elaboration in rrc_freq_engine.sv.
  parameter integer FREQ_H_L1_MAX = 30472;

  // T[k] = exp(-j 2 pi k / 16), k = 0..7, Q2.14 (RNE from the exact value).
  // The extremes are +-16384, so the inverse conjugate -tw_im fits 16 bits.
  function automatic logic signed [15:0] tw_re(input logic [2:0] k);
    case (k)
      3'd0: tw_re = 16'sd16384;
      3'd1: tw_re = 16'sd15137;
      3'd2: tw_re = 16'sd11585;
      3'd3: tw_re = 16'sd6270;
      3'd4: tw_re = 16'sd0;
      3'd5: tw_re = -16'sd6270;
      3'd6: tw_re = -16'sd11585;
      default: tw_re = -16'sd15137;
    endcase
  endfunction

  function automatic logic signed [15:0] tw_im(input logic [2:0] k);
    case (k)
      3'd0: tw_im = 16'sd0;
      3'd1: tw_im = -16'sd6270;
      3'd2: tw_im = -16'sd11585;
      3'd3: tw_im = -16'sd15137;
      3'd4: tw_im = -16'sd16384;
      3'd5: tw_im = -16'sd15137;
      3'd6: tw_im = -16'sd11585;
      default: tw_im = -16'sd6270;
    endcase
  endfunction

  // H[k] = DFT16 of the quantized taps zero-padded to 16, one RNE; natural bin k.
  function automatic logic signed [15:0] h_nat_re(input logic [3:0] k);
    case (k)
      4'd0: h_nat_re = 16'sd22948;
      4'd1: h_nat_re = 16'sd4532;
      4'd2: h_nat_re = -16'sd21547;
      4'd3: h_nat_re = -16'sd11912;
      4'd4: h_nat_re = 16'sd11474;
      4'd5: h_nat_re = 16'sd7128;
      4'd6: h_nat_re = -16'sd685;
      4'd7: h_nat_re = 16'sd968;
      4'd8: h_nat_re = 16'sd0;
      4'd9: h_nat_re = 16'sd968;
      4'd10: h_nat_re = -16'sd685;
      4'd11: h_nat_re = 16'sd7128;
      4'd12: h_nat_re = 16'sd11474;
      4'd13: h_nat_re = -16'sd11912;
      4'd14: h_nat_re = -16'sd21547;
      default: h_nat_re = 16'sd4532;
    endcase
  endfunction

  function automatic logic signed [15:0] h_nat_im(input logic [3:0] k);
    case (k)
      4'd0: h_nat_im = 16'sd0;
      4'd1: h_nat_im = -16'sd22783;
      4'd2: h_nat_im = -16'sd8925;
      4'd3: h_nat_im = 16'sd17827;
      4'd4: h_nat_im = 16'sd11474;
      4'd5: h_nat_im = -16'sd4763;
      4'd6: h_nat_im = -16'sd1653;
      4'd7: h_nat_im = -16'sd193;
      4'd8: h_nat_im = 16'sd0;
      4'd9: h_nat_im = 16'sd193;
      4'd10: h_nat_im = 16'sd1653;
      4'd11: h_nat_im = 16'sd4763;
      4'd12: h_nat_im = -16'sd11474;
      4'd13: h_nat_im = -16'sd17827;
      4'd14: h_nat_im = 16'sd8925;
      default: h_nat_im = 16'sd22783;
    endcase
  endfunction

  // The forward DIF transform delivers X[k] in bit-reversed order, so H[k] is
  // stored at bit-reversed addresses. This is an address mapping only; bin k
  // keeps its standard DFT meaning.
  function automatic logic [3:0] bitrev4(input logic [3:0] value);
    bitrev4 = {value[0], value[1], value[2], value[3]};
  endfunction

  function automatic logic signed [15:0] h_store_re(input logic [3:0] address);
    h_store_re = h_nat_re(bitrev4(address));
  endfunction

  function automatic logic signed [15:0] h_store_im(input logic [3:0] address);
    h_store_im = h_nat_im(bitrev4(address));
  endfunction

  // One definition of a legal framing tuple, used by the engine and by the
  // wrapper. The transform and its tables are 16 points, an 8-tap filter needs
  // at least FILTER_TAPS-1 discarded outputs, and the emitted window is the
  // hop. Only (16, 8, 8, 8, 8) is a contract configuration.
  function automatic bit valid_framing(
    input integer fft_len,
    input integer hop,
    input integer discard_prefix,
    input integer emit_start,
    input integer emit_len
  );
    valid_framing = (fft_len == FREQ_FFT_LEN) && (hop > 0) && (hop <= fft_len) &&
                    (discard_prefix >= FREQ_FILTER_TAPS - 1) && (discard_prefix < fft_len) &&
                    (emit_start == discard_prefix) && (emit_len == fft_len - discard_prefix) &&
                    (emit_len == hop);
  endfunction

  // RNE right shift by F of a complex-multiply sum, narrowed into the
  // container. Ties go to the even code: round up iff the dropped bits exceed
  // one half, or equal one half and the floor is odd. Odd-symmetric.
  function automatic logic signed [FREQ_CW-1:0] rne_shift_frac(
    input logic signed [FREQ_PW-1:0] value
  );
    logic signed [FREQ_PW-1:0] floor_value;
    logic signed [FREQ_PW-1:0] rounded;
    logic [FREQ_FRAC-1:0] dropped;
    logic round_up;
    begin
      floor_value = value >>> FREQ_FRAC;
      dropped = value[FREQ_FRAC-1:0];
      round_up = dropped[FREQ_FRAC-1] && ((dropped[FREQ_FRAC-2:0] != 0) || floor_value[0]);
      rounded = floor_value + $signed({{(FREQ_PW-1){1'b0}}, round_up});
      rne_shift_frac = rounded[FREQ_CW-1:0];
    end
  endfunction

  // Final cast of one IFFT component: the exact /16 binary-point move and one
  // RNE shift by F+4, then saturation to the signed 16-bit Q2.14 range.
  localparam logic signed [FREQ_CW:0] OUT_MAX = (1 <<< (FREQ_IN_W - 1)) - 1;
  localparam logic signed [FREQ_CW:0] OUT_MIN = -(1 <<< (FREQ_IN_W - 1));

  function automatic logic signed [FREQ_IN_W-1:0] output_cast(
    input logic signed [FREQ_CW-1:0] value
  );
    logic signed [FREQ_CW:0] floor_value;
    logic signed [FREQ_CW:0] rounded;
    logic [FREQ_OUT_SHIFT-1:0] dropped;
    logic round_up;
    begin
      floor_value = $signed({value[FREQ_CW-1], value}) >>> FREQ_OUT_SHIFT;
      dropped = value[FREQ_OUT_SHIFT-1:0];
      round_up = dropped[FREQ_OUT_SHIFT-1] && ((dropped[FREQ_OUT_SHIFT-2:0] != 0) || floor_value[0]);
      rounded = floor_value + $signed({{FREQ_CW{1'b0}}, round_up});
      if (rounded > OUT_MAX) output_cast = OUT_MAX[FREQ_IN_W-1:0];
      else if (rounded < OUT_MIN) output_cast = OUT_MIN[FREQ_IN_W-1:0];
      else output_cast = rounded[FREQ_IN_W-1:0];
    end
  endfunction
endpackage
