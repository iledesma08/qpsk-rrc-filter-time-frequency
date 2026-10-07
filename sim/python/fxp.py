"""Integer fixed-point models of the time and frequency RRC filters (T20, #44).

Normative policy: ``docs/contracts/fxp-policy-16.md`` (Numeric Policy and the
production-A integer freeze amendment). Every value is an exact Python integer
held in NumPy ``object`` arrays, so no intermediate wraps silently. Each
declared width is checked explicitly and an out-of-range value counts as
internal overflow, which fails the candidate.

The narrowing primitives (quantization, RNE rounding and saturation) use
``fxpmath`` with ``rounding='around'`` (RNE) and ``overflow='saturate'``.
fxpmath converts its operand through float64, which is exact only below 2^53,
while the inverse-FFT twiddle products reach about 2^53 at W=18. Integer RNE
narrowing therefore reduces the operand by an even multiple of the step first
(``round_shift``), so fxpmath rounds exactly at every datapath width. Additions
and products stay exact integer operations, as in the RTL.

The frequency model is the integer FFT16 schedule itself: radix-2 DIF forward
transform, bin-wise product with the stored ``H[k]`` table, radix-2 DIT inverse
transform and one final cast. It is not ``numpy.fft`` followed by a cast.
"""

import argparse
import hashlib
import json
import math
import platform
from dataclasses import dataclass, field
from pathlib import Path

import fxpmath
import numpy as np
from fxpmath import Fxp

from rrc_coefs import load_rrc8_coefficients


FFT_LENGTH = 16
HOP_LENGTH = 8
FILTER_LENGTH = 8
FFT_STAGES = 4
EMIT_START = FFT_LENGTH - HOP_LENGTH
PRODUCTION_WIDTH = 16
SWEEP_WIDTHS = (8, 10, 12, 14, 16, 18)
ROUNDING_MODE = "RNE"
OVERFLOW_MODE = "saturating_narrowing_with_fail_on_internal_overflow"
FFT_MODE = "baseline_A_grow_by_stage"
TRACE_OUTPUT_INDICES = (0, 7, 1024, 2054)
TRACE_BLOCKS = (0, 1, 128, 256)

_SIM_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_DIR = _SIM_DIR / "artifacts" / "t20-fxp"
_DEFAULT_VECTORS_DIR = _SIM_DIR.parent / "vectors"
_SOURCE_FILES = ("fxp.py", "sqnr.py", "rrc_coefs.py", "gen_vectors.py")
_HASH_SERIALIZATION = {
    "algorithm": "SHA-256",
    "array_order": "C",
    "byte_order": "little-endian",
    "samples_dtype": "<c16",
    "coefficients_dtype": "<f8",
    "codes_dtype": "<i8",
    "codes_layout": "shape (samples, 2), columns [I, Q]",
}
# Minimum distance of an exactly computed constant from an RNE decision
# boundary; float64 evaluation error is many orders of magnitude smaller.
_CONSTANT_TIE_MARGIN = 1e-6
# fxpmath rounds through float64: exact only while the operand has at most
# 53 significant bits.
_FLOAT64_SIGNIFICAND_BITS = 53
_QUANTIZE_WORD = _FLOAT64_SIGNIFICAND_BITS + 1
# Widest source word kept on fxpmath's int64 path; a 64-bit word switches it to
# its object path, which warns that rounding may be bypassed.
_SATURATE_SOURCE_WORD = 63


@dataclass(frozen=True)
class FxpPolicy:
    """Production-A widths derived from the common width ``W`` (``Q2.(W-2)``)."""

    width: int = PRODUCTION_WIDTH

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width < 4:
            raise ValueError("width: expected an integer of at least 4 bits")

    @property
    def fraction_bits(self) -> int:
        return self.width - 2

    @property
    def product_width(self) -> int:
        return 2 * self.width

    @property
    def time_accumulator_width(self) -> int:
        return 2 * self.width + 3

    @property
    def fft_stage_widths(self) -> tuple[int, ...]:
        """Component width at the FFT input and after each of the four stages."""
        return tuple(self.width + stage for stage in range(FFT_STAGES + 1))

    @property
    def spectral_product_width(self) -> int:
        return 2 * self.fft_stage_widths[-1] + 1

    @property
    def ifft_stage_widths(self) -> tuple[int, ...]:
        """Component width at the IFFT input and after each of the four stages."""
        return tuple(self.spectral_product_width + stage for stage in range(FFT_STAGES + 1))

    @property
    def frequency_accumulator_width(self) -> int:
        return self.ifft_stage_widths[-1]

    @property
    def output_shift(self) -> int:
        """Bits dropped by the final cast: ``2F + log2(16)`` down to ``F``."""
        return self.fraction_bits + FFT_STAGES

    @property
    def ifft_scale(self) -> str:
        return f"divide_by_16_then_cast_to_Q2.{self.fraction_bits}"

    def manifest_fields(self) -> dict:
        """Return the schema section 2 fields of this policy."""
        return {
            "W_common": self.width,
            "F_data": self.fraction_bits,
            "F_coeff": self.fraction_bits,
            "rounding_mode": ROUNDING_MODE,
            "overflow_mode": OVERFLOW_MODE,
            "W_product": self.product_width,
            "W_acc_time": self.time_accumulator_width,
            "fft_mode": FFT_MODE,
            "fft_stage_widths": list(self.fft_stage_widths),
            "W_acc_freq": self.frequency_accumulator_width,
            "ifft_scale": self.ifft_scale,
        }


