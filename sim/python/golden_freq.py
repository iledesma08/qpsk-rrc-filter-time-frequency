"""Floating-point frequency-domain golden model and evidence generation."""

import argparse
import hashlib
import json
import os
import platform
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import scipy

from golden_time import generate_time_golden
from rrc_coefs import load_rrc8_coefficients
from stimulus import generate_canonical_samples


FFT_LENGTH = 16
HOP_LENGTH = 8
FILTER_LENGTH = 8
_SYMBOL_COUNT = 1024
_RANDOM_SEED = 2026
_RTOL = 1e-10
_ATOL = 1e-12
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "t12-freq-golden"
_DEFAULT_COMPARISON_DIR = Path(__file__).resolve().parent / "artifacts" / "golden_comparison"
_HASH_SERIALIZATION = {
	"algorithm": "SHA-256",
	"array_order": "C",
	"byte_order": "little-endian",
	"samples_dtype": "<c16",
	"coefficients_dtype": "<f8",
}


def _iter_ols_blocks(
	samples: np.ndarray,
	coefficients: np.ndarray,
) -> Iterator[tuple[int, np.ndarray]]:
	"""Yield each forced-50% OLS output block with its causal output index."""
	output_length = samples.size + coefficients.size - 1
	block_count = (output_length + HOP_LENGTH - 1) // HOP_LENGTH
	right_padding = block_count * HOP_LENGTH - samples.size
	padded_input = np.pad(samples, (HOP_LENGTH, right_padding))
	padded_filter = np.pad(coefficients, (0, FFT_LENGTH - FILTER_LENGTH))
	filter_spectrum = np.fft.fft(padded_filter)

	for block in range(block_count):
		frame_start = block * HOP_LENGTH
		frame = padded_input[frame_start : frame_start + FFT_LENGTH]
		spectrum = np.fft.fft(frame) * filter_spectrum
		output_block = np.fft.ifft(spectrum)[FILTER_LENGTH:]
		yield block * HOP_LENGTH, output_block


def filter_frequency_domain(
	samples: np.ndarray,
	coefficients: np.ndarray | None = None,
) -> np.ndarray:
	"""Filter complex samples with the forced-50% overlap-save contract."""
	input_samples = np.asarray(samples, dtype=np.complex128)
	if input_samples.ndim != 1:
		raise ValueError("samples: expected a one-dimensional array")

	if coefficients is None:
		filter_coefficients = load_rrc8_coefficients()
	else:
		filter_coefficients = np.asarray(coefficients, dtype=np.complex128)
	if filter_coefficients.shape != (FILTER_LENGTH,):
		raise ValueError("coefficients: expected eight values")

	output_length = input_samples.size + FILTER_LENGTH - 1
	block_count = (output_length + HOP_LENGTH - 1) // HOP_LENGTH
	output = np.empty(block_count * HOP_LENGTH, dtype=np.complex128)
	for output_start, output_block in _iter_ols_blocks(input_samples, filter_coefficients):
		output[output_start : output_start + HOP_LENGTH] = output_block

	return output[:output_length]


def _generate_frequency_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
	"""Return canonical samples, their coefficients, and the full filtered output."""
	samples = generate_canonical_samples()
	coefficients = load_rrc8_coefficients()
	output = filter_frequency_domain(samples, coefficients)
	return samples, coefficients, output


def generate_frequency_golden() -> np.ndarray:
	"""Return the full causal output for the canonical QPSK sample frame."""
	_, _, output = _generate_frequency_data()
	return output


