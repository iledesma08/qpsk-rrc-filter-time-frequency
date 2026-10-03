"""Shared integration checks between time- and frequency-domain goldens."""

import numpy as np

from golden_freq import filter_frequency_domain
from golden_time import generate_time_golden
from stimulus import generate_canonical_samples


def test_canonical_time_and_frequency_goldens_match():
	samples = generate_canonical_samples()
	frequency_output = filter_frequency_domain(samples)
	time_output = generate_time_golden()

	assert samples.shape == (2048,)
	assert frequency_output.shape == time_output.shape == (2055,)
	np.testing.assert_allclose(frequency_output, time_output, rtol=1e-10, atol=1e-12)