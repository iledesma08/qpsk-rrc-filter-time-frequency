"""Floating-point frequency-domain golden model."""

import numpy as np

from rrc_coefs import load_rrc8_coefficients


FFT_LENGTH = 16
HOP_LENGTH = 8
FILTER_LENGTH = 8


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
		filter_coefficients = np.asarray(coefficients, dtype=np.float64)
	if filter_coefficients.shape != (FILTER_LENGTH,):
		raise ValueError("coefficients: expected eight values")

	output_length = input_samples.size + FILTER_LENGTH - 1
	block_count = (output_length + HOP_LENGTH - 1) // HOP_LENGTH
	right_padding = block_count * HOP_LENGTH - input_samples.size
	padded_input = np.pad(input_samples, (HOP_LENGTH, right_padding))
	padded_filter = np.pad(filter_coefficients, (0, FFT_LENGTH - FILTER_LENGTH))
	filter_spectrum = np.fft.fft(padded_filter)
	output = np.empty(block_count * HOP_LENGTH, dtype=np.complex128)

	for block in range(block_count):
		frame_start = block * HOP_LENGTH
		frame = padded_input[frame_start : frame_start + FFT_LENGTH]
		spectrum = np.fft.fft(frame) * filter_spectrum
		output_start = block * HOP_LENGTH
		output[output_start : output_start + HOP_LENGTH] = np.fft.ifft(spectrum)[FILTER_LENGTH:]

	return output[:output_length]
