"""Float64 coefficients for the fixed eight-tap root-raised-cosine filter."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import scipy
from scipy.signal import freqz


_ALPHA = 0.5
_SYMBOL_PERIOD = 1.0
_SAMPLES_PER_SYMBOL = 2
_NUM_COEFFICIENTS = 8
_ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "rrc8-v1" / "manifest.json"
_ARTIFACT_FIELDS = {
    "artifact_version": "rrc8-v1",
    "family": "root-raised-cosine",
    "alpha": 0.5,
    "symbol_period": 1.0,
    "samples_per_symbol": 2,
    "num_coefficients": 8,
    "grid_formula": "t[n] = (n-(N-1)/2)/sps",
    "normalization": "discrete_l2_unit_energy",
    "ordering": "ascending_time",
    "delay_samples": 3.5,
    "input_constellation_components": [-1.0, 1.0],
    "input_scale_16bit": "Q2.14",
    "coefficient_scale_16bit": "Q2.14",
    "coefficient_scale_sensitivity": "Q1.15 (optional phase E)",
}


def _rrc_pulse(t: float) -> float:
    """Evaluate the continuous RRC pulse, including its removable singularities."""
    u = abs(t) / _SYMBOL_PERIOD
    if u == 0.0:
        return (1 + _ALPHA * (4 / math.pi - 1)) / _SYMBOL_PERIOD
    if u == 1 / (4 * _ALPHA):
        angle = math.pi / (4 * _ALPHA)
        return _ALPHA / (_SYMBOL_PERIOD * math.sqrt(2)) * (
            (1 + 2 / math.pi) * math.sin(angle)
            + (1 - 2 / math.pi) * math.cos(angle)
        )

    numerator = math.sin(math.pi * u * (1 - _ALPHA)) + 4 * _ALPHA * u * math.cos(
        math.pi * u * (1 + _ALPHA)
    )
    denominator = math.pi * u * (1 - (4 * _ALPHA * u) ** 2)
    return numerator / (_SYMBOL_PERIOD * denominator)


def _calculate_rrc8() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ascending-time grid, raw pulse values and unit-energy coefficients."""
    grid = (np.arange(_NUM_COEFFICIENTS, dtype=np.float64) - 3.5) / _SAMPLES_PER_SYMBOL
    raw = np.fromiter((_rrc_pulse(t) for t in grid), dtype=np.float64, count=_NUM_COEFFICIENTS)
    normalized = raw / np.linalg.norm(raw)
    return grid, raw, normalized


