"""Contract checks for the time-domain float golden and its evidence."""

import hashlib
import json
from pathlib import Path

import numpy as np

import golden_time
from golden_time import _filter_time_domain, _folded_sample_windows, generate_time_evidence, generate_time_golden
from rrc_coefs import load_rrc8_coefficients
from stimulus import generate_canonical_samples


def test_time_golden_emits_the_full_causal_output():
    samples = generate_canonical_samples()
    coefficients = load_rrc8_coefficients()
    output = generate_time_golden()

    assert output.shape == (2055,)
    assert output.dtype == np.complex128
    assert np.all(np.isfinite(output))
    np.testing.assert_array_equal(output, np.convolve(samples, coefficients, mode="full"))


def test_impulse_response_is_the_coefficient_sequence_in_causal_order():
    coefficients = load_rrc8_coefficients()

    output = _filter_time_domain(np.array([1 + 0j], dtype=np.complex128), coefficients)

    np.testing.assert_array_equal(output, coefficients)


def test_impulse_at_last_input_sample_preserves_the_complete_filter_tail():
    coefficients = load_rrc8_coefficients()
    samples = np.zeros(2048, dtype=np.complex128)
    samples[-1] = 1

    output = _filter_time_domain(samples, coefficients)

    assert output.shape == (2055,)
    np.testing.assert_array_equal(output[:-8], np.zeros(2047, dtype=np.complex128))
    np.testing.assert_array_equal(output[-8:], coefficients)


def test_folded_samples_use_exact_natural_grid_indices():
    samples = np.arange(2055, dtype=np.float64).astype(np.complex128)
    samples += 1j * samples

    phase, i_windows, q_windows = _folded_sample_windows(samples)
    symbol_indices = np.arange(64, 960)
    expected_indices = 2 * symbol_indices[:, np.newaxis] + np.arange(1, 7)

    np.testing.assert_array_equal(phase, [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5])
    assert i_windows.shape == q_windows.shape == (896, 6)
    np.testing.assert_array_equal(i_windows, samples[expected_indices].real)
    np.testing.assert_array_equal(q_windows, samples[expected_indices].imag)


def test_evidence_uses_canonical_frame_and_natural_grid(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_hex

    original_subplots = plt.subplots
    captured_axes = []

    def capture_subplots(*args, **kwargs):
        fig, axes = original_subplots(*args, **kwargs)
        captured_axes.append(axes)
        return fig, axes

    monkeypatch.setattr(plt, "subplots", capture_subplots)
    manifest_path = generate_time_evidence(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = generate_canonical_samples()
    coefficients = load_rrc8_coefficients()
    output = generate_time_golden()

    assert manifest["stimulus_version"] == "qpsk-stim-15-v1"
    assert manifest["coefficient_artifact"] == "rrc8-v1"
    assert manifest["symbol_count"] == 1024
    assert manifest["random_seed"] == 2026
    assert manifest["input_samples"] == 2048
    assert manifest["output_samples"] == manifest["valid_len"] == 2055
    assert manifest["valid_start"] == 0
    assert manifest["symbol_center_offset_samples"] == 3.5
    assert manifest["folded_window_count"] == 896
    assert manifest["folded_sample_index_offsets"] == [1, 2, 3, 4, 5, 6]
    assert manifest["folded_sample_offsets"] == [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]
    assert manifest["interpolation"] == "none"
    assert manifest["frequency_units"] == "cycles/symbol"
    assert manifest["folded_series"] == {
        "I": {"color": "#0057B8", "marker": "o", "alpha": 0.75, "markersize": 3.5},
        "Q": {
            "color": "#E65100",
            "marker": "x",
            "alpha": 0.75,
            "markersize": 3.5,
            "markeredgewidth": 0.9,
        },
    }
    assert manifest["plots"] == ["folded_samples_natural_grid.png", "spectrum.png"]
    assert "model_source_sha256" in manifest
    assert "generator_sha256" not in manifest
    assert manifest["model_source_sha256"] == hashlib.sha256(Path(golden_time.__file__).read_bytes()).hexdigest()
    assert manifest["input_samples_sha256"] == hashlib.sha256(samples.tobytes()).hexdigest()
    assert manifest["input_coefficients_sha256"] == hashlib.sha256(coefficients.tobytes()).hexdigest()

    expected_phase, expected_i, expected_q = _folded_sample_windows(output)
    eye_lines = captured_axes[0].lines
    assert len(eye_lines) == 2 * manifest["folded_window_count"] + 1
    for window_index in range(manifest["folded_window_count"]):
        i_line, q_line = eye_lines[2 * window_index : 2 * window_index + 2]
        np.testing.assert_array_equal(i_line.get_xdata(), expected_phase)
        np.testing.assert_array_equal(i_line.get_ydata(), expected_i[window_index])
        np.testing.assert_array_equal(q_line.get_xdata(), expected_phase)
        np.testing.assert_array_equal(q_line.get_ydata(), expected_q[window_index])
    i_line, q_line = eye_lines[:2]
    assert (to_hex(i_line.get_color()), to_hex(q_line.get_color())) == ("#0057b8", "#e65100")
    assert (i_line.get_marker(), q_line.get_marker()) == ("o", "x")
    assert (i_line.get_alpha(), q_line.get_alpha()) == (0.75, 0.75)
    assert (i_line.get_markersize(), q_line.get_markersize()) == (3.5, 3.5)
    assert q_line.get_markeredgewidth() == 0.9
    assert [text.get_text() for text in captured_axes[0].get_legend().get_texts()] == [
        "I samples",
        "Q samples",
        "symbol center between samples",
    ]

    for filename in manifest["plots"]:
        image_path = tmp_path / filename
        assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == manifest["plot_sha256"][filename]
