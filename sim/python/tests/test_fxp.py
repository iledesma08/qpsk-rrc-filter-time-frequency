"""Directed arithmetic checks and production-gate preview for the T20 integer FXP models."""

import json
import shutil
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

import fxp
from fxp import (
    PRODUCTION_POLICY,
    ArithmeticMonitor,
    FxpPolicy,
    bit_reversed_indices,
    fft16_dif,
    filter_frequency_fxp,
    filter_time_fxp,
    generate_fxp_evidence,
    h_spectrum_codes,
    ifft16_dit,
    measure_frame,
    quantize,
    quantize_coefficients,
    quantize_samples,
    round_shift,
    run_fxp_model,
    saturate,
    twiddle_codes,
)
from golden_freq import filter_frequency_domain
from golden_time import _filter_time_domain
from rrc_coefs import load_rrc8_coefficients
from sqnr import SQNR_CROSS_MIN_DB, SQNR_MIN_DB, split_half_is_stable
from stimulus import CORNER_CASES, generate_canonical_samples, generate_corner_samples


LSB = 2.0**-14
_COMMITTED_EVIDENCE = Path(fxp.__file__).resolve().parent / "artifacts" / "t20-fxp"
_FRAMES = {"canonical": generate_canonical_samples(), **{case: generate_corner_samples(case) for case in CORNER_CASES}}


@pytest.fixture(scope="module")
def production_frames():
    coefficients = load_rrc8_coefficients()
    measured = {}
    for name, samples in _FRAMES.items():
        references = {
            "time": _filter_time_domain(samples, coefficients),
            "frequency": filter_frequency_domain(samples, coefficients),
        }
        measured[name] = {"references": references, **measure_frame(samples, references, trace=True)}
    return measured


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("t20-fxp")
    return generate_fxp_evidence(output_dir)


# Policy -------------------------------------------------------------------


def test_production_policy_matches_the_contract_widths():
    assert PRODUCTION_POLICY.manifest_fields() == {
        "W_common": 16,
        "F_data": 14,
        "F_coeff": 14,
        "rounding_mode": "RNE",
        "overflow_mode": "saturating_narrowing_with_fail_on_internal_overflow",
        "W_product": 32,
        "W_acc_time": 35,
        "fft_mode": "baseline_A_grow_by_stage",
        "fft_stage_widths": [16, 17, 18, 19, 20],
        "W_acc_freq": 45,
        "ifft_scale": "divide_by_16_then_cast_to_Q2.14",
    }
    assert PRODUCTION_POLICY.spectral_product_width == 41
    assert PRODUCTION_POLICY.ifft_stage_widths == (41, 42, 43, 44, 45)
    assert PRODUCTION_POLICY.output_shift == 18


def test_sweep_widths_derive_every_width_from_w():
    policy = FxpPolicy(10)
    assert policy.fraction_bits == 8
    assert policy.time_accumulator_width == 23
    assert policy.fft_stage_widths == (10, 11, 12, 13, 14)
    assert policy.frequency_accumulator_width == 2 * 14 + 1 + 4


@pytest.mark.parametrize("width", [3, 16.0, True])
def test_policy_rejects_invalid_widths(width):
    with pytest.raises(ValueError):
        FxpPolicy(width)


# Quantizer, rounding and saturation primitives (fxp-policy-16 item 6) ------


@pytest.mark.parametrize(
    ("value", "code", "saturated"),
    [
        (1.0, 16384, False),
        (-1.0, -16384, False),
        (0.0, 0, False),
        (-2.0, -32768, False),
        (2.0 - LSB, 32767, False),
        (2.0, 32767, True),
        (3.5, 32767, True),
        (-2.0 - LSB, -32768, True),
        (-7.25, -32768, True),
    ],
)
def test_quantizer_extremes_and_saturation(value, code, saturated):
    codes, mask = quantize([value], 16, 14)
    assert codes.tolist() == [code]
    assert mask.tolist() == [saturated]


