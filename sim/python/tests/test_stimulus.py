"""Contract checks for the canonical deterministic QPSK stimulus."""

import numpy as np

from stimulus import generate_canonical_samples


def test_canonical_frame_has_expected_length_and_complex_dtype():
    samples = generate_canonical_samples()

    assert samples.shape == (2048,)
    assert samples.dtype == np.complex128


def test_first_40_symbols_match_all_documented_edge_patterns():
    expected_symbols = np.array(
        [
            1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j, 1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j,
            1 + 1j, -1 - 1j, 1 + 1j, -1 - 1j, 1 + 1j, -1 - 1j, 1 + 1j, -1 - 1j,
            1 + 1j, -1 + 1j, 1 + 1j, -1 + 1j, 1 + 1j, -1 + 1j, 1 + 1j, -1 + 1j,
            1 + 1j, 1 - 1j, 1 + 1j, 1 - 1j, 1 + 1j, 1 - 1j, 1 + 1j, 1 - 1j,
            1 + 1j, 1 + 1j, 1 + 1j, 1 + 1j, 1 + 1j, 1 + 1j, 1 + 1j, 1 + 1j,
        ],
        dtype=np.complex128,
    )

    np.testing.assert_array_equal(generate_canonical_samples()[::2][:40], expected_symbols)


def test_seeded_tail_uses_contract_gray_mapping_and_regenerates_identically():
    first = generate_canonical_samples()
    second = generate_canonical_samples()
    indices = np.random.default_rng(2026).integers(0, 4, size=984)
    corners = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], dtype=np.complex128)

    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first[80::2], corners[indices])


def test_symbols_preserve_unnormalized_corner_energy():
    symbols = generate_canonical_samples()[::2]

    np.testing.assert_allclose(np.abs(symbols) ** 2, 2.0, rtol=0, atol=1e-15)


def test_zero_insertion_places_symbols_at_even_indices_and_zeros_at_odd_indices():
    samples = generate_canonical_samples()

    assert np.all(samples[1::2] == 0)
    assert np.all(np.isin(samples[::2], [1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j]))
