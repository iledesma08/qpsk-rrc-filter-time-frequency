"""Shared integration checks between time- and frequency-domain goldens."""

import numpy as np

from golden_freq import generate_frequency_golden
from golden_time import generate_time_golden


def test_canonical_time_and_frequency_goldens_match():
	frequency_output = generate_frequency_golden()
	time_output = generate_time_golden()

	assert frequency_output.shape == time_output.shape == (2055,)
	np.testing.assert_allclose(frequency_output, time_output, rtol=1e-10, atol=1e-12)