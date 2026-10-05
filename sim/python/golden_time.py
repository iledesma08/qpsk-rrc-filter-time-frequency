"""Floating-point time-domain golden model and evidence generation."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy

from rrc_coefs import load_rrc8_coefficients
from stimulus import generate_canonical_samples


_SYMBOL_COUNT = 1024
_SAMPLES_PER_SYMBOL = 2
_SYMBOL_CENTER_OFFSET = 3.5
_CROP_SYMBOL_START = 64
_CROP_SYMBOL_STOP = 960
_FOLDED_I_COLOR = "#0057B8"
_FOLDED_Q_COLOR = "#E65100"
_FOLDED_ALPHA = 0.75
_FOLDED_MARKER_SIZE = 3.5
_FOLDED_MARKER_EDGE_WIDTH = 0.9
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "t11-time-golden"
_HASH_SERIALIZATION = {
    "algorithm": "SHA-256",
    "array_order": "C",
    "byte_order": "little-endian",
    "samples_dtype": "<c16",
    "coefficients_dtype": "<f8",
}


def _array_sha256(values: np.ndarray, dtype: str) -> str:
    canonical_values = np.asarray(values, dtype=dtype)
    return hashlib.sha256(canonical_values.tobytes(order="C")).hexdigest()


def _filter_time_domain(samples: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    """Apply the causal FIR and retain its complete linear-convolution tail."""
    return np.convolve(samples, coefficients, mode="full")


def _generate_time_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return canonical samples, their coefficients, and the full filtered output."""
    samples = generate_canonical_samples()
    coefficients = load_rrc8_coefficients()
    output = _filter_time_domain(samples, coefficients)
    return samples, coefficients, output


def generate_time_golden() -> np.ndarray:
    """Return the full causal output for the canonical QPSK sample frame."""
    _, _, output = _generate_time_data()
    return output


def _folded_sample_windows(output: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return exact sample offsets and I/Q windows without interpolation."""
    symbol_indices = np.arange(_CROP_SYMBOL_START, _CROP_SYMBOL_STOP)
    sample_offsets = np.arange(1, 7)
    sample_indices = 2 * symbol_indices[:, np.newaxis] + sample_offsets
    phase = sample_offsets - _SYMBOL_CENTER_OFFSET
    return phase, output[sample_indices].real, output[sample_indices].imag


def generate_time_evidence(output_dir: Path) -> Path:
    """Write folded sample and spectrum plots plus their evidence manifest."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    samples, coefficients, output = _generate_time_data()
    output_dir.mkdir(parents=True, exist_ok=True)

    folded_samples_path = output_dir / "folded_samples_natural_grid.png"
    phase, i_windows, q_windows = _folded_sample_windows(output)
    fig, ax = plt.subplots(figsize=(9, 5))
    for window_index, (i_samples, q_samples) in enumerate(zip(i_windows, q_windows, strict=True)):
        first_window = window_index == 0
        ax.plot(
            phase,
            i_samples,
            linestyle="None",
            marker="o",
            color=_FOLDED_I_COLOR,
            alpha=_FOLDED_ALPHA,
            markersize=_FOLDED_MARKER_SIZE,
            label="I samples" if first_window else "_nolegend_",
        )
        ax.plot(
            phase,
            q_samples,
            linestyle="None",
            marker="x",
            color=_FOLDED_Q_COLOR,
            alpha=_FOLDED_ALPHA,
            markersize=_FOLDED_MARKER_SIZE,
            markeredgewidth=_FOLDED_MARKER_EDGE_WIDTH,
            label="Q samples" if first_window else "_nolegend_",
        )
    ax.axvline(0, color="black", linestyle="--", label="symbol center between samples")
    ax.set(
        xlabel="Sample offset from 2k+3.5 (no interpolation)",
        ylabel="I (blue circles) / Q (orange crosses)",
        title="Canonical QPSK samples folded around symbol centers",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(folded_samples_path, dpi=150)
    plt.close(fig)

    spectrum_path = output_dir / "spectrum.png"
    sample_start = _CROP_SYMBOL_START * _SAMPLES_PER_SYMBOL
    sample_stop = _CROP_SYMBOL_STOP * _SAMPLES_PER_SYMBOL
    interior = output[sample_start:sample_stop]
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(interior)))
    frequency = np.fft.fftshift(np.fft.fftfreq(len(interior), d=1 / _SAMPLES_PER_SYMBOL))
    spectrum_db = 20 * np.log10(np.maximum(spectrum / spectrum.max(), 1e-12))

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(frequency, spectrum_db, label="filtered canonical QPSK")
    ax.set(
        xlim=(-1, 1),
        ylim=(-75, 5),
        xlabel="Frequency (cycles/symbol)",
        ylabel="Relative magnitude (dB)",
        title="Canonical QPSK spectrum on the natural sample grid",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(spectrum_path, dpi=150)
    plt.close(fig)

    plot_names = [folded_samples_path.name, spectrum_path.name]
    manifest = {
        "stimulus_version": "qpsk-stim-15-v1",
        "coefficient_artifact": "rrc8-v1",
        "symbol_count": _SYMBOL_COUNT,
        "random_seed": 2026,
        "input_samples": len(samples),
        "output_samples": len(output),
        "valid_start": 0,
        "valid_len": len(output),
        "symbol_center_offset_samples": _SYMBOL_CENTER_OFFSET,
        "crop_symbol_start": _CROP_SYMBOL_START,
        "crop_symbol_stop": _CROP_SYMBOL_STOP,
        "folded_window_count": len(i_windows),
        "folded_sample_index_offsets": list(range(1, 7)),
        "folded_sample_offsets": phase.tolist(),
        "interpolation": "none",
        "frequency_units": "cycles/symbol",
        "folded_series": {
            "I": {
                "color": _FOLDED_I_COLOR,
                "marker": "o",
                "alpha": _FOLDED_ALPHA,
                "markersize": _FOLDED_MARKER_SIZE,
            },
            "Q": {
                "color": _FOLDED_Q_COLOR,
                "marker": "x",
                "alpha": _FOLDED_ALPHA,
                "markersize": _FOLDED_MARKER_SIZE,
                "markeredgewidth": _FOLDED_MARKER_EDGE_WIDTH,
            },
        },
        "plots": plot_names,
        "hash_serialization": _HASH_SERIALIZATION,
        "model_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_samples_sha256": _array_sha256(samples, _HASH_SERIALIZATION["samples_dtype"]),
        "input_coefficients_sha256": _array_sha256(coefficients, _HASH_SERIALIZATION["coefficients_dtype"]),
        "plot_sha256": {
            name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
            for name in plot_names
        },
        "versions": {"numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__},
    }
    manifest_path = output_dir / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the T11 time-domain golden evidence")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    generate_time_evidence(args.output_dir)


if __name__ == "__main__":
    main()