def generate_rrc8_artifact(output_dir: Path) -> Path:
    """Write the canonical float64 artifact and an illustrative Q2.14 example."""
    grid, raw, coefficients = _calculate_rrc8()
    example = np.rint(coefficients * (1 << 14)).astype(np.int64)
    if np.any((example < -(1 << 15)) | (example >= (1 << 15))):
        raise ValueError("quantized_example: coefficient outside signed 16-bit range")

    manifest = {
        **_ARTIFACT_FIELDS,
        "grid_t_over_T": grid.tolist(),
        "coefficients_raw_float64": raw.tolist(),
        "coefficients_float64": coefficients.tolist(),
        "quantized_example": {
            "width_bits": 16,
            "fractional_bits": 14,
            "rounding_mode": "round_nearest_even",
            "status": "illustrative_not_frozen",
            "values": example.tolist(),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path


def _float_vector(manifest: dict, field: str) -> np.ndarray:
    values = manifest.get(field)
    if (
        not isinstance(values, list)
        or len(values) != _NUM_COEFFICIENTS
        or any(type(value) not in (int, float) for value in values)
    ):
        raise ValueError(f"{field}: expected eight finite numbers")
    try:
        result = np.asarray(values, dtype=np.float64)
    except (OverflowError, ValueError, TypeError) as exc:
        raise ValueError(f"{field}: expected eight finite numbers") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{field}: expected eight finite numbers")
    return result


def load_rrc8_coefficients(artifact_path: Path | None = None) -> np.ndarray:
    """Read a validated copy of the canonical coefficients without a fallback."""
    path = _ARTIFACT_PATH if artifact_path is None else artifact_path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest: expected an object")

    for field, expected in _ARTIFACT_FIELDS.items():
        actual = manifest.get(field)
        if (
            type(actual) is not type(expected)
            or actual != expected
            or (isinstance(expected, list) and any(type(item) is not type(ref) for item, ref in zip(actual, expected)))
        ):
            raise ValueError(f"{field}: does not match rrc8-v1")

    grid = _float_vector(manifest, "grid_t_over_T")
    raw = _float_vector(manifest, "coefficients_raw_float64")
    coefficients = _float_vector(manifest, "coefficients_float64")
    expected_grid, expected_raw, expected_coefficients = _calculate_rrc8()
    for field, actual, expected in (
        ("grid_t_over_T", grid, expected_grid),
        ("coefficients_raw_float64", raw, expected_raw),
        ("coefficients_float64", coefficients, expected_coefficients),
    ):
        if not np.allclose(actual, expected, rtol=0, atol=1e-15):
            raise ValueError(f"{field}: does not match the RRC formula")
    if abs(np.sum(coefficients**2) - 1) > 1e-15:
        raise ValueError("coefficients_float64: energy is not one")

    example = manifest.get("quantized_example")
    if not isinstance(example, dict) or any(
        example.get(field) != expected
        for field, expected in (
            ("width_bits", 16),
            ("fractional_bits", 14),
            ("rounding_mode", "round_nearest_even"),
            ("status", "illustrative_not_frozen"),
        )
    ):
        raise ValueError("quantized_example: invalid format or status")
    values = example.get("values")
    if (
        not isinstance(values, list)
        or len(values) != _NUM_COEFFICIENTS
        or any(type(value) is not int for value in values)
        or values != np.rint(coefficients * (1 << 14)).astype(np.int64).tolist()
    ):
        raise ValueError("quantized_example: integers do not match float64 coefficients")

    return coefficients.copy()


def _write_evidence(output_dir: Path, grid: np.ndarray, raw: np.ndarray, h: np.ndarray) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    times = np.linspace(-2, 2, 1001)
    curve = np.fromiter((_rrc_pulse(t) for t in times), dtype=np.float64) / np.linalg.norm(raw)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(times, curve, label="Continuous RRC / finite-tap L2 norm")
    ax.stem(grid, h, linefmt="C1-", markerfmt="C1o", basefmt="k-", label="8 coefficients")
    ax.set(xlabel="t/T", ylabel="Amplitude", title="rrc8-v1: unit-energy coefficients, D=3.5 samples")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "coefs_stem.png", dpi=150)
    plt.close(fig)

    frequencies, response = freqz(h, worN=4096, whole=True, fs=_SAMPLES_PER_SYMBOL)
    frequencies = np.where(frequencies >= 1, frequencies - 2, frequencies)
    order = np.argsort(frequencies)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(frequencies[order], 20 * np.log10(np.maximum(np.abs(response[order]), 1e-12)), label="8-tap FIR")
    for edge, label in ((0.25, "Ideal passband edge"), (0.75, "Ideal stopband edge")):
        ax.axvline(-edge, linestyle="--", color="C1" if edge == 0.25 else "C2", alpha=0.7)
        ax.axvline(edge, linestyle="--", color="C1" if edge == 0.25 else "C2", alpha=0.7, label=label)
    ax.set(xlim=(-1, 1), xlabel="Frequency (cycles/symbol)", ylabel="Magnitude (dB)", title="rrc8-v1: freqz, 4096 points")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "freqz_4096.png", dpi=150)
    plt.close(fig)

    corners = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j])
    symbols = corners[np.random.default_rng(2026).integers(0, 4, size=1024)]
    samples = np.zeros(2 * len(symbols), dtype=np.complex128)
    samples[::2] = symbols
    filtered = np.convolve(samples, h, mode="full")

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), layout="constrained")
    first = 2 * 64
    shown = np.arange(first, first + 32)
    axes[0].plot(shown / 2, filtered[shown].real, ".", label="I samples")
    axes[0].plot(shown / 2, filtered[shown].imag, ".", label="Q samples")
    axes[0].axvline((first + 3.5) / 2, color="black", linestyle="--", label="delayed symbol center: 2k+3.5 samples")
    axes[0].set(xlabel="Time (symbol periods; samples spaced by T/2)", ylabel="Amplitude", title="Natural sample grid, D=3.5 samples")
    axes[0].legend()

    eye_window_count = 0
    for k in range(64, 960):
        indices = np.arange(2 * k + 1, 2 * k + 7)
        phase = indices - (2 * k + 3.5)
        axes[1].plot(phase, filtered[indices].real, ".", color="C0", alpha=0.02)
        axes[1].plot(phase, filtered[indices].imag, ".", color="C1", alpha=0.02)
        eye_window_count += 1
    axes[1].axvline(0, color="black", linestyle="--", label="symbol center between sample instants")
    axes[1].set(xlabel="Sample offset from 2k+3.5 (no interpolation)", ylabel="I (blue) / Q (orange)", title="Folded QPSK samples (no interpolation)")
    axes[1].legend()

    interior = filtered[first : 2 * 960]
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(interior)))
    frequency = np.fft.fftshift(np.fft.fftfreq(len(interior), d=0.5))
    signal_spectrum_db = 20 * np.log10(np.maximum(spectrum / spectrum.max(), 1e-12))
    filter_response = freqz(h, worN=frequency, fs=_SAMPLES_PER_SYMBOL)[1]
    filter_magnitude = np.abs(filter_response)
    filter_response_db = 20 * np.log10(np.maximum(filter_magnitude / filter_magnitude.max(), 1e-12))
    axes[2].plot(frequency, signal_spectrum_db, label="Filtered QPSK signal")
    axes[2].plot(frequency, filter_response_db, "--", label="8-tap RRC response (shape reference)")
    axes[2].set(xlim=(-1, 1), ylim=(-75, 5), xlabel="Frequency (cycles/symbol)", ylabel="Relative magnitude (dB)", title="Signal spectrum compared with filter response")
    axes[2].legend()
    fig.suptitle("T10 plot-only QPSK, seed 2026 (not T11 canonical stimulus)")
    fig.savefig(output_dir / "qpsk_filter_views.png", dpi=150)
    plt.close(fig)

    evidence = {
        "artifact_version": "rrc8-v1",
        "plot_seed": 2026,
        "plot_symbol_count": 1024,
        "crop_symbol_start": 64,
        "crop_symbol_stop": 960,
        "eye_window_count": eye_window_count,
        "plot_stimulus": "visualization_only_not_T11",
        "input_constellation": "+/-1 +/- j",
        "symbol_map": "0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j",
        "samples_per_symbol": 2,
        "response_points": 4096,
        "delay_samples": 3.5,
        "interpolation": "none",
        "spectrum_reference": "normalized_rrc8_magnitude_on_signal_fft_bins",
        "plots": ["coefs_stem.png", "freqz_4096.png", "qpsk_filter_views.png"],
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "plot_sha256": {
            name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
            for name in ("coefs_stem.png", "freqz_4096.png", "qpsk_filter_views.png")
        },
        "versions": {"numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__},
    }
    (output_dir / "evidence_manifest.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the rrc8-v1 artifact and plot evidence")
    parser.add_argument("--output-dir", type=Path, default=_ARTIFACT_PATH.parent)
    args = parser.parse_args()
    generate_rrc8_artifact(args.output_dir)
    _write_evidence(args.output_dir, *_calculate_rrc8())
