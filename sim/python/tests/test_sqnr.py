"""Checks for the complex SQNR measurement (ADR-0005, fxp-policy-16 D6)."""

import math

import numpy as np
import pytest

from sqnr import (
    SQNR_CROSS_MIN_DB,
    SQNR_MIN_DB,
    split_half_is_stable,
    split_half_sqnr_db,
    sqnr_cross_db,
    sqnr_db,
)


def test_thresholds_match_the_contract():
    assert SQNR_MIN_DB == 40.0
    assert SQNR_CROSS_MIN_DB == pytest.approx(33.9794, abs=1e-4)


def test_sqnr_aggregates_i_and_q_power():
    reference = np.array([1 + 1j, -1 - 1j, 1 - 1j, -1 + 1j])
    fxp = reference + np.array([0.01, 0.01j, -0.01, -0.01j])
    # Signal power 8, noise power 4e-4.
    assert sqnr_db(reference, fxp) == pytest.approx(10 * math.log10(8 / 4e-4))


def test_one_percent_rms_error_is_exactly_forty_db():
    reference = np.ones(2055, dtype=np.complex128)
    assert sqnr_db(reference, reference * 1.01) == pytest.approx(40.0)


def test_error_free_output_is_infinite():
    reference = np.array([0.5 + 0.25j, -0.75j])
    assert sqnr_db(reference, reference.copy()) == math.inf


def test_cross_domain_sqnr_uses_the_float_reference_as_signal():
    reference = np.full(4, 2 + 0j)
    time_fxp = reference + 0.02
    frequency_fxp = reference - 0.02
    # Noise is the time/frequency difference (0.04), not either domain error.
    assert sqnr_cross_db(reference, time_fxp, frequency_fxp) == pytest.approx(10 * math.log10(4 / 0.04**2))


def test_cross_domain_bound_follows_from_two_passing_domains():
    rng = np.random.default_rng(7)
    reference = rng.normal(size=2055) + 1j * rng.normal(size=2055)
    rms = math.sqrt(np.mean(np.abs(reference) ** 2))
    error = 0.01 * rms
    # Worst case: equal and opposite errors at exactly the 40 dB limit.
    cross = sqnr_cross_db(reference, reference + error, reference - error)
    assert sqnr_db(reference, reference + error) == pytest.approx(40.0)
    assert cross == pytest.approx(SQNR_CROSS_MIN_DB)


@pytest.mark.parametrize(
    ("reference", "fxp"),
    [
        (np.ones(4), np.ones(3)),
        (np.ones((2, 2)), np.ones((2, 2))),
        (np.array([]), np.array([])),
        (np.array([1.0, np.nan]), np.ones(2)),
    ],
)
def test_sqnr_rejects_mismatched_or_invalid_windows(reference, fxp):
    with pytest.raises(ValueError):
        sqnr_db(reference, fxp)


def test_sqnr_rejects_zero_reference_power():
    with pytest.raises(ValueError, match="signal power"):
        sqnr_db(np.zeros(4), np.ones(4))


def test_cross_domain_sqnr_rejects_different_windows():
    with pytest.raises(ValueError):
        sqnr_cross_db(np.ones(4), np.ones(4), np.ones(5))


def test_split_half_uses_the_two_halves_of_the_window():
    reference = np.ones(2055, dtype=np.complex128)
    fxp = reference.copy()
    fxp[:1027] *= 1.01
    fxp[1027:] *= 1.001
    first, second = split_half_sqnr_db(reference, fxp)
    assert first == pytest.approx(40.0)
    assert second == pytest.approx(60.0)
    assert not split_half_is_stable(reference, fxp)


def test_split_half_is_stable_for_uniform_error():
    reference = np.ones(2055, dtype=np.complex128)
    assert split_half_is_stable(reference, reference * 1.01)
    assert split_half_is_stable(reference, reference.copy())
