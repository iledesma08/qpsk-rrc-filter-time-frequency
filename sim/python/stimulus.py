"""Canonical deterministic QPSK stimulus frame."""

import numpy as np


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

    samples = np.zeros(2048, dtype=np.complex128)
    samples[::2] = symbols
    return samples
