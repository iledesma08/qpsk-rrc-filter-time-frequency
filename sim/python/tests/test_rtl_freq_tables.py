"""T32 (#49) integration gate: rrc_freq_pkg.sv against the T20 model and the T22 export.

The tables and widths of the RTL package are parsed from the source and
compared with ``fxp.py`` (the accepted production-A integer freeze) and with the
coefficient table exported by T22, so a drift in either side fails here. The
no-wrap bound that the engine checks at elaboration is also tied to the model.
"""

import json
import math
from pathlib import Path
import re

import numpy as np
import pytest

import fxp


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = (ROOT / "rtl" / "common" / "rrc_freq_pkg.sv").read_text()
RRC_PACKAGE = (ROOT / "rtl" / "common" / "rrc_pkg.sv").read_text()
T22_COEFFICIENTS = ROOT / "sim" / "vectors" / "fxp_expected" / "rrc8_q2.14_coefficients.json"


def constants(source: str) -> dict:
    """Evaluate the ``parameter integer NAME = expr;`` lines of a package in order."""
    values = {}
    for name, expression in re.findall(r"parameter integer (\w+) = ([^;]+);", source):
        values[name] = int(eval(expression, {"__builtins__": {}}, dict(values)))  # noqa: S307 (package source)
    return values


def table(name: str, size: int, index_bits: int) -> list:
    """Read the ``case`` ROM of function ``name``; the last entry is the ``default``."""
    body = re.search(rf"function automatic [^;]*? {name}\(.*?endfunction", PACKAGE, re.S).group(0)
    entries = {
        int(index): -int(value) if sign else int(value)
        for index, sign, value in re.findall(rf"{index_bits}'d(\d+): {name} = (-?)16'sd(\d+);", body)
    }
    default = re.search(rf"default: {name} = (-?)16'sd(\d+);", body)
    entries[size - 1] = -int(default.group(2)) if default.group(1) else int(default.group(2))
    assert sorted(entries) == list(range(size)), name
    return [entries[index] for index in range(size)]


POLICY = fxp.PRODUCTION_POLICY
RTL = constants(PACKAGE)


def test_twiddle_table_equals_the_t20_freeze():
    real, imag = fxp.twiddle_codes(POLICY)
    assert table("tw_re", 8, 3) == [int(v) for v in real]
    assert table("tw_im", 8, 3) == [int(v) for v in imag]


def test_h_table_equals_the_t20_freeze():
    real, imag = fxp.h_spectrum_codes(POLICY)
    assert table("h_nat_re", 16, 4) == [int(v) for v in real]
    assert table("h_nat_im", 16, 4) == [int(v) for v in imag]


def test_h_table_is_the_dft_of_the_t22_coefficient_codes():
    codes = json.loads(T22_COEFFICIENTS.read_text(encoding="utf-8"))["coefficient_codes"]
    assert codes == [int(v) for v in fxp.quantize_coefficients(POLICY)]
    real, imag = fxp.h_spectrum_codes(POLICY, np.array(codes, dtype=object))
    assert table("h_nat_re", 16, 4) == [int(v) for v in real]
    assert table("h_nat_im", 16, 4) == [int(v) for v in imag]


def test_h_is_read_at_bit_reversed_addresses():
    body = re.search(r"function automatic logic \[3:0\] bitrev4.*?endfunction", PACKAGE, re.S).group(0)
    assert "{value[0], value[1], value[2], value[3]}" in body
    assert "h_nat_re(bitrev4(address))" in PACKAGE and "h_nat_im(bitrev4(address))" in PACKAGE
    assert [int(f"{k:04b}"[::-1], 2) for k in range(16)] == [int(v) for v in fxp.bit_reversed_indices()]


def test_widths_equal_the_production_policy():
    assert RTL["FREQ_IN_W"] == POLICY.width
    assert RTL["FREQ_FRAC"] == POLICY.fraction_bits
    assert RTL["FREQ_FFT_LEN"] == fxp.FFT_LENGTH
    assert RTL["FREQ_FILTER_TAPS"] == fxp.FILTER_LENGTH
    assert RTL["FREQ_CW"] == POLICY.frequency_accumulator_width
    assert RTL["FREQ_OUT_SHIFT"] == POLICY.output_shift
    assert RTL["FREQ_CW"] >= max(POLICY.fft_stage_widths + POLICY.ifft_stage_widths)
    assert RTL["FREQ_PW"] == RTL["FREQ_CW"] + RTL["FREQ_IN_W"] + 1


def test_package_constants_agree_with_the_shared_rrc_pkg():
    """rrc_freq_pkg repeats them (Yosys cannot cross-reference packages); the engine checks the same."""
    shared = constants(RRC_PACKAGE)
    assert RTL["FREQ_FFT_LEN"] == shared["FFT_LEN"]
    assert RTL["FREQ_IN_W"] == shared["DATA_WIDTH"]


def test_h_l1_bound_is_the_table_maximum():
    real, imag = fxp.h_spectrum_codes(POLICY)
    assert RTL["FREQ_H_L1_MAX"] == max(abs(int(a)) + abs(int(b)) for a, b in zip(real, imag))


def test_twiddles_fit_the_16_bit_conjugate():
    real, imag = fxp.twiddle_codes(POLICY)
    assert -min(int(v) for v in imag) <= (1 << (RTL["FREQ_IN_W"] - 1)) - 1


def adversarial_frames(length=64):
    low, high = -2.0, ((1 << 15) - 1) / (1 << 14)
    rng = np.random.default_rng(3)
    even = np.arange(length) % 2 == 0
    yield rng.choice([low, high], length) + 1j * rng.choice([low, high], length)
    yield rng.uniform(low, high, length) + 1j * rng.uniform(low, high, length)
    yield np.where(even, high, low) + 1j * np.where(even, low, high)
    yield np.full(length, high) + 1j * np.full(length, high)
    yield np.full(length, low) + 1j * np.full(length, low)


def test_no_wrap_bound_covers_full_scale_frames_in_the_model():
    """The engine checks BOUND_BITS < FREQ_CW at elaboration; the model stays far below it."""
    bound_bits = RTL["FREQ_IN_W"] + 4 + math.ceil(math.log2(RTL["FREQ_H_L1_MAX"] + 1)) + 4
    assert bound_bits < RTL["FREQ_CW"]
    largest = 0
    for samples in adversarial_frames():
        monitor = fxp.filter_frequency_fxp(samples, POLICY).monitor
        largest = max(
            largest, *(max(abs(monitor.minimum[p]), abs(monitor.maximum[p])) for p in monitor.declared_width))
    assert largest < 1 << bound_bits
    assert largest < 1 << (RTL["FREQ_CW"] - 1)