@pytest.mark.parametrize(
    ("offset_lsb", "code_offset"),
    [
        (0.4, 0),
        (0.6, 1),
        (-0.4, 0),
        (-0.6, -1),
        (0.5, 0),
        (1.5, 2),
        (-0.5, 0),
        (-1.5, -2),
        (2.5, 2),
    ],
)
def test_quantizer_rounds_plus_minus_one_lsb_with_ties_to_even(offset_lsb, code_offset):
    codes, mask = quantize([1.0 + offset_lsb * LSB, -1.0 - offset_lsb * LSB], 16, 14)
    assert codes.tolist() == [16384 + code_offset, -16384 - code_offset]
    assert not mask.any()


@pytest.mark.parametrize("shift", [1, 2, 3, 5, 18])
def test_round_shift_matches_exact_round_half_even(shift):
    values = list(range(-1200, 1201)) + [(1 << 40) + (1 << (shift - 1)), -(1 << 44) - (3 << (shift - 1))]
    rounded, inexact, tie = round_shift(values, shift)
    expected = [round(Fraction(value, 1 << shift)) for value in values]
    assert rounded.tolist() == expected
    assert inexact.tolist() == [value % (1 << shift) != 0 for value in values]
    assert tie.tolist() == [value % (1 << shift) == 1 << (shift - 1) for value in values]