def _sha256_bytes(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def _canonical_array_bytes(values: np.ndarray, dtype: str) -> bytes:
	return np.asarray(values, dtype=dtype).tobytes(order="C")


def generate_frequency_evidence(
	output_dir: Path = _DEFAULT_OUTPUT_DIR,
	comparison_output_dir: Path = _DEFAULT_COMPARISON_DIR,
) -> Path:
	"""Write canonical comparison plots and a manifest for the float reference."""
	import matplotlib

	matplotlib.use("Agg")
	from matplotlib import pyplot as plt

	samples, coefficients, frequency_output = _generate_frequency_data()
	time_output = generate_time_golden()
	comparison_passed = bool(np.allclose(frequency_output, time_output, rtol=_RTOL, atol=_ATOL))
	absolute_error = np.abs(frequency_output - time_output)
	maximum_absolute_error = float(np.max(absolute_error))
	output_dir = Path(output_dir)
	comparison_output_dir = Path(comparison_output_dir)
	output_dir.mkdir(parents=True, exist_ok=True)
	comparison_output_dir.mkdir(parents=True, exist_ok=True)

	comparison_path = comparison_output_dir / "canonical_time_frequency_comparison.png"
	fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
	indices = np.arange(frequency_output.size)
	axes[0].plot(indices, time_output.real, label="Time golden I", linewidth=1)
	axes[0].plot(indices, frequency_output.real, "--", label="Frequency golden I", linewidth=1)
	axes[0].set_ylabel("I amplitude")
	axes[0].legend()
	axes[1].plot(indices, time_output.imag, label="Time golden Q", linewidth=1)
	axes[1].plot(indices, frequency_output.imag, "--", label="Frequency golden Q", linewidth=1)
	axes[1].set_ylabel("Q amplitude")
	axes[1].legend()
	axes[2].plot(indices, absolute_error, color="black", linewidth=0.8)
	axes[2].set(xlabel="Sample index", ylabel="Absolute error", xlim=(0, len(indices) - 1))
	axes[2].set_ylim(bottom=0)
	fig.suptitle(
		f"Float goldens: max |y_freq - y_time| = {maximum_absolute_error:.3e}; "
		f"rtol={_RTOL:g}, atol={_ATOL:g}"
	)
	for axis in axes:
		axis.grid(alpha=0.25)
	fig.tight_layout()
	fig.savefig(comparison_path, dpi=150)
	plt.close(fig)

	boundary_path = output_dir / "ols_boundaries.png"
	boundary_windows = ((0, 24), (1016, 1040), (2032, len(frequency_output)))
	fig, axes = plt.subplots(3, 1, figsize=(11, 9))
	for axis, (start, stop) in zip(axes, boundary_windows, strict=True):
		window_indices = np.arange(start, stop)
		axis.plot(window_indices, time_output.real[start:stop], "o-", label="Time I", markersize=3)
		axis.plot(window_indices, frequency_output.real[start:stop], ".--", label="Frequency I", markersize=5)
		axis.plot(window_indices, time_output.imag[start:stop], "s-", label="Time Q", markersize=3)
		axis.plot(window_indices, frequency_output.imag[start:stop], "x--", label="Frequency Q", markersize=4)
		for boundary in range(((start // HOP_LENGTH) + 1) * HOP_LENGTH, stop, HOP_LENGTH):
			axis.axvline(boundary - 0.5, color="gray", linestyle=":", linewidth=0.8)
		axis.set(xlim=(start - 0.5, stop - 0.5), ylim=(-1.05, 1.05), ylabel="Amplitude")
		axis.set_title(f"Output samples {start}–{stop - 1}")
		axis.grid(alpha=0.25)
		axis.legend(ncol=4, fontsize="small")
	last_start = 2032
	last_stop = len(frequency_output)
	axes[-1].set(xlim=(last_start - 0.5, last_stop + 0.5), ylim=(-1.05, 1.05))
	axes[-1].axvspan(last_stop - 0.5, last_stop + 0.5, color="lightgray", alpha=0.35, label="Discarded padding")
	axes[-1].axvline(last_stop - 0.5, color="red", linestyle="--", label="Causal output limit")
	axes[-1].legend(ncol=4, fontsize="small")
	axes[-1].set_xlabel("Sample index (vertical dotted lines: hop boundaries every 8 samples)")
	fig.suptitle("Forced-50% OLS boundaries: 2056 scheduled positions, 2055 causal samples retained")
	fig.tight_layout()
	fig.savefig(boundary_path, dpi=150)
	plt.close(fig)

	impulse_path = output_dir / "impulse_response.png"
	impulse_output = filter_frequency_domain(np.array([1 + 0j]), coefficients)
	impulse_indices = np.arange(FILTER_LENGTH)
	fig, axis = plt.subplots(figsize=(9, 4))
	axis.stem(impulse_indices, impulse_output.real, linefmt="C0-", markerfmt="C0o", basefmt="k-", label="Emitted impulse response I")
	axis.stem(impulse_indices, coefficients.real, linefmt="C1--", markerfmt="C1x", basefmt=" ", label="RRC coefficients")
	axis.axvline(3.5, color="black", linestyle=":", label="Group delay: 3.5 samples")
	axis.scatter([3, 4], impulse_output.real[[3, 4]], color="red", zorder=3, label="Equal peaks at indices 3 and 4")
	axis.set(
		xlabel="Sample index (discrete samples, no interpolation)",
		ylabel="Amplitude",
		title="Eight emitted samples match the rrc8-v1 impulse response",
		xticks=impulse_indices,
	)
	axis.grid(alpha=0.25)
	axis.legend()
	fig.tight_layout()
	fig.savefig(impulse_path, dpi=150)
	plt.close(fig)

	plot_paths = {
		"golden_comparison": comparison_path,
		"ols_boundaries": boundary_path,
		"impulse_response": impulse_path,
	}
	plot_names = {
		name: Path(os.path.relpath(path, start=output_dir.parent)).as_posix()
		for name, path in plot_paths.items()
	}
	manifest = {
		"evidence_version": "t12-freq-golden-v1",
		"stage": "floating_point_reference",
		"hash_serialization": _HASH_SERIALIZATION,
		"input": {
			"stimulus_version": "qpsk-stim-15-v1",
			"coefficient_artifact": "rrc8-v1",
			"random_seed": _RANDOM_SEED,
			"symbol_count": _SYMBOL_COUNT,
			"input_samples": int(samples.size),
			"input_samples_sha256": _sha256_bytes(
				_canonical_array_bytes(samples, _HASH_SERIALIZATION["samples_dtype"])
			),
			"coefficients_sha256": _sha256_bytes(
				_canonical_array_bytes(coefficients, _HASH_SERIALIZATION["coefficients_dtype"])
			),
		},
		"schedule": {
			"fft_length": FFT_LENGTH,
			"filter_length": FILTER_LENGTH,
			"hop_length": HOP_LENGTH,
			"overlap_length": FFT_LENGTH - HOP_LENGTH,
			"discard_initial": FILTER_LENGTH,
			"selected_samples_start": FILTER_LENGTH,
			"selected_samples_count": HOP_LENGTH,
			"scheduled_blocks": (frequency_output.size + HOP_LENGTH - 1) // HOP_LENGTH,
			"scheduled_output_positions": ((frequency_output.size + HOP_LENGTH - 1) // HOP_LENGTH) * HOP_LENGTH,
			"fft_convention": {
				"forward": "unscaled",
				"inverse": "1/N normalization applied once by numpy.fft.ifft",
			},
		},
		"window": {
			"output_samples": int(frequency_output.size),
			"valid_start": 0,
			"valid_len": int(frequency_output.size),
			"group_delay_samples": 3.5,
		},
		"comparison": {
			"rtol": _RTOL,
			"atol": _ATOL,
			"max_absolute_error": maximum_absolute_error,
			"time_frequency_allclose": comparison_passed,
		},
		"presentation": {
			"interpolation": "none",
			"boundary_windows_sample_indices": [[start, stop - 1] for start, stop in boundary_windows],
			"axes": {
				"comparison_x": "sample index",
				"comparison_y": "I/Q amplitude and absolute error",
				"boundary_x": "sample index",
				"boundary_y": "amplitude",
				"impulse_x": "sample index",
				"impulse_y": "amplitude",
			},
		},
		"provenance": {
			"golden_time_source_sha256": _sha256_bytes(Path(__file__).with_name("golden_time.py").read_bytes()),
			"golden_frequency_source_sha256": _sha256_bytes(Path(__file__).read_bytes()),
			"evidence_generator": {
				"source": "golden_freq.py:generate_frequency_evidence",
				"sha256": _sha256_bytes(Path(__file__).read_bytes()),
			},
			"versions": {
				"python": platform.python_version(),
				"numpy": np.__version__,
				"scipy": scipy.__version__,
				"matplotlib": matplotlib.__version__,
			},
		},
		"plots": plot_names,
		"plot_sha256": {name: _sha256_bytes(path.read_bytes()) for name, path in plot_paths.items()},
	}
	manifest_path = output_dir / "evidence_manifest.json"
	manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
	return manifest_path


def main() -> None:
	parser = argparse.ArgumentParser(description="Generate the T12 frequency-domain golden evidence")
	parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
	parser.add_argument("--comparison-output-dir", type=Path, default=_DEFAULT_COMPARISON_DIR)
	args = parser.parse_args()
	generate_frequency_evidence(args.output_dir, args.comparison_output_dir)


if __name__ == "__main__":
	main()
