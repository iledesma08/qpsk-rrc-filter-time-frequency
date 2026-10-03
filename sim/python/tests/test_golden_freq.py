"""Contract checks for the forced-50% frequency-domain golden model."""

import numpy as np

from golden_freq import FILTER_LENGTH, HOP_LENGTH, filter_frequency_domain
from golden_time import generate_time_golden
from rrc_coefs import load_rrc8_coefficients
from stimulus import generate_canonical_samples


def _overlap_add(samples, coefficients):
    output_length = samples.size + coefficients.size - 1
    block_count = (output_length + 7) // 8
    padded_samples = np.pad(samples, (0, block_count * 8 - samples.size))
    padded_coefficients = np.pad(coefficients, (0, 16 - coefficients.size))
    filter_spectrum = np.fft.fft(padded_coefficients)
    output = np.zeros(block_count * 8 + 15, dtype=np.complex128)

    for block in range(block_count):
        frame = np.zeros(16, dtype=np.complex128)
        frame[:8] = padded_samples[block * 8 : (block + 1) * 8]
        block_output = np.fft.ifft(np.fft.fft(frame) * filter_spectrum)
        output[block * 8 : block * 8 + 16] += block_output

    return output[:output_length]


def _canonical_overlap_save(samples, coefficients):
    output_length = samples.size + coefficients.size - 1
    block_count = (output_length + 8) // 9
    padded_samples = np.pad(samples, (7, block_count * 9 - samples.size))
    padded_coefficients = np.pad(coefficients, (0, 16 - coefficients.size))
    filter_spectrum = np.fft.fft(padded_coefficients)
    output = np.empty(block_count * 9, dtype=np.complex128)

    for block in range(block_count):
        frame = padded_samples[block * 9 : block * 9 + 16]
        block_output = np.fft.ifft(np.fft.fft(frame) * filter_spectrum)
        output[block * 9 : (block + 1) * 9] = block_output[7:16]

    return output[:output_length]


def _pack_iq(i_values, q_values):
    i_words = np.asarray(i_values, dtype=np.int64) & 0xFFFF
    q_words = np.asarray(q_values, dtype=np.int64) & 0xFFFF
    return ((q_words << 16) | i_words).astype(np.uint32)


def _unpack_iq(words):
    words = np.asarray(words, dtype=np.uint32)
    i_values = (words & 0xFFFF).astype(np.int64)
    q_values = (words >> 16).astype(np.int64)
    i_values[i_values >= 0x8000] -= 0x10000
    q_values[q_values >= 0x8000] -= 0x10000
    return i_values, q_values


def test_forced_50_percent_ols_matches_direct_convolution():
    rng = np.random.default_rng(32)
    samples = rng.normal(size=32) + 1j * rng.normal(size=32)
    coefficients = rng.normal(size=8)

    np.testing.assert_allclose(
        filter_frequency_domain(samples, coefficients),
        np.convolve(samples, coefficients, mode="full"),
        rtol=1e-10,
        atol=1e-12,
    )


def test_forced_ols_selects_each_output_index_once():
    output_length = 32 + FILTER_LENGTH - 1
    block_count = (output_length + HOP_LENGTH - 1) // HOP_LENGTH
    selected_indices = np.concatenate(
        [
            np.arange(block * HOP_LENGTH, (block + 1) * HOP_LENGTH)
            for block in range(block_count)
        ]
    )
    selected_indices = selected_indices[selected_indices < output_length]

    selection_counts = np.bincount(selected_indices, minlength=output_length)

    np.testing.assert_array_equal(selection_counts, np.ones(output_length, dtype=int))


def test_ola_reference_matches_direct_convolution():
    rng = np.random.default_rng(32)
    samples = rng.normal(size=32) + 1j * rng.normal(size=32)
    coefficients = rng.normal(size=8)
    expected = np.convolve(samples, coefficients, mode="full")

    np.testing.assert_allclose(_overlap_add(samples, coefficients), expected, rtol=1e-10, atol=1e-12)


def test_canonical_ols_reference_matches_direct_convolution():
    rng = np.random.default_rng(32)
    samples = rng.normal(size=32) + 1j * rng.normal(size=32)
    coefficients = rng.normal(size=8)
    expected = np.convolve(samples, coefficients, mode="full")

    np.testing.assert_allclose(
        _canonical_overlap_save(samples, coefficients), expected, rtol=1e-10, atol=1e-12
    )


def test_impulse_alignment_preserves_coefficient_order():
    coefficients = load_rrc8_coefficients()

    output = filter_frequency_domain(np.array([1.0 + 0.0j]), coefficients)

    np.testing.assert_allclose(output, coefficients, rtol=1e-10, atol=1e-12)
    assert np.flatnonzero(np.abs(output) == np.max(np.abs(output))).tolist() == [3, 4]


def test_packed_iq_round_trip_preserves_signed_16_bit_words():
    i_values = np.array([-32768, -16384, -1, 0, 1, 16384, 32767])
    q_values = np.array([32767, 16384, 1, 0, -1, -16384, -32768])

    packed = _pack_iq(i_values, q_values)
    unpacked_i, unpacked_q = _unpack_iq(packed)

    np.testing.assert_array_equal(unpacked_i, i_values)
    np.testing.assert_array_equal(unpacked_q, q_values)


def test_canonical_frame_has_full_causal_frequency_output():
    samples = generate_canonical_samples()

    output = filter_frequency_domain(samples)

    assert samples.shape == (2048,)
    assert output.shape == (2055,)
    assert output.dtype == np.complex128


def test_canonical_frame_matches_direct_rrc_convolution():
    samples = generate_canonical_samples()
    coefficients = load_rrc8_coefficients()

    np.testing.assert_allclose(
        filter_frequency_domain(samples, coefficients),
        np.convolve(samples, coefficients, mode="full"),
        rtol=1e-10,
        atol=1e-12,
    )


def test_canonical_time_and_frequency_goldens_match():
    samples = generate_canonical_samples()

    frequency_output = filter_frequency_domain(samples)
    time_output = generate_time_golden()

    assert frequency_output.shape == time_output.shape == (2055,)
    np.testing.assert_allclose(frequency_output, time_output, rtol=1e-10, atol=1e-12)