@pytest.mark.parametrize(("bits", "shift"), [(61, 14), (63, 16), (67, 16), (90, 20)])
def test_round_shift_stays_exact_beyond_the_float64_significand(bits, shift):
    # Inverse-FFT twiddle products measure 2^52.2 at W=18 in 64-67-bit containers.
    rng = np.random.default_rng(bits)
    limit = 1 << (bits - 2)
    values = [int(value) * limit // (1 << 62) for value in rng.integers(-(1 << 62), 1 << 62, size=2000)]
    values += [(k << shift) + (1 << (shift - 1)) for k in (-(limit >> shift), -3, 3, (limit >> shift) - 1)]
    rounded, _, tie = round_shift(values, shift)
    assert rounded.tolist() == [round(Fraction(value, 1 << shift)) for value in values]
    assert tie[-4:].all()


def test_fxpmath_float64_limit_motivates_the_operand_reduction():
    # Documents the pinned fxpmath behaviour behind round_shift's reduction: a
    # direct raw narrowing of a 61-bit value goes through float64 and misrounds.
    from fxpmath import Fxp

    value = -458008934979084306
    direct = Fxp(Fxp(np.array([value]), True, 61, 28, raw=True), True, 47, 14, rounding="around")
    assert int(direct.val[0]) != round(Fraction(value, 1 << 14))
    assert round_shift([value], 14)[0].tolist() == [round(Fraction(value, 1 << 14))]


def test_narrowing_primitives_refuse_widths_fxpmath_cannot_round_exactly():
    with pytest.raises(ValueError, match="53 bits"):
        saturate([1], 54)
    with pytest.raises(ValueError, match="at most 63 bits"):
        saturate([1 << 70], 16)
    with pytest.raises(ValueError, match="significand"):
        round_shift([1], 52)


def test_round_shift_ties_go_to_even_for_both_signs():
    rounded, inexact, tie = round_shift([1, 3, 5, -1, -3, -5, 6, -6, 7, -7], 1)
    assert rounded.tolist() == [0, 2, 2, 0, -2, -2, 3, -3, 4, -4]
    assert tie.tolist() == [True] * 6 + [False, False, True, True]
    assert inexact.tolist() == tie.tolist()


def test_round_shift_is_odd_symmetric():
    values = np.arange(-5000, 5001)
    for shift in (1, 4, 9):
        assert round_shift(-values, shift)[0].tolist() == (-round_shift(values, shift)[0]).tolist()


def test_round_shift_by_zero_is_the_identity():
    rounded, inexact, tie = round_shift([5, -3], 0)
    assert rounded.tolist() == [5, -3]
    assert not inexact.any() and not tie.any()


@pytest.mark.parametrize("values", [[0.5], [True], np.array([1.0])])
def test_round_shift_refuses_float_or_boolean_payloads(values):
    with pytest.raises(TypeError):
        round_shift(values, 2)


def test_saturate_clamps_both_sides_and_flags_events():
    values, mask = saturate([32767, 32768, -32768, -32769, 0, 1 << 40], 16)
    assert values.tolist() == [32767, 32767, -32768, -32768, 0, 32767]
    assert mask.tolist() == [False, True, False, True, False, True]


def test_production_coefficients_are_the_contract_integers():
    assert quantize_coefficients().tolist() == [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]


def test_coefficient_range_violation_is_an_error_not_a_saturation():
    with pytest.raises(ValueError, match="range violation"):
        quantize_coefficients(coefficients=[2.5, 0, 0, 0, 0, 0, 0, 0])


def test_input_range_violation_is_an_error():
    with pytest.raises(ValueError, match="input range violation"):
        quantize_samples(np.array([1 + 1j, 2 + 0j]))


# Frozen constants ----------------------------------------------------------


def test_production_twiddles_are_q2_14():
    real, imag = twiddle_codes()
    assert real.tolist() == [16384, 15137, 11585, 6270, 0, -6270, -11585, -15137]
    assert imag.tolist() == [0, -6270, -11585, -15137, -16384, -15137, -11585, -6270]


def test_twiddles_follow_the_common_width_in_the_sweep():
    real, imag = twiddle_codes(FxpPolicy(8))
    assert real.tolist() == [64, 59, 45, 24, 0, -24, -45, -59]
    assert imag.tolist() == [0, -24, -45, -59, -64, -59, -45, -24]


def test_h_spectrum_is_one_rne_of_the_exact_dft_of_quantized_taps():
    real, imag = h_spectrum_codes()
    taps = np.zeros(16)
    taps[:8] = quantize_coefficients().astype(np.float64)
    exact = np.fft.fft(taps)
    assert np.max(np.abs(np.asarray(real, dtype=float) - exact.real)) <= 0.5
    assert np.max(np.abs(np.asarray(imag, dtype=float) - exact.imag)) <= 0.5
    assert real.tolist()[:4] == [22948, 4532, -21547, -11912]
    assert imag.tolist()[:4] == [0, -22783, -8925, 17827]


def test_h_spectrum_keeps_real_tap_conjugate_symmetry_and_fits_q2_14():
    real, imag = h_spectrum_codes()
    for k in range(1, 16):
        assert real[k] == real[16 - k] and imag[k] == -imag[16 - k]
    assert max(abs(value) for value in [*real, *imag]) < 1 << 15


def test_bit_reversed_storage_order():
    assert bit_reversed_indices().tolist() == [0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15]


# Integer FFT engine --------------------------------------------------------


def _random_frames(seed: int, count: int = 32, amplitude: int = 16384):
    rng = np.random.default_rng(seed)
    real = rng.integers(-amplitude, amplitude, size=(count, 16))
    imag = rng.integers(-amplitude, amplitude, size=(count, 16))
    return real, imag


def test_dif_fft_returns_dft_bins_in_bit_reversed_order():
    real, imag = _random_frames(1)
    monitor = ArithmeticMonitor()
    out_real, out_imag = fft16_dif(real, imag, twiddle_codes(), PRODUCTION_POLICY, monitor)
    exact = np.fft.fft(real + 1j * imag, axis=1)[:, bit_reversed_indices()]
    error = np.abs(np.asarray(out_real, dtype=float) + 1j * np.asarray(out_imag, dtype=float) - exact)
    # Twiddle quantization (|e| <= 2^-15) and four RNE stages stay a few LSB.
    assert error.max() < 16
    assert monitor.internal_overflow_count == 0


def test_dit_ifft_inverts_the_dif_fft_up_to_the_factor_16():
    real, imag = _random_frames(2)
    monitor = ArithmeticMonitor()
    twiddles = twiddle_codes()
    spectrum = fft16_dif(real, imag, twiddles, PRODUCTION_POLICY, monitor)
    back_real, back_imag = ifft16_dit(*spectrum, twiddles, PRODUCTION_POLICY, monitor)
    restored = (np.asarray(back_real, dtype=float) + 1j * np.asarray(back_imag, dtype=float)) / 16
    assert np.max(np.abs(restored - (real + 1j * imag))) < 4


def test_overflow_detector_negative_control_full_scale_rotation():
    # Not a candidate gate: an arbitrary full-scale frame outside the QPSK
    # alphabet. A complex twiddle rotation grows a component by up to sqrt(2),
    # so W+s per stage is not a worst-case bound for arbitrary inputs; the
    # monitor must flag it instead of wrapping.
    real = np.zeros((1, 16), dtype=np.int64)
    imag = np.zeros((1, 16), dtype=np.int64)
    real[0, 1], imag[0, 1] = 32767, 32767
    real[0, 9], imag[0, 9] = -32768, -32768
    monitor = ArithmeticMonitor()
    fft16_dif(real, imag, twiddle_codes(), PRODUCTION_POLICY, monitor)
    assert monitor.overflow["fft_stage1"] > 0


def test_monitor_counts_values_outside_the_declared_width():
    monitor = ArithmeticMonitor()
    monitor.check("acc", np.array([1 << 34, -(1 << 34), (1 << 34) - 1], dtype=object), 35)
    assert monitor.overflow["acc"] == 1
    assert monitor.required_width("acc") == 36


# Time model ----------------------------------------------------------------


def test_time_impulse_response_is_the_coefficient_codes():
    result = filter_time_fxp(np.array([1 + 0j]))
    assert result.i_codes.tolist() == [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]
    assert result.q_codes.tolist() == [0] * 8


def test_time_model_is_exact_integer_convolution_on_the_stimulus_alphabet():
    # Inputs are {0, +/-2^14}: every accumulator is a multiple of 2^14, so the
    # final RNE drops only zero bits. This is the arithmetic reason no output
    # tie is reachable in the time domain.
    samples = _FRAMES["canonical"]
    result = filter_time_fxp(samples)
    coefficients = quantize_coefficients().astype(np.int64)
    expected_i = np.convolve(np.rint(samples.real).astype(np.int64), coefficients)
    expected_q = np.convolve(np.rint(samples.imag).astype(np.int64), coefficients)
    assert result.i_codes.tolist() == expected_i.tolist()
    assert result.q_codes.tolist() == expected_q.tolist()
    assert result.monitor.rounding["output_cast"]["inexact"] == 0


def test_time_output_saturates_only_at_the_explicit_output_cast():
    signs = np.sign(load_rrc8_coefficients())[::-1]
    samples = signs * (2.0 - LSB) * (1 + 1j)
    result = filter_time_fxp(samples)
    assert result.monitor.internal_overflow_count == 0
    assert result.monitor.output_saturation_count >= 2
    assert result.i_codes[7] == 32767 and result.q_codes[7] == 32767


# Frequency model -----------------------------------------------------------


def test_frequency_impulse_response_is_within_two_lsb_of_the_coefficients():
    result = filter_frequency_fxp(np.array([1 + 0j]))
    assert result.i_codes.size == 8
    assert np.max(np.abs(result.i_codes - quantize_coefficients().astype(np.int64))) <= 2
    assert np.max(np.abs(result.q_codes)) <= 2


def test_frequency_model_is_not_a_cast_of_the_float_reference(production_frames):
    frame = production_frames["canonical"]
    reference = frame["references"]["frequency"]
    cast_i, _ = quantize(reference.real, 16, 14)
    codes = frame["results"]["frequency"].i_codes
    assert codes.size == 2055
    assert np.count_nonzero(codes != cast_i.astype(np.int64)) > 0


def test_frequency_schedule_covers_257_blocks_and_trims_the_padding_output(production_frames):
    trace = production_frames["canonical"]["results"]["frequency"].trace
    assert [entry["block"] for entry in trace] == [0, 1, 128, 256]
    assert trace[0]["frame_i"][:8] == [0] * 8
    assert trace[-1]["first_output_index"] == 2048 and trace[-1]["valid_outputs"] == 7


def test_traces_agree_with_the_model_outputs(production_frames):
    results = production_frames["canonical"]["results"]
    for entry in results["time"].trace:
        index = entry["output_index"]
        assert entry["partial_sums_i"][-1] >> 14 == entry["output_i"] == results["time"].i_codes[index]
        assert entry["output_q"] == results["time"].q_codes[index]
    for entry in results["frequency"].trace:
        first = entry["first_output_index"]
        valid = entry["valid_outputs"]
        assert entry["output_i"] == results["frequency"].i_codes[first : first + valid].tolist()
        assert entry["output_q"] == results["frequency"].q_codes[first : first + valid].tolist()


@pytest.mark.parametrize(("domain", "positions"), [("time", [0, 7]), ("frequency", [0])])
def test_trace_keeps_only_the_default_positions_a_short_input_has(domain, positions):
    impulse = np.array([1 + 0j])
    traced = run_fxp_model(domain, impulse, trace=True)
    plain = run_fxp_model(domain, impulse)
    key = "output_index" if domain == "time" else "block"
    assert [entry[key] for entry in traced.trace] == positions
    assert traced.i_codes.tolist() == plain.i_codes.tolist()
    assert traced.q_codes.tolist() == plain.q_codes.tolist()


def test_explicit_trace_positions_are_absolute_and_match_the_outputs():
    samples = np.array([1 + 0j, -1 + 1j, 1 - 1j])
    time = filter_time_fxp(samples, trace_indices=(np.int64(9), 2))
    assert [entry["output_index"] for entry in time.trace] == [9, 2]
    for entry in time.trace:
        assert entry["output_i"] == time.i_codes[entry["output_index"]]
        assert entry["output_q"] == time.q_codes[entry["output_index"]]
    frequency = filter_frequency_fxp(samples, trace_blocks=(1,))
    (entry,) = frequency.trace
    assert (entry["block"], entry["first_output_index"], entry["valid_outputs"]) == (1, 8, 2)
    assert entry["output_i"] == frequency.i_codes[8:10].tolist()
    assert entry["output_q"] == frequency.q_codes[8:10].tolist()


@pytest.mark.parametrize(
    ("position", "error"),
    [(-1, ValueError), ("limit", ValueError), (1.0, TypeError), (True, TypeError), (np.bool_(True), TypeError)],
)
@pytest.mark.parametrize(("domain", "limit"), [("time", 10), ("frequency", 2)])
def test_trace_positions_must_be_integers_inside_the_output(domain, limit, position, error):
    # Three samples give 10 outputs and 2 overlap-save blocks. A negative
    # position is refused rather than read as NumPy indexing from the end.
    samples = np.array([1 + 0j, -1 + 1j, 1 - 1j])
    position = limit if isinstance(position, str) else position
    with pytest.raises(error):
        if domain == "time":
            filter_time_fxp(samples, trace_indices=(position,))
        else:
            filter_frequency_fxp(samples, trace_blocks=(position,))


# Production gate preview (canonical gate, sys_corners diagnostic) ---------


@pytest.mark.parametrize("frame_name", list(_FRAMES))
def test_production_q2_14_has_zero_internal_overflow_and_saturation(production_frames, frame_name):
    measurement = production_frames[frame_name]["measurement"]
    for domain in ("time", "frequency"):
        assert measurement[domain]["internal_overflow_count"] == 0
        assert measurement[domain]["output_saturation_count"] == 0


def test_production_q2_14_passes_sqnr_in_both_domains_on_canonical(production_frames):
    frame = production_frames["canonical"]
    measurement = frame["measurement"]
    assert measurement["time"]["sqnr_db"] >= SQNR_MIN_DB
    assert measurement["frequency"]["sqnr_db"] >= SQNR_MIN_DB
    assert measurement["sqnr_cross_db"] >= SQNR_CROSS_MIN_DB
    for domain in ("time", "frequency"):
        decoded = frame["results"][domain].decoded()
        assert split_half_is_stable(frame["references"][domain], decoded)


def test_rne_ties_are_unreachable_at_every_narrowing_point(production_frames):
    # fxp-policy-16 item 7: enumerate the canonical frame plus sys_corners. If a
    # schedule change makes a tie reachable, this fails and the exact-rounding
    # check on that tie becomes a MUST.
    for frame in production_frames.values():
        for domain in ("time", "frequency"):
            for point, counts in frame["measurement"][domain]["rounding"].items():
                assert counts["ties"] == 0, (domain, point)


# Evidence ------------------------------------------------------------------


def _without_provenance(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop("provenance")
    return manifest


def test_evidence_records_policy_freeze_gate_and_trace_hash(evidence):
    manifest = json.loads(evidence.read_text(encoding="utf-8"))
    assert manifest["policy"] == PRODUCTION_POLICY.manifest_fields()
    assert manifest["freeze"]["coefficient_codes"] == [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]
    assert manifest["freeze"]["frequency"]["h_spectrum"]["storage_order"] == "bit_reversed"
    assert set(manifest["frames"]) == {
        "canonical/none",
        *(f"sys_corners/{case}" for case in CORNER_CASES),
    }
    assert manifest["gate_preview"]["passed"] is True
    traces = evidence.with_name(manifest["traces"]["file"])
    assert fxp._sha256_bytes(traces.read_bytes()) == manifest["traces"]["sha256"]


def test_evidence_regeneration_is_byte_identical(evidence, tmp_path):
    again = generate_fxp_evidence(tmp_path)
    assert again.read_bytes() == evidence.read_bytes()
    assert (tmp_path / "traces.json").read_bytes() == evidence.with_name("traces.json").read_bytes()


def test_committed_evidence_is_current(evidence):
    committed = _COMMITTED_EVIDENCE / "evidence_manifest.json"
    assert _without_provenance(committed) == _without_provenance(evidence)
    committed_sources = json.loads(committed.read_text(encoding="utf-8"))["provenance"]["source_sha256"]
    fresh_sources = json.loads(evidence.read_text(encoding="utf-8"))["provenance"]["source_sha256"]
    assert committed_sources == fresh_sources
    assert (_COMMITTED_EVIDENCE / "traces.json").read_bytes() == evidence.with_name("traces.json").read_bytes()


def test_evidence_refuses_tampered_f1_references(tmp_path):
    vectors = tmp_path / "vectors"
    shutil.copytree(Path(fxp._DEFAULT_VECTORS_DIR) / "float_reference", vectors / "float_reference")
    reference = vectors / "float_reference" / "canonical" / "none" / "reference_time.c16.bin"
    data = bytearray(reference.read_bytes())
    data[0] ^= 1
    reference.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="hash does not match"):
        generate_fxp_evidence(tmp_path / "out", vectors_dir=vectors)


def test_cli_accepts_a_diagnostic_width(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["fxp.py", "--output-dir", str(tmp_path), "--width", "10"])
    fxp.main()
    manifest = json.loads((tmp_path / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert manifest["policy"]["W_common"] == 10
    assert manifest["freeze"]["format"] == "Q2.8"
    assert capsys.readouterr().out.strip().endswith("evidence_manifest.json")
