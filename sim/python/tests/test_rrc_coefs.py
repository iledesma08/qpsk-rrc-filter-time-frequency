"""Contract checks for the fixed float64 RRC coefficient artifact."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from scipy.signal import fftconvolve, freqz

import rrc_coefs
from rrc_coefs import _calculate_rrc8, _rrc_pulse, generate_rrc8_artifact, load_rrc8_coefficients


RAW = [
    0.015468180292133855,
    -0.15684266071530739,
    0.15684266071530747,
    0.97449535840443269,
    0.97449535840443269,
    0.15684266071530747,
    -0.15684266071530739,
    0.015468180292133855,
]
NORMALIZED = [
    0.010942691568693054,
    -0.11095557645481881,
    0.11095557645481886,
    0.68938956882766222,
    0.68938956882766222,
    0.11095557645481886,
    -0.11095557645481881,
    0.010942691568693054,
]
ARTIFACT = Path(__file__).resolve().parents[1] / "artifacts" / "rrc8-v1" / "manifest.json"


def test_rrc_grid_raw_values_and_unit_energy():
    grid, raw, h = _calculate_rrc8()

    np.testing.assert_array_equal(grid, [-1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75])
    np.testing.assert_allclose(raw, RAW, rtol=0, atol=1e-15)
    np.testing.assert_allclose(h, NORMALIZED, rtol=0, atol=1e-15)
    assert grid.dtype == raw.dtype == h.dtype == np.float64
    assert abs(np.sum(raw**2) - 1.9981594171876955) <= 1e-15
    assert abs(np.sum(h**2) - 1) <= 1e-15
    assert np.max(np.abs(h - h[::-1])) <= 1e-15
    assert np.max(np.abs(h)) < 1
    assert np.sum(h) == pytest.approx(1.4006645207927106, rel=0, abs=1e-15)
    assert np.sum(np.abs(h)) == pytest.approx(1.8444868266119858, rel=0, abs=1e-15)


@pytest.mark.parametrize("t,expected", [(0, 1.136619772367581), (0.5, 0.578632469632550), (-0.5, 0.578632469632550)])
def test_rrc_singular_limits_are_finite(t, expected):
    assert np.isfinite(_rrc_pulse(t))
    assert _rrc_pulse(t) == pytest.approx(expected, rel=0, abs=1e-15)


@pytest.mark.parametrize("t", [0.25, 0.75, 1.25, 0.5 - 1e-5, 0.5 + 1e-5])
def test_rrc_ordinary_branch_agrees_with_rearranged_formula(t):
    alpha = 0.5
    u = abs(t)
    expected = (
        np.sin(np.pi * (1 - alpha) * u) / (np.pi * u)
        + (4 * alpha / np.pi) * np.cos(np.pi * (1 + alpha) * u)
    ) / (1 - (4 * alpha * u) ** 2)
    assert _rrc_pulse(t) == pytest.approx(expected, rel=0, abs=1e-11)
    assert _rrc_pulse(-t) == _rrc_pulse(t)


def test_impulse_peaks_and_linear_phase_preserve_half_sample_delay():
    _, _, h = _calculate_rrc8()
    np.testing.assert_array_equal(np.convolve([1.0], h, mode="full"), h)
    assert np.flatnonzero(np.abs(h) == np.max(np.abs(h))).tolist() == [3, 4]

    frequencies = np.array([-1e-4, 1e-4])
    _, response = freqz(h, worN=frequencies)
    phase_slope = (np.angle(response[1]) - np.angle(response[0])) / np.diff(frequencies)[0]
    assert phase_slope == pytest.approx(-3.5, rel=0, abs=1e-10)


def test_direct_and_fft_full_convolution_agree_for_complex_qpsk():
    _, _, h = _calculate_rrc8()
    corners = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j])
    x = corners[np.random.default_rng(2026).integers(0, 4, size=32)]

    np.testing.assert_allclose(
        np.convolve(x, h, mode="full"), fftconvolve(x, h, mode="full"), rtol=1e-10, atol=1e-12
    )


def test_artifact_is_reproducible_and_matches_contract(tmp_path):
    first = generate_rrc8_artifact(tmp_path / "first")
    second = generate_rrc8_artifact(tmp_path / "second")
    assert first.read_bytes() == second.read_bytes() == ARTIFACT.read_bytes()

    manifest = json.loads(first.read_text(encoding="utf-8"))
    assert manifest["artifact_version"] == "rrc8-v1"
    assert manifest["family"] == "root-raised-cosine"
    assert manifest["alpha"] == 0.5
    assert manifest["symbol_period"] == 1.0
    assert manifest["samples_per_symbol"] == 2
    assert manifest["num_coefficients"] == 8
    assert manifest["grid_formula"] == "t[n] = (n-(N-1)/2)/sps"
    assert manifest["normalization"] == "discrete_l2_unit_energy"
    assert manifest["ordering"] == "ascending_time"
    assert manifest["delay_samples"] == 3.5
    assert manifest["input_constellation_components"] == [-1.0, 1.0]
    assert manifest["input_scale_16bit"] == manifest["coefficient_scale_16bit"] == "Q2.14"
    assert manifest["coefficient_scale_sensitivity"] == "Q1.15 (optional phase E)"
    np.testing.assert_allclose(manifest["coefficients_raw_float64"], RAW, rtol=0, atol=1e-15)
    np.testing.assert_allclose(manifest["coefficients_float64"], NORMALIZED, rtol=0, atol=1e-15)
    assert manifest["grid_t_over_T"] == [-1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75]
    assert manifest["quantized_example"] == {
        "width_bits": 16,
        "fractional_bits": 14,
        "rounding_mode": "round_nearest_even",
        "status": "illustrative_not_frozen",
        "values": [179, -1818, 1818, 11295, 11295, 1818, -1818, 179],
    }
    assert "W_common" not in manifest


def test_loader_returns_independent_float64_copies(tmp_path):
    path = generate_rrc8_artifact(tmp_path)
    first = load_rrc8_coefficients(path)
    second = load_rrc8_coefficients()
    assert first.dtype == second.dtype == np.float64
    np.testing.assert_allclose(first, NORMALIZED, rtol=0, atol=1e-15)
    first[0] = 0
    assert second[0] == pytest.approx(NORMALIZED[0])


def test_missing_or_broken_json_never_triggers_a_fallback(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_rrc8_coefficients(missing)
    assert not missing.exists()

    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_rrc8_coefficients(broken)


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_version", "rrc8-v2"),
        ("normalization", None),
        ("num_coefficients", 9),
        ("symbol_period", True),
        ("delay_samples", 4),
        ("grid_t_over_T", [-1.75] * 8),
        ("coefficients_raw_float64", RAW[:7]),
        ("coefficients_float64", [float("nan"), *NORMALIZED[1:]]),
        ("coefficients_float64", [10**400, *NORMALIZED[1:]]),
        ("coefficients_float64", ["0.0", *NORMALIZED[1:]]),
        ("coefficients_float64", [0.0, *NORMALIZED[1:]]),
        ("quantized_example", {"status": "frozen", "values": [0] * 8}),
    ],
)
def test_loader_rejects_invalid_artifacts(tmp_path, field, value):
    artifact = generate_rrc8_artifact(tmp_path)
    manifest = json.loads(artifact.read_text(encoding="utf-8"))
    manifest[field] = value
    artifact.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        load_rrc8_coefficients(artifact)


def test_loader_rejects_incorrect_derived_integer(tmp_path):
    artifact = generate_rrc8_artifact(tmp_path)
    manifest = json.loads(artifact.read_text(encoding="utf-8"))
    manifest["quantized_example"]["values"][0] = 180
    artifact.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="quantized_example"):
        load_rrc8_coefficients(artifact)


def test_cli_generates_headless_plots_and_reproducible_evidence(tmp_path):
    directories = [tmp_path / "first", tmp_path / "second"]
    for directory in directories:
        subprocess.run(
            [sys.executable, str(Path(rrc_coefs.__file__)), "--output-dir", str(directory)],
            check=True,
            capture_output=True,
            text=True,
        )

    first, second = directories
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert (first / "evidence_manifest.json").read_bytes() == (second / "evidence_manifest.json").read_bytes()
    evidence = json.loads((first / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert evidence["artifact_version"] == "rrc8-v1"
    assert evidence["plot_seed"] == 2026
    assert evidence["plot_symbol_count"] == 1024
    assert (evidence["crop_symbol_start"], evidence["crop_symbol_stop"]) == (64, 960)
    assert evidence["eye_window_count"] == 896
    assert evidence["plot_stimulus"] == "visualization_only_not_T11"
    assert evidence["input_constellation"] == "+/-1 +/- j"
    assert evidence["symbol_map"] == "0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j"
    assert evidence["samples_per_symbol"] == 2
    assert evidence["response_points"] == 4096
    assert evidence["delay_samples"] == 3.5
    assert evidence["interpolation"] == "none"
    assert evidence["spectrum_reference"] == "normalized_rrc8_magnitude_on_signal_fft_bins"
    assert set(evidence["versions"]) == {"numpy", "scipy", "matplotlib"}
    assert evidence["plots"] == ["coefs_stem.png", "freqz_4096.png", "qpsk_filter_views.png"]
    assert not (first / "eye_spectrum.png").exists()
    expected_source_hash = hashlib.sha256(Path(rrc_coefs.__file__).read_bytes()).hexdigest()
    assert evidence["generator_sha256"] == expected_source_hash

    retained = json.loads((ARTIFACT.parent / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert {key: value for key, value in retained.items() if key != "plot_sha256"} == {
        key: value for key, value in evidence.items() if key != "plot_sha256"
    }
    assert retained["plot_sha256"] == evidence["plot_sha256"]
    for filename in evidence["plots"]:
        path = first / filename
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert plt.imread(path).size > 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["plot_sha256"][filename]
        retained_path = ARTIFACT.parent / filename
        assert retained_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert hashlib.sha256(retained_path.read_bytes()).hexdigest() == retained["plot_sha256"][filename]
