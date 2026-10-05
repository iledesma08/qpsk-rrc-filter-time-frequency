"""Shared integration checks between time- and frequency-domain goldens."""

import json

import numpy as np

from golden_freq import generate_frequency_evidence, generate_frequency_golden
from golden_time import generate_time_evidence, generate_time_golden


def test_canonical_time_and_frequency_goldens_match():
	frequency_output = generate_frequency_golden()
	time_output = generate_time_golden()

	assert frequency_output.shape == time_output.shape == (2055,)
	np.testing.assert_allclose(frequency_output, time_output, rtol=1e-10, atol=1e-12)


def test_time_and_frequency_evidence_hashes_are_comparable(tmp_path):
	time_manifest_path = generate_time_evidence(tmp_path / "t11-time-golden")
	frequency_manifest_path = generate_frequency_evidence(
		tmp_path / "t12-freq-golden",
		tmp_path / "golden_comparison",
	)
	time_manifest = json.loads(time_manifest_path.read_text(encoding="utf-8"))
	frequency_manifest = json.loads(frequency_manifest_path.read_text(encoding="utf-8"))

	assert time_manifest["hash_serialization"] == frequency_manifest["hash_serialization"]
	assert time_manifest["input_samples_sha256"] == frequency_manifest["input"]["input_samples_sha256"]
	assert time_manifest["input_coefficients_sha256"] == frequency_manifest["input"]["coefficients_sha256"]