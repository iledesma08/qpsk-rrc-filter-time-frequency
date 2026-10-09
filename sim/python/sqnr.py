"""Complex SQNR measurement over the full causal output window (ADR-0005).

``SQNR = 10 log10(sum|y_float|^2 / sum|y_float - y_fxp|^2)`` aggregates I and Q
power. The cross-domain SQNR keeps the common float reference as signal power
and uses the difference between the two decoded FXP outputs as noise
(``fxp-policy-16.md`` cross-domain amendment). Callers pass arrays on the same
absolute sample indices; nothing here shifts, trims or pads them.
"""

import math

import numpy as np


SQNR_MIN_DB = 40.0
SQNR_CROSS_MIN_DB = SQNR_MIN_DB - 20 * math.log10(2)
SPLIT_HALF_TOLERANCE_DB = 0.5


def _as_window(name: str, values: np.ndarray) -> np.ndarray:
    window = np.asarray(values, dtype=np.complex128)
    if window.ndim != 1 or window.size == 0:
        raise ValueError(f"{name}: expected a non-empty one-dimensional array")
    if not np.all(np.isfinite(window)):
        raise ValueError(f"{name}: expected finite samples")
    return window


def _ratio_db(reference: np.ndarray, error: np.ndarray) -> float:
    signal_power = float(np.sum(np.abs(reference) ** 2))
    if signal_power == 0:
        raise ValueError("reference: signal power is zero")
    noise_power = float(np.sum(np.abs(error) ** 2))
    if noise_power == 0:
        return math.inf
    return 10 * math.log10(signal_power / noise_power)


def sqnr_db(reference: np.ndarray, fxp: np.ndarray) -> float:
    """Return the complex SQNR of ``fxp`` against the float ``reference``."""
    reference_window = _as_window("reference", reference)
    fxp_window = _as_window("fxp", fxp)
    if fxp_window.shape != reference_window.shape:
        raise ValueError("fxp: expected the same window as the reference")
    return _ratio_db(reference_window, reference_window - fxp_window)


def sqnr_cross_db(reference: np.ndarray, time_fxp: np.ndarray, frequency_fxp: np.ndarray) -> float:
    """Return the cross-domain SQNR between the time and frequency FXP outputs."""
    reference_window = _as_window("reference", reference)
    time_window = _as_window("time_fxp", time_fxp)
    frequency_window = _as_window("frequency_fxp", frequency_fxp)
    if time_window.shape != reference_window.shape or frequency_window.shape != reference_window.shape:
        raise ValueError("time_fxp/frequency_fxp: expected the same window as the reference")
    return _ratio_db(reference_window, time_window - frequency_window)


def split_half_sqnr_db(reference: np.ndarray, fxp: np.ndarray) -> tuple[float, float]:
    """Return the SQNR of the first and second half of the window (fxp-policy D6)."""
    reference_window = _as_window("reference", reference)
    fxp_window = _as_window("fxp", fxp)
    if fxp_window.shape != reference_window.shape:
        raise ValueError("fxp: expected the same window as the reference")
    middle = reference_window.size // 2
    return (
        sqnr_db(reference_window[:middle], fxp_window[:middle]),
        sqnr_db(reference_window[middle:], fxp_window[middle:]),
    )


def split_half_is_stable(
    reference: np.ndarray,
    fxp: np.ndarray,
    tolerance_db: float = SPLIT_HALF_TOLERANCE_DB,
) -> bool:
    """Return whether both halves stay within ``tolerance_db`` of the full-window SQNR.

    Infinite values (no quantization error) are stable only against each other.
    """
    full = sqnr_db(reference, fxp)
    for half in split_half_sqnr_db(reference, fxp):
        if math.isinf(full) or math.isinf(half):
            if full != half:
                return False
        elif abs(half - full) > tolerance_db:
            return False
    return True
