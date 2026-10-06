"""Shell fixtures are reproducible integer-code tests, not RRC goldens."""

import hashlib
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "sim/python/tests/rtl_shell_fixture.py"


def generate(directory, *arguments):
    return subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(directory), *arguments],
        capture_output=True, text=True, check=False,
    )


def test_fixture_preserves_signed_iq_codes_and_partial_beat(tmp_path):
    result = generate(tmp_path, "--data-width", "8", "--spc", "4", "--count", "33")
    assert result.returncode == 0, result.stderr
    records = (tmp_path / "input.hex").read_text().splitlines()
    assert len(records) == 33
    assert records[:5] == ["FFFF0001", "007FFF80", "FF80007F", "FFFF0000", "0000FFFF"]
    assert (tmp_path / "expected.hex").read_text().splitlines() == records
    manifest = (tmp_path / "vector_manifest.svh").read_text()
    for declaration in (
        "DATA_WIDTH = 8;", "SPC = 4;", "input_samples = 33;",
        "output_samples = 33;", "valid_start = 0;", "valid_len = 33;",
        "latency_samples = 0;", "latency_cycles = 1;",
        "flush_samples = 0;", "transport_padding_samples = 3;",
        "accepted_input_samples = 36;", "raw_output_samples = 36;",
    ):
        assert declaration in manifest


def test_fixture_appends_flush_zeros_but_not_physical_beat_padding(tmp_path):
    result = generate(tmp_path, "--data-width", "8", "--spc", "4", "--count", "5",
                      "--flush-samples", "2")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "input.hex").read_text().splitlines() == [
        "FFFF0001", "007FFF80", "FF80007F", "FFFF0000", "0000FFFF",
    ]
    assert (tmp_path / "expected.hex").read_text().splitlines() == [
        "FFFF0001", "007FFF80", "FF80007F", "FFFF0000", "0000FFFF",
        "00000000", "00000000",
    ]
    manifest = (tmp_path / "vector_manifest.svh").read_text()
    for declaration in (
        "input_samples = 5;", "output_samples = 7;", "valid_len = 7;",
        "flush_samples = 2;", "transport_padding_samples = 1;",
        "accepted_input_samples = 8;", "raw_output_samples = 8;",
    ):
        assert declaration in manifest
    for name in ("input.hex", "expected.hex", "vector_manifest.svh"):
        contents = (tmp_path / name).read_bytes()
        assert (tmp_path / f"{name}.sha256").read_text().split()[0] == hashlib.sha256(contents).hexdigest()


def test_fixture_rejects_negative_flush(tmp_path):
    result = generate(tmp_path, "--flush-samples", "-1")
    assert result.returncode != 0
    assert "flush_samples >= 0" in result.stderr
    assert not (tmp_path / "input.hex").exists()


def test_fixture_regenerates_with_valid_hashes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    assert generate(first).returncode == 0
    assert generate(second).returncode == 0
    for name in ("input.hex", "expected.hex", "vector_manifest.svh"):
        contents = (first / name).read_bytes()
        assert contents == (second / name).read_bytes()
        assert (first / f"{name}.sha256").read_text().split()[0] == hashlib.sha256(contents).hexdigest()


@pytest.mark.parametrize("arguments", [
    ("--data-width", "18"), ("--data-width", "1"),
    ("--spc", "0"), ("--count", "0"),
])
def test_fixture_rejects_unrepresentable_configuration(tmp_path, arguments):
    result = generate(tmp_path, *arguments)
    assert result.returncode != 0
    assert "error:" in result.stderr
    assert not (tmp_path / "input.hex").exists()


def test_fixture_refuses_to_write_goldens():
    result = generate(ROOT / "sim/vectors")
    assert result.returncode != 0
    assert "sim/vectors" in result.stderr
