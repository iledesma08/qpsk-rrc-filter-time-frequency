`timescale 1ns/1ps
// Frozen production-A integer arithmetic of the frequency-domain filter
// (docs/contracts/fxp-policy-16.md, production-A integer freeze, W=16/Q2.14).
// Tables and widths mirror sim/python/fxp.py; they are not a second definition.
package rrc_freq_pkg;
  // Transform and filter geometry.
  parameter integer FREQ_FFT_LEN = 16;
  parameter integer FREQ_FILTER_TAPS = 8;

  // Q2.14 external words; fractional bits of data, twiddles and H[k].
  parameter integer FREQ_IN_W = 16;
  parameter integer FREQ_FRAC = 14;

  // Work-buffer container: W_acc_freq = 2*(W+4)+5 = 45 bits per component.
  // Every FFT/IFFT stage width (16..20 and 41..45) fits it. A magnitude bound
  // for any full-scale Q2.14 frame is about 2^38.4, and adversarial full-scale
  // frames in the T20 model reach 2^34.1, both far below the 2^44 limit, so the
  // container does not wrap: no overflow flag or port is needed.
  parameter integer FREQ_CW = 45;
  // Butterfly multiplier operand: a-b of two containers needs one more bit.
  parameter integer FREQ_MW = 46;
  // Twiddle / H[k] operand: 16-bit code, one more bit for the inverse conjugate.
  parameter integer FREQ_TW = 17;
  // Complex-multiply accumulator: 46x17 products are 63 bits, their sum 64.
  parameter integer FREQ_PW = 64;
  // Output cast: divide by 16 (binary-point move) then RNE by F, i.e. F+4.
  parameter integer FREQ_OUT_SHIFT = FREQ_FRAC + 4;

  // T[k] = exp(-j 2 pi k / 16), k = 0..7, Q2.14 (RNE from the exact value).
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
      rounded = floor_value + (round_up ? 64'sd1 : 64'sd0);
      rne_shift_frac = rounded[FREQ_CW-1:0];
    end
  endfunction

  // Final cast of one IFFT component: the exact /16 binary-point move and one
  // RNE shift by F+4, then saturation to the signed 16-bit Q2.14 range.
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
      rounded = floor_value + (round_up ? 46'sd1 : 46'sd0);
      if (rounded > 46'sd32767) output_cast = 16'sh7FFF;
      else if (rounded < -46'sd32768) output_cast = 16'sh8000;
      else output_cast = rounded[FREQ_IN_W-1:0];
    end
  endfunction
endpackage
