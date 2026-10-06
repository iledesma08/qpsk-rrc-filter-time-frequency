"""Canonical deterministic QPSK stimulus frame and ``sys_corners`` frames."""

import numpy as np


_SYMBOL_COUNT = 1024
_SAMPLES_PER_SYMBOL = 2
_PERTURBATION_INDEX = 512

CORNER_CASES = ("corner_repeat", "max_alternation", "single_symbol_perturbation")


def _zero_insert(symbols: np.ndarray) -> np.ndarray:
    """Place symbols at even sample indices and zeros at odd indices."""
    samples = np.zeros(_SAMPLES_PER_SYMBOL * symbols.size, dtype=np.complex128)
    samples[::_SAMPLES_PER_SYMBOL] = symbols
    return samples


def generate_canonical_samples() -> np.ndarray:
    """Return the 2048-sample zero-inserted canonical QPSK frame."""
    fixed_symbols = np.concatenate(
        (
            np.tile([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], 2),
            np.tile([1 + 1j, -1 - 1j], 4),
            np.tile([1 + 1j, -1 + 1j], 4),
            np.tile([1 + 1j, 1 - 1j], 4),
            np.full(8, 1 + 1j),
        )
    ).astype(np.complex128, copy=False)

    indices = np.random.default_rng(2026).integers(0, 4, size=984)
    corners = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], dtype=np.complex128)
    symbols = np.concatenate((fixed_symbols, corners[indices]))
    return _zero_insert(symbols)


def generate_corner_samples(case: str) -> np.ndarray:
    """Return the 2048-sample zero-inserted frame of one ``sys_corners`` case."""
    if case == "corner_repeat":
        symbols = np.full(_SYMBOL_COUNT, 1 + 1j, dtype=np.complex128)
    elif case == "max_alternation":
        symbols = np.tile(np.array([1 + 1j, -1 - 1j], dtype=np.complex128), _SYMBOL_COUNT // 2)
    elif case == "single_symbol_perturbation":
        symbols = np.full(_SYMBOL_COUNT, 1 + 1j, dtype=np.complex128)
        symbols[_PERTURBATION_INDEX] = -1 - 1j
    else:
        raise ValueError(f"case: expected one of {CORNER_CASES}, got {case!r}")
    return _zero_insert(symbols)