PRODUCTION_POLICY = FxpPolicy()


def _as_integer_array(values) -> np.ndarray:
    """Return ``values`` as an ``object`` array of exact Python integers."""
    array = np.asarray(values)
    if array.dtype.kind in "iu":
        return array.astype(object)
    if array.dtype == object and all(type(value) is int for value in array.flat):
        return array.copy()
    raise TypeError("values: expected integers, float or boolean payloads are never narrowed")


def fits(values, width: int) -> np.ndarray:
    """Return a mask of the values representable as signed ``width``-bit integers."""
    array = _as_integer_array(values)
    return (array >= -(1 << (width - 1))) & (array <= (1 << (width - 1)) - 1)


def _fxp_word(values, n_word: int, n_frac: int, raw: bool = False) -> Fxp:
    """Signed fxpmath word with the policy's RNE (``around``) and saturating overflow."""
    return Fxp(values, signed=True, n_word=n_word, n_frac=n_frac, raw=raw, rounding="around", overflow="saturate")


def _raw_codes(word: Fxp, shape: tuple) -> np.ndarray:
    """Return the raw integers of an fxpmath word as exact Python integers."""
    return np.array([int(value) for value in np.asarray(word.val).ravel()], dtype=object).reshape(shape)


def saturate(values, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Clamp to the signed ``width``-bit range with fxpmath; return the values and a saturation mask.

    Saturation applies only at explicit narrowing boundaries, on values that
    were already rounded, so the input is limited to 63 bits (fxpmath's int64
    path) and the output word to 53 bits, where fxpmath is exact.
    """
    array = _as_integer_array(values)
    if width > _FLOAT64_SIGNIFICAND_BITS:
        raise ValueError("width: fxpmath saturation is exact only up to 53 bits")
    if not np.all(fits(array, _SATURATE_SOURCE_WORD)):
        raise ValueError("values: expected an already narrowed value of at most 63 bits")
    if array.size == 0:
        return array, np.zeros(array.shape, dtype=bool)
    source = _fxp_word(array.ravel().astype(np.int64), _SATURATE_SOURCE_WORD, 0, raw=True)
    return _raw_codes(_fxp_word(source, width, 0), array.shape), ~fits(array, width)


def round_shift(values, shift: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Divide by ``2**shift`` with round-to-nearest, ties-to-even (RNE).

    The rounding is fxpmath ``rounding='around'``. To keep its float64 path
    exact at any width, the operand is reduced first: ``m = 2*floor(v / 2^(shift+1))``
    is an even integer, the reduced operand ``v - m*2^shift`` lies in
    ``[0, 2^(shift+1))``, and ``RNE(v / 2^shift) = m + RNE(reduced / 2^shift)``
    because ties-to-even is invariant under even integer offsets.

    Returns the rounded integers, a mask of inexact results and a mask of exact
    ties (dropped bits ``100...0``). RNE is odd-symmetric:
    ``round_shift(-v) == -round_shift(v)``.
    """
    array = _as_integer_array(values)
    if type(shift) is not int or shift < 0:
        raise ValueError("shift: expected a nonnegative integer")
    if shift + 2 > _FLOAT64_SIGNIFICAND_BITS:
        raise ValueError("shift: the reduced operand must stay within the float64 significand")
    if shift == 0 or array.size == 0:
        no_flags = np.zeros(array.shape, dtype=bool)
        return array, no_flags, no_flags.copy()
    offset = (array >> (shift + 1)) << 1
    reduced = array - (offset << shift)
    source = _fxp_word(reduced.ravel().astype(np.int64), shift + 2, shift, raw=True)
    rounded = offset + _raw_codes(_fxp_word(source, 3, 0), array.shape)
    half = 1 << (shift - 1)
    inexact = (reduced != 0) & (reduced != 1 << shift)
    tie = (reduced == half) | (reduced == 3 * half)
    return rounded, inexact, tie


def quantize(values, width: int, fraction_bits: int) -> tuple[np.ndarray, np.ndarray]:
    """Quantize real values to signed ``Q(width-F).F`` codes with fxpmath RNE and saturation.

    The unbounded code comes from a 54-bit fxpmath word, which cannot saturate
    while ``|x * 2^F| < 2^52``; the ``width``-bit saturation is a separate step
    so its events are counted. Scaling by a power of two is exact in float64.
    """
    real = np.asarray(values, dtype=np.float64)
    scaled = real * float(1 << fraction_bits)
    if not np.all(np.isfinite(scaled)) or np.any(np.abs(scaled) >= 2.0**52):
        raise ValueError("values: expected finite values within the exact float64 range")
    if real.size == 0:
        return np.zeros(real.shape, dtype=object), np.zeros(real.shape, dtype=bool)
    unbounded = _raw_codes(_fxp_word(real.ravel(), _QUANTIZE_WORD, fraction_bits), real.shape)
    return saturate(unbounded, width)


def quantize_coefficients(policy: FxpPolicy = PRODUCTION_POLICY, coefficients=None) -> np.ndarray:
    """Return the eight stored RRC coefficient codes; a range violation is an error."""
    float_coefficients = load_rrc8_coefficients() if coefficients is None else np.asarray(coefficients)
    if float_coefficients.shape != (FILTER_LENGTH,):
        raise ValueError("coefficients: expected eight values")
    codes, saturated = quantize(float_coefficients, policy.width, policy.fraction_bits)
    if np.any(saturated):
        raise ValueError("coefficients: range violation, refusing to saturate a stored coefficient")
    return codes


def quantize_samples(samples, policy: FxpPolicy = PRODUCTION_POLICY) -> tuple[np.ndarray, np.ndarray]:
    """Return the I and Q input codes; a range violation is an error."""
    complex_samples = np.asarray(samples, dtype=np.complex128)
    if complex_samples.ndim != 1:
        raise ValueError("samples: expected a one-dimensional array")
    i_codes, i_saturated = quantize(complex_samples.real, policy.width, policy.fraction_bits)
    q_codes, q_saturated = quantize(complex_samples.imag, policy.width, policy.fraction_bits)
    if np.any(i_saturated) or np.any(q_saturated):
        raise ValueError("samples: input range violation")
    return i_codes, q_codes


def decode(i_codes, q_codes, fraction_bits: int) -> np.ndarray:
    """Return the complex real values represented by I/Q codes."""
    scale = float(1 << fraction_bits)
    real = np.asarray(i_codes, dtype=np.float64) / scale
    imag = np.asarray(q_codes, dtype=np.float64) / scale
    return real + 1j * imag


def _quantize_constant(values: np.ndarray, policy: FxpPolicy, name: str) -> np.ndarray:
    """RNE-quantize exactly evaluated constants, rejecting near-ties and range violations."""
    scaled = np.asarray(values, dtype=np.float64)
    distance_to_tie = np.abs(np.abs(scaled - np.floor(scaled)) - 0.5)
    if np.any(distance_to_tie < _CONSTANT_TIE_MARGIN):
        raise ValueError(f"{name}: value too close to an RNE tie to quantize from float64")
    codes, saturated = quantize(scaled / float(1 << policy.fraction_bits), policy.width, policy.fraction_bits)
    if np.any(saturated):
        raise ValueError(f"{name}: range violation in Q2.{policy.fraction_bits}")
    return codes


def twiddle_codes(policy: FxpPolicy = PRODUCTION_POLICY) -> tuple[np.ndarray, np.ndarray]:
    """Return ``T[k] = exp(-j 2 pi k / 16)`` for ``k = 0..7`` in ``Q2.(W-2)``."""
    angle = 2 * np.pi * np.arange(FFT_LENGTH // 2) / FFT_LENGTH
    scale = float(1 << policy.fraction_bits)
    return (
        _quantize_constant(np.cos(angle) * scale, policy, "twiddles"),
        _quantize_constant(-np.sin(angle) * scale, policy, "twiddles"),
    )


def h_spectrum_codes(
    policy: FxpPolicy = PRODUCTION_POLICY,
    coefficient_codes=None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``H[k]`` in natural bin order: the exact DFT16 of the quantized taps, one RNE.

    The taps are zero-padded to 16. Because the codes already carry ``2^F``,
    ``sum(c[n] exp(-j 2 pi k n / 16))`` is ``H[k] * 2^F`` before rounding.
    """
    codes = quantize_coefficients(policy) if coefficient_codes is None else _as_integer_array(coefficient_codes)
    taps = np.asarray(codes, dtype=np.float64)
    angle = 2 * np.pi * np.outer(np.arange(FFT_LENGTH), np.arange(FILTER_LENGTH)) / FFT_LENGTH
    return (
        _quantize_constant(np.cos(angle) @ taps, policy, "H[k]"),
        _quantize_constant(-np.sin(angle) @ taps, policy, "H[k]"),
    )


def bit_reversed_indices(length: int = FFT_LENGTH) -> np.ndarray:
    """Return the bit-reversal permutation of ``range(length)``."""
    bits = length.bit_length() - 1
    if length != 1 << bits:
        raise ValueError("length: expected a power of two")
    return np.array([int(f"{index:0{bits}b}"[::-1], 2) if bits else 0 for index in range(length)])


@dataclass
class ArithmeticMonitor:
    """Overflow, range and rounding counters per named datapath point."""

    overflow: dict[str, int] = field(default_factory=dict)
    declared_width: dict[str, int] = field(default_factory=dict)
    minimum: dict[str, int] = field(default_factory=dict)
    maximum: dict[str, int] = field(default_factory=dict)
    rounding: dict[str, dict[str, int]] = field(default_factory=dict)
    output_saturation_count: int = 0

    def check(self, point: str, values: np.ndarray, width: int) -> None:
        """Record the range of ``values`` and count those outside ``width`` bits."""
        if values.size == 0:
            return
        self.declared_width[point] = width
        self.minimum[point] = min(self.minimum.get(point, 0), int(values.min()))
        self.maximum[point] = max(self.maximum.get(point, 0), int(values.max()))
        violations = int(np.count_nonzero(~fits(values, width)))
        self.overflow[point] = self.overflow.get(point, 0) + violations

    def narrow(self, point: str, values: np.ndarray, shift: int) -> np.ndarray:
        """Apply an RNE narrowing and count operations, inexact results and ties."""
        rounded, inexact, tie = round_shift(values, shift)
        counts = self.rounding.setdefault(point, {"operations": 0, "inexact": 0, "ties": 0})
        counts["operations"] += int(values.size)
        counts["inexact"] += int(np.count_nonzero(inexact))
        counts["ties"] += int(np.count_nonzero(tie))
        return rounded

    @property
    def internal_overflow_count(self) -> int:
        return sum(self.overflow.values())

    def required_width(self, point: str) -> int:
        """Smallest signed width holding every value seen at ``point``."""
        low, high = self.minimum[point], self.maximum[point]
        return max((-low - 1).bit_length(), high.bit_length()) + 1

    def as_dict(self) -> dict:
        return {
            "internal_overflow_count": self.internal_overflow_count,
            "output_saturation_count": self.output_saturation_count,
            "ranges": {
                point: {
                    "declared_width": self.declared_width[point],
                    "required_width": self.required_width(point),
                    "min": self.minimum[point],
                    "max": self.maximum[point],
                    "overflow_count": self.overflow[point],
                }
                for point in sorted(self.declared_width)
            },
            "rounding": {point: dict(counts) for point, counts in sorted(self.rounding.items())},
        }


@dataclass
class FxpResult:
    """Output codes of one integer model run plus its counters and traces."""

    domain: str
    policy: FxpPolicy
    i_codes: np.ndarray
    q_codes: np.ndarray
    monitor: ArithmeticMonitor
    trace: list[dict]

    def decoded(self) -> np.ndarray:
        return decode(self.i_codes, self.q_codes, self.policy.fraction_bits)

    def codes_sha256(self) -> str:
        codes = np.stack((self.i_codes, self.q_codes), axis=1).astype(_HASH_SERIALIZATION["codes_dtype"])
        return hashlib.sha256(codes.tobytes(order="C")).hexdigest()


def _integers(values: np.ndarray) -> list:
    return [int(value) for value in np.asarray(values).ravel()]


def _cast_output(
    monitor: ArithmeticMonitor,
    values: np.ndarray,
    shift: int,
    policy: FxpPolicy,
) -> np.ndarray:
    """Single RNE narrowing to ``F`` fractional bits, then saturation to ``W`` bits."""
    rounded = monitor.narrow("output_cast", values, shift)
    codes, saturated = saturate(rounded, policy.width)
    monitor.output_saturation_count += int(np.count_nonzero(saturated))
    return codes


def filter_time_fxp(
    samples,
    policy: FxpPolicy = PRODUCTION_POLICY,
    trace_indices=(),
) -> FxpResult:
    """Integer causal FIR over the full causal window.

    Full-precision ``2W``-bit products are summed in ascending tap order in a
    ``2W+3``-bit accumulator with no intermediate rounding; the only narrowing
    is the final RNE/saturating cast to ``Q2.(W-2)``.
    """
    input_i, input_q = quantize_samples(samples, policy)
    coefficients = quantize_coefficients(policy)
    monitor = ArithmeticMonitor()
    output_length = input_i.size + FILTER_LENGTH - 1
    history = np.zeros(FILTER_LENGTH - 1, dtype=object)
    taps = np.arange(FILTER_LENGTH)
    window_index = np.arange(output_length)[:, np.newaxis] + (FILTER_LENGTH - 1) - taps

    components = {}
    for name, codes in (("i", input_i), ("q", input_q)):
        padded = np.concatenate((history, codes, history))
        window = padded[window_index]
        products = window * coefficients
        monitor.check("time_product", products, policy.product_width)
        partial_sums = np.cumsum(products, axis=1)
        monitor.check("time_accumulator", partial_sums, policy.time_accumulator_width)
        output = _cast_output(monitor, partial_sums[:, -1], policy.fraction_bits, policy)
        components[name] = (window, products, partial_sums, output)

    trace = []
    for index in trace_indices:
        entry = {"output_index": int(index)}
        for name, (window, products, partial_sums, output) in components.items():
            entry[f"input_{name}"] = _integers(window[index])
            entry[f"products_{name}"] = _integers(products[index])
            entry[f"partial_sums_{name}"] = _integers(partial_sums[index])
            entry[f"output_{name}"] = int(output[index])
        trace.append(entry)

    return FxpResult(
        domain="time",
        policy=policy,
        i_codes=components["i"][3].astype(np.int64),
        q_codes=components["q"][3].astype(np.int64),
        monitor=monitor,
        trace=trace,
    )


def _complex_multiply(a_real, a_imag, b_real, b_imag) -> tuple[np.ndarray, np.ndarray]:
    return a_real * b_real - a_imag * b_imag, a_real * b_imag + a_imag * b_real


def fft16_dif(
    real: np.ndarray,
    imag: np.ndarray,
    twiddles: tuple[np.ndarray, np.ndarray],
    policy: FxpPolicy,
    monitor: ArithmeticMonitor,
    stages: list | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Unscaled radix-2 DIF FFT16 on rows; natural-order input, bit-reversed output.

    Butterfly: ``u = a + b``, ``v = RNE_F((a - b) * T[k])`` with
    ``k = j * 16 / (2 * span)``. Stage ``s`` values must fit ``W + s`` bits.
    """
    twiddle_real, twiddle_imag = twiddles
    real, imag = _as_integer_array(real), _as_integer_array(imag)
    blocks = real.shape[0]
    for stage, span in enumerate((8, 4, 2, 1), start=1):
        groups = FFT_LENGTH // (2 * span)
        width = policy.fft_stage_widths[stage]
        shaped_real = real.reshape(blocks, groups, 2, span)
        shaped_imag = imag.reshape(blocks, groups, 2, span)
        a_real, b_real = shaped_real[:, :, 0, :], shaped_real[:, :, 1, :]
        a_imag, b_imag = shaped_imag[:, :, 0, :], shaped_imag[:, :, 1, :]
        k = np.arange(span) * groups
        product_real, product_imag = _complex_multiply(
            a_real - b_real, a_imag - b_imag, twiddle_real[k], twiddle_imag[k]
        )
        v_real = monitor.narrow("fft_twiddle", product_real, policy.fraction_bits)
        v_imag = monitor.narrow("fft_twiddle", product_imag, policy.fraction_bits)
        real = np.stack((a_real + b_real, v_real), axis=2).reshape(blocks, FFT_LENGTH)
        imag = np.stack((a_imag + b_imag, v_imag), axis=2).reshape(blocks, FFT_LENGTH)
        monitor.check(f"fft_stage{stage}", np.concatenate((real, imag), axis=1), width)
        if stages is not None:
            stages.append((real, imag))
    return real, imag


def ifft16_dit(
    real: np.ndarray,
    imag: np.ndarray,
    twiddles: tuple[np.ndarray, np.ndarray],
    policy: FxpPolicy,
    monitor: ArithmeticMonitor,
    stages: list | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Unscaled radix-2 DIT IFFT16 on rows; bit-reversed input, natural-order output.

    Butterfly: ``v = RNE_F(b * conj(T[k]))``, then ``a + v`` and ``a - v``;
    ``v`` and both outputs of stage ``s`` must fit the stage-``s`` width. The
    result is 16 times the inverse DFT; the final cast removes that factor.
    """
    twiddle_real, twiddle_imag = twiddles
    real, imag = _as_integer_array(real), _as_integer_array(imag)
    blocks = real.shape[0]
    for stage, span in enumerate((1, 2, 4, 8), start=1):
        groups = FFT_LENGTH // (2 * span)
        width = policy.ifft_stage_widths[stage]
        shaped_real = real.reshape(blocks, groups, 2, span)
        shaped_imag = imag.reshape(blocks, groups, 2, span)
        a_real, b_real = shaped_real[:, :, 0, :], shaped_real[:, :, 1, :]
        a_imag, b_imag = shaped_imag[:, :, 0, :], shaped_imag[:, :, 1, :]
        k = np.arange(span) * groups
        product_real, product_imag = _complex_multiply(b_real, b_imag, twiddle_real[k], -twiddle_imag[k])
        v_real = monitor.narrow("ifft_twiddle", product_real, policy.fraction_bits)
        v_imag = monitor.narrow("ifft_twiddle", product_imag, policy.fraction_bits)
        monitor.check(f"ifft_stage{stage}_rotated", np.concatenate((v_real, v_imag), axis=1), width)
        real = np.stack((a_real + v_real, a_real - v_real), axis=2).reshape(blocks, FFT_LENGTH)
        imag = np.stack((a_imag + v_imag, a_imag - v_imag), axis=2).reshape(blocks, FFT_LENGTH)
        monitor.check(f"ifft_stage{stage}", np.concatenate((real, imag), axis=1), width)
        if stages is not None:
            stages.append((real, imag))
    return real, imag


def filter_frequency_fxp(
    samples,
    policy: FxpPolicy = PRODUCTION_POLICY,
    trace_blocks=(),
) -> FxpResult:
    """Integer forced-50% overlap-save filter (FFT16, hop 8, emit ``z[8:16]``).

    Frames start with eight zero history samples, exactly as the float golden.
    The spectral product keeps full precision; the IFFT output carries ``2F``
    fractional bits and a factor 16, removed by one RNE shift of ``F + 4``.
    """
    input_i, input_q = quantize_samples(samples, policy)
    monitor = ArithmeticMonitor()
    twiddles = twiddle_codes(policy)
    h_real, h_imag = h_spectrum_codes(policy)
    storage_order = bit_reversed_indices()
    h_real, h_imag = h_real[storage_order], h_imag[storage_order]

    output_length = input_i.size + FILTER_LENGTH - 1
    block_count = -(-output_length // HOP_LENGTH)
    right_padding = block_count * HOP_LENGTH - input_i.size
    zeros_left = np.zeros(HOP_LENGTH, dtype=object)
    zeros_right = np.zeros(right_padding, dtype=object)
    frame_index = np.arange(block_count)[:, np.newaxis] * HOP_LENGTH + np.arange(FFT_LENGTH)
    frame_real = np.concatenate((zeros_left, input_i, zeros_right))[frame_index]
    frame_imag = np.concatenate((zeros_left, input_q, zeros_right))[frame_index]
    monitor.check("fft_input", np.concatenate((frame_real, frame_imag), axis=1), policy.fft_stage_widths[0])

    fft_stages: list = []
    spectrum_real, spectrum_imag = fft16_dif(frame_real, frame_imag, twiddles, policy, monitor, fft_stages)
    product_real, product_imag = _complex_multiply(spectrum_real, spectrum_imag, h_real, h_imag)
    monitor.check(
        "spectral_product",
        np.concatenate((product_real, product_imag), axis=1),
        policy.spectral_product_width,
    )
    ifft_stages: list = []
    block_real, block_imag = ifft16_dit(product_real, product_imag, twiddles, policy, monitor, ifft_stages)

    emitted_real = block_real[:, EMIT_START:].reshape(-1)
    emitted_imag = block_imag[:, EMIT_START:].reshape(-1)
    output_i = _cast_output(monitor, emitted_real[:output_length], policy.output_shift, policy)
    output_q = _cast_output(monitor, emitted_imag[:output_length], policy.output_shift, policy)

    trace = []
    for block in trace_blocks:
        first = int(block) * HOP_LENGTH
        valid = max(0, min(HOP_LENGTH, output_length - first))
        entry = {
            "block": int(block),
            "first_output_index": first,
            "valid_outputs": valid,
            "frame_i": _integers(frame_real[block]),
            "frame_q": _integers(frame_imag[block]),
        }
        for stage, (real, imag) in enumerate(fft_stages, start=1):
            entry[f"fft_stage{stage}_i"] = _integers(real[block])
            entry[f"fft_stage{stage}_q"] = _integers(imag[block])
        entry["spectral_product_i"] = _integers(product_real[block])
        entry["spectral_product_q"] = _integers(product_imag[block])
        for stage, (real, imag) in enumerate(ifft_stages, start=1):
            entry[f"ifft_stage{stage}_i"] = _integers(real[block])
            entry[f"ifft_stage{stage}_q"] = _integers(imag[block])
        entry["output_i"] = _integers(output_i[first : first + valid])
        entry["output_q"] = _integers(output_q[first : first + valid])
        trace.append(entry)

    return FxpResult(
        domain="frequency",
        policy=policy,
        i_codes=output_i.astype(np.int64),
        q_codes=output_q.astype(np.int64),
        monitor=monitor,
        trace=trace,
    )


def run_fxp_model(domain: str, samples, policy: FxpPolicy = PRODUCTION_POLICY, trace: bool = False) -> FxpResult:
    """Run the integer model of ``domain`` (``time`` or ``frequency``)."""
    if domain == "time":
        return filter_time_fxp(samples, policy, TRACE_OUTPUT_INDICES if trace else ())
    if domain == "frequency":
        return filter_frequency_fxp(samples, policy, TRACE_BLOCKS if trace else ())
    raise ValueError(f"domain: expected 'time' or 'frequency', got {domain!r}")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_db(value: float) -> float | None:
    """JSON-safe dB value: ``None`` stands for an error-free (infinite) SQNR."""
    return None if math.isinf(value) else value


def _load_f1_frame(vectors_dir: Path, vector_set: str, vector_case: str) -> dict:
    """Read and hash-check the F1 input and float references of one frame."""
    from gen_vectors import INPUT_FILE, MANIFEST_FILE, REFERENCE_FILE, read_samples

    frame_dir = vectors_dir / "float_reference" / vector_set / vector_case
    frame = {"manifest_sha256": {}, "reference": {}}
    for domain, tag in (("time", "time"), ("frequency", "freq")):
        manifest_path = frame_dir / MANIFEST_FILE.format(tag=tag)
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest["artifact_stage"] != "float_reference" or manifest["model_domain"] != domain:
            raise ValueError(f"{manifest_path}: expected the {domain} float_reference manifest")
        input_path = frame_dir / INPUT_FILE
        reference_path = frame_dir / REFERENCE_FILE.format(tag=tag)
        if _sha256_bytes(input_path.read_bytes()) != manifest["hashes"]["input_samples_sha256"]:
            raise ValueError(f"{input_path}: hash does not match its F1 manifest")
        if _sha256_bytes(reference_path.read_bytes()) != manifest["hashes"]["reference_sha256"]:
            raise ValueError(f"{reference_path}: hash does not match its F1 manifest")
        frame["manifest_sha256"][domain] = _sha256_bytes(manifest_bytes)
        frame["samples"] = read_samples(input_path)
        frame["reference"][domain] = read_samples(reference_path)
    return frame


def measure_frame(samples, references: dict, policy: FxpPolicy = PRODUCTION_POLICY, trace: bool = False) -> dict:
    """Run both integer models on one frame and measure them against their float references."""
    from sqnr import split_half_sqnr_db, sqnr_cross_db, sqnr_db

    results = {domain: run_fxp_model(domain, samples, policy, trace) for domain in ("time", "frequency")}
    measurement = {}
    for domain, result in results.items():
        decoded = result.decoded()
        measurement[domain] = {
            "sqnr_db": _json_db(sqnr_db(references[domain], decoded)),
            "split_half_sqnr_db": [_json_db(value) for value in split_half_sqnr_db(references[domain], decoded)],
            "output_codes_sha256": result.codes_sha256(),
            **result.monitor.as_dict(),
        }
    measurement["sqnr_cross_db"] = _json_db(
        sqnr_cross_db(references["time"], results["time"].decoded(), results["frequency"].decoded())
    )
    return {"measurement": measurement, "results": results}


def _freeze_record(policy: FxpPolicy) -> dict:
    twiddle_real, twiddle_imag = twiddle_codes(policy)
    h_real, h_imag = h_spectrum_codes(policy)
    return {
        "status": "proposed in the fxp-policy-16.md T20 amendment, pending frequency co-design sign-off",
        "format": f"Q2.{policy.fraction_bits}",
        "narrowing_implementation": (
            "fxpmath rounding='around' (RNE) and overflow='saturate'; integer RNE narrowing reduces "
            "the operand by an even multiple of the step so the float64 path is exact at any width"
        ),
        "coefficient_codes": _integers(quantize_coefficients(policy)),
        "time": {
            "product_width": policy.product_width,
            "product_fraction_bits": 2 * policy.fraction_bits,
            "accumulator_width": policy.time_accumulator_width,
            "accumulation_order": "ascending tap index k = 0..7, no intermediate rounding",
            "output_cast": f"RNE right shift by {policy.fraction_bits}, saturate to {policy.width} bits",
        },
        "frequency": {
            "forward": "radix-2 DIF, spans 8,4,2,1, natural-order input, bit-reversed output, unscaled",
            "inverse": "radix-2 DIT, spans 1,2,4,8, bit-reversed input, natural-order output, conjugate twiddles, unscaled",
            "bin_numbering": "standard DFT bin k (k=0 is DC); bit-reversed storage is an address mapping",
            "twiddles": {
                "definition": "T[k] = exp(-j*2*pi*k/16), k = 0..7, RNE from exact value",
                "real": _integers(twiddle_real),
                "imag": _integers(twiddle_imag),
            },
            "h_spectrum": {
                "definition": "exact DFT16 of the quantized taps zero-padded to 16, one RNE",
                "order": "natural bin k",
                "storage_order": "bit_reversed",
                "real": _integers(h_real),
                "imag": _integers(h_imag),
            },
            "fft_stage_widths": list(policy.fft_stage_widths),
            "fft_fraction_bits": policy.fraction_bits,
            "fft_twiddle_narrowing": f"RNE right shift by {policy.fraction_bits} into the stage width",
            "spectral_product_width": policy.spectral_product_width,
            "spectral_product_fraction_bits": 2 * policy.fraction_bits,
            "ifft_stage_widths": list(policy.ifft_stage_widths),
            "ifft_fraction_bits": 2 * policy.fraction_bits,
            "ifft_twiddle_narrowing": f"RNE right shift by {policy.fraction_bits} into the stage width",
            "output_cast": (
                f"divide by 16 as an exact binary-point move, then one RNE right shift by "
                f"{policy.output_shift} and saturation to {policy.width} bits"
            ),
            "total_scale": "forward x1, inverse x16 (unscaled), final /16 exactly once",
        },
    }


def _tie_reachability(frames: dict) -> dict:
    """Summarize RNE ties and inexact roundings per narrowing point over all frames."""
    summary = {}
    for domain in ("time", "frequency"):
        points: dict[str, dict[str, int]] = {}
        for frame in frames.values():
            for point, counts in frame[domain]["rounding"].items():
                total = points.setdefault(point, {"operations": 0, "inexact": 0, "ties": 0})
                for key in total:
                    total[key] += counts[key]
        summary[domain] = points
    return summary


def generate_fxp_evidence(
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    policy: FxpPolicy = PRODUCTION_POLICY,
    vectors_dir: Path = _DEFAULT_VECTORS_DIR,
) -> Path:
    """Write the T20 evidence manifest and integer traces for one policy."""
    from gen_vectors import iter_frames
    from sqnr import SQNR_CROSS_MIN_DB, SQNR_MIN_DB

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    traces = {}
    for vector_set, vector_case in iter_frames():
        key = f"{vector_set}/{vector_case}"
        frame = _load_f1_frame(Path(vectors_dir), vector_set, vector_case)
        canonical = vector_set == "canonical"
        measured = measure_frame(frame["samples"], frame["reference"], policy, trace=canonical)
        frames[key] = {"f1_manifest_sha256": frame["manifest_sha256"], **measured["measurement"]}
        if canonical:
            traces = {domain: result.trace for domain, result in measured["results"].items()}

    traces_document = {
        "evidence_version": "t20-fxp-traces-v1",
        "frame": "canonical/none",
        "policy": policy.manifest_fields(),
        "time": {
            "output_indices": list(TRACE_OUTPUT_INDICES),
            "operand_order": "input_*, products_* and partial_sums_* listed for taps k = 0..7 (x[n-k] * h[k])",
            "entries": traces["time"],
        },
        "frequency": {
            "blocks": list(TRACE_BLOCKS),
            "stage_storage_order": "fft stages in DIF butterfly order (stage 4 = bit-reversed bins); "
            "spectral product in bit-reversed bin order; ifft stage 4 in natural time order",
            "entries": traces["frequency"],
        },
    }
    traces_path = output_dir / "traces.json"
    traces_path.write_text(json.dumps(traces_document, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    canonical = frames["canonical/none"]
    gate = {
        "scope": "preview on the canonical frame; numerical acceptance is T21 (#45)",
        "sqnr_min_db": SQNR_MIN_DB,
        "sqnr_cross_min_db": SQNR_CROSS_MIN_DB,
        "sqnr_time_passed": canonical["time"]["sqnr_db"] is None or canonical["time"]["sqnr_db"] >= SQNR_MIN_DB,
        "sqnr_freq_passed": canonical["frequency"]["sqnr_db"] is None
        or canonical["frequency"]["sqnr_db"] >= SQNR_MIN_DB,
        "sqnr_cross_passed": canonical["sqnr_cross_db"] is None or canonical["sqnr_cross_db"] >= SQNR_CROSS_MIN_DB,
        "internal_overflow_count": sum(
            frame[domain]["internal_overflow_count"] for frame in frames.values() for domain in ("time", "frequency")
        ),
        "canonical_output_saturation_count": sum(
            canonical[domain]["output_saturation_count"] for domain in ("time", "frequency")
        ),
    }
    gate["passed"] = bool(
        gate["sqnr_time_passed"]
        and gate["sqnr_freq_passed"]
        and gate["sqnr_cross_passed"]
        and gate["internal_overflow_count"] == 0
        and gate["canonical_output_saturation_count"] == 0
    )

    manifest = {
        "evidence_version": "t20-fxp-v1",
        "stage": "fxp_model_evidence",
        "scope": "integer FXP model evidence; not fxp_expected vectors (T22) or the width sweep (T21)",
        "hash_serialization": _HASH_SERIALIZATION,
        "policy": policy.manifest_fields(),
        "freeze": _freeze_record(policy),
        "window": {"valid_start": 0, "valid_len": 2055},
        "sqnr_reference": {
            "per_domain": "each domain against its own F1 float reference",
            "cross_domain": "time F1 float reference as common signal power",
            "null_db": "zero quantization error (infinite SQNR)",
        },
        "frames": frames,
        "tie_reachability": _tie_reachability(frames),
        "gate_preview": gate,
        "traces": {"file": traces_path.name, "sha256": _sha256_bytes(traces_path.read_bytes())},
        "provenance": {
            "source_sha256": {name: _sha256_bytes((_SIM_DIR / name).read_bytes()) for name in _SOURCE_FILES},
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "fxpmath": fxpmath.__version__,
            },
        },
    }
    manifest_path = output_dir / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the T20 integer FXP model evidence")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--vectors-dir", type=Path, default=_DEFAULT_VECTORS_DIR)
    parser.add_argument("--width", type=int, default=PRODUCTION_WIDTH, help="common width W (Q2.(W-2))")
    args = parser.parse_args()
    print(generate_fxp_evidence(args.output_dir, FxpPolicy(args.width), args.vectors_dir))


if __name__ == "__main__":
    main()
