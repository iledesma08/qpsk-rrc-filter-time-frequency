"""Exercise real Icarus shells and the manifest-driven runner at their interface."""

import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_variant(variant="time_serial", *arguments):
    return subprocess.run(
        ["bash", str(ROOT / f"rtl/{variant}/run.sh"), *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )


@pytest.mark.parametrize("variant", ["time_serial", "freq_serial", "time_opt", "freq_opt"])
@pytest.mark.parametrize("width,spc,accepted,padding", [(8, 1, 33, 0), (12, 2, 34, 1), (16, 4, 36, 3)])
def test_shell_preserves_codes_under_reset_bubbles_and_stalls(variant, width, spc, accepted, padding):
    result = run_variant(variant, "--data-width", str(width), "--spc", str(spc))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: shell stream W={width} SPC={spc}" in result.stdout
    assert "reset, latency, bubbles, stalls" in result.stdout
    assert (f"source_samples=33 flush_samples=0 transport_padding_samples={padding} "
            f"accepted_input_samples={accepted} raw_output_samples={accepted}") in result.stdout


def fixture(directory, *arguments):
    subprocess.run(
        [sys.executable, str(ROOT / "sim/python/tests/rtl_shell_fixture.py"),
         "--output", str(directory), *arguments], check=True,
    )


def rehash(path):
    path.with_name(path.name + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )


def update_manifest(directory, **fields):
    manifest = directory / "vector_manifest.svh"
    contents = manifest.read_text()
    for name, value in fields.items():
        contents, replacements = re.subn(rf"(integer {name} = )-?\d+", rf"\g<1>{value}", contents)
        assert replacements == 1, name
    manifest.write_text(contents)
    rehash(manifest)


@pytest.mark.parametrize("source,flush,compared,physical", [(33, 3, 35, 36), (2048, 8, 2055, 2056)])
def test_tb_accepts_declared_flush_and_captures_raw_padding_without_expected_code(
    tmp_path, source, flush, compared, physical,
):
    # Identity transport analogue only, including the canonical-size count boundary.
    fixture(tmp_path, "--count", str(source), "--flush-samples", str(flush))
    expected = tmp_path / "expected.hex"
    expected.write_text("\n".join(expected.read_text().splitlines()[:-1]) + "\n")
    rehash(expected)
    update_manifest(tmp_path, output_samples=compared, valid_len=compared)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    for robustness in (0, 1):
        assert (f"Frame robustness={robustness} compared={compared} "
                f"accepted_beats={physical} emitted_beats={physical}") in result.stdout
    assert (f"source_samples={source} flush_samples={flush} transport_padding_samples=0 "
            f"accepted_input_samples={physical} raw_output_samples={physical}") in result.stdout


def test_tb_counts_zero_source_flush_and_padding_lanes_on_handshakes(tmp_path):
    fixture(tmp_path, "--data-width", "8", "--spc", "4", "--flush-samples", "2")
    # A zero-valued source record is still source, not flush or an invalid bubble.
    for name in ("input.hex", "expected.hex"):
        vector = tmp_path / name
        vector.write_text(vector.read_text().replace("FFFF0001", "00000000", 1))
        rehash(vector)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    for robustness in (0, 1):
        assert (f"Frame robustness={robustness} compared=35 accepted_beats=9 emitted_beats=9") in result.stdout
    assert ("source_samples=33 flush_samples=2 transport_padding_samples=1 "
            "accepted_input_samples=36 raw_output_samples=36") in result.stdout


@pytest.mark.parametrize("source,flush,padding,physical,beats,compared,codes", [
    (5, 2, 1, 8, 2, 7, [
        "FFFF0001", "007FFF80", "FF80007F", "FFFF0000", "0000FFFF",
        "00000000", "00000000",
    ]),
    (1, 0, 3, 4, 1, 1, ["FFFF0001"]),
], ids=["two-beats-with-flush", "one-beat"])
def test_tb_accepts_short_frames_with_bubbles_and_minimal_beat_padding(
    tmp_path, source, flush, padding, physical, beats, compared, codes,
):
    fixture(tmp_path, "--data-width", "8", "--spc", "4", "--count", str(source),
            "--flush-samples", str(flush))
    assert (tmp_path / "input.hex").read_text().splitlines() == codes[:source]
    assert (tmp_path / "expected.hex").read_text().splitlines() == codes
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: shell stream W=8 SPC=4" in result.stdout
    for robustness in (0, 1):
        frame = next(line for line in result.stdout.splitlines()
                     if line.startswith(f"Frame robustness={robustness} "))
        assert (f"compared={compared} accepted_beats={beats} emitted_beats={beats}") in frame
        assert (f"source_samples={source} flush_samples={flush} transport_padding_samples={padding} "
                f"accepted_input_samples={physical} raw_output_samples={physical}") in frame


@pytest.mark.parametrize("spc,fields", [
    (1, {"accepted_input_samples": 32}),
    (1, {"accepted_input_samples": 34}),
    (1, {"flush_samples": 1}),
    (1, {"flush_samples": -1}),
    (4, {"transport_padding_samples": -1}),
    (4, {"transport_padding_samples": 2, "accepted_input_samples": 35}),
    (4, {"transport_padding_samples": 7, "accepted_input_samples": 40, "raw_output_samples": 40}),
    (1, {"raw_output_samples": 32}),
    (4, {"raw_output_samples": 35}),
    (1, {"raw_output_samples": 0}),
], ids=["accepted-below-source", "accepted-sum", "flush-mismatch", "negative-flush",
        "negative-padding", "partial-input-beat", "nonminimal-padding", "raw-below-window",
        "partial-output-beat", "zero-raw"])
def test_tb_rejects_invalid_transport_counts(tmp_path, spc, fields):
    fixture(tmp_path, "--spc", str(spc))
    update_manifest(tmp_path, **fields)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "Invalid manifest transport counts" in result.stdout


def test_runner_rejects_missing_manifest(tmp_path):
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "Missing vector file" in result.stderr


def test_runner_rejects_bad_checksum(tmp_path):
    fixture(tmp_path)
    (tmp_path / "expected.hex").write_text("00000000\n")
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "Checksum mismatch" in result.stderr


def test_comparator_rejects_wrong_expected_integer_code(tmp_path):
    fixture(tmp_path)
    expected = tmp_path / "expected.hex"
    expected.write_text(expected.read_text().replace("FFFF0001", "FFFF0002", 1))
    rehash(expected)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "Mismatch index=0" in result.stdout
    assert "expected=ffff0002 got=ffff0001" in result.stdout


@pytest.mark.parametrize("old,new", [
    ("DATA_WIDTH = 16", "DATA_WIDTH = 18"),
    ("valid_len = 33", "valid_len = 34"),
    ("latency_cycles = 1", "latency_cycles = 2"),
])
def test_tb_rejects_invalid_metadata(tmp_path, old, new):
    fixture(tmp_path)
    manifest = tmp_path / "vector_manifest.svh"
    manifest.write_text(manifest.read_text().replace(old, new))
    rehash(manifest)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "FATAL" in result.stdout


@pytest.mark.parametrize("name", ["input.hex", "expected.hex"])
def test_tb_rejects_extra_vector_records(tmp_path, name):
    fixture(tmp_path)
    vector = tmp_path / name
    vector.write_text(vector.read_text() + "00000000\n")
    rehash(vector)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "Vector count mismatch" in result.stdout


def test_tb_compares_only_the_manifest_window(tmp_path):
    fixture(tmp_path)
    manifest = tmp_path / "vector_manifest.svh"
    manifest.write_text(manifest.read_text().replace("valid_start = 0", "valid_start = 4")
                        .replace("valid_len = 33", "valid_len = 29"))
    rehash(manifest)
    expected = tmp_path / "expected.hex"
    expected.write_text(expected.read_text().replace("FFFF0001", "00000000", 1))
    rehash(expected)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "compared=29" in result.stdout


@pytest.mark.parametrize("name", ["input.hex", "expected.hex"])
def test_tb_validates_sign_extension_even_outside_comparison_window(tmp_path, name):
    fixture(tmp_path, "--data-width", "8", "--spc", "4")
    update_manifest(tmp_path, valid_start=4, valid_len=29)
    vector = tmp_path / name
    vector.write_text(vector.read_text().replace("FFFF0001", "00000080", 1))
    rehash(vector)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert f"Invalid {name.removesuffix('.hex')} code/sign extension index=0" in result.stdout


def test_runner_rejects_width_override_for_an_existing_manifest(tmp_path):
    fixture(tmp_path)
    result = run_variant("time_serial", "--vectors", str(tmp_path), "--data-width", "8")
    assert result.returncode != 0
    assert "manifest owns" in result.stderr


def test_shell_cannot_claim_a_non_fixture_vector_pass(tmp_path):
    fixture(tmp_path)
    manifest = tmp_path / "vector_manifest.svh"
    manifest.write_text(manifest.read_text().replace("`define RRC_SHELL_FIXTURE\n", ""))
    rehash(manifest)
    result = run_variant("time_serial", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "T03 transport DUT requires a shell fixture" in result.stdout


@pytest.mark.parametrize("raw,compared,error,unknown_ready_after_frame", [
    (29, 29, None, False),
    (28, 28, "Extra or duplicated output after frame", False),
    (30, 29, "Timeout sent=33 received=29 matched=29", False),
    (29, 29, "Unknown post-reset controls ready_o=x valid_o=0", True),
], ids=["declared-raw", "extra-raw", "missing-raw", "unknown-ready-in-drain"])
def test_tb_counts_outputs_from_the_manifest_sample_offset(
    tmp_path, raw, compared, error, unknown_ready_after_frame,
):
    fixture(tmp_path)
    update_manifest(tmp_path, raw_output_samples=raw, valid_len=compared,
                    valid_start=4, latency_samples=4, latency_cycles=5)
    manifest = tmp_path / "vector_manifest.svh"
    manifest.write_text(manifest.read_text().replace("`define RRC_SHELL_FIXTURE\n", ""))
    rehash(manifest)
    adapter = tmp_path / "offset_adapter.sv"
    # Test adapter drops the first four records, exposing absolute indices 4..32.
    adapter.write_text(f"""`timescale 1ns/1ps
module offset_adapter #(
  parameter integer DATA_WIDTH=16, SAMPLES_PER_CLOCK=1
) (
  input logic clk, rst_n, valid_i, ready_i,
  output wire ready_o, valid_o,
  input logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_i,
  output wire [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_o
);
  wire raw_valid, raw_ready, shell_ready;
  integer index;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) index <= 0;
    else if (raw_valid && raw_ready) index <= index + 1;
  assign valid_o = raw_valid && index >= 4;
  assign raw_ready = index < 4 || ready_i;
  assign ready_o = {"index >= 33 ? 1'bx : shell_ready" if unknown_ready_after_frame else "shell_ready"};
  rrc_stream_shell #(.DATA_WIDTH(DATA_WIDTH), .SAMPLES_PER_CLOCK(SAMPLES_PER_CLOCK)) shell (
    .clk(clk), .rst_n(rst_n), .valid_i(valid_i), .ready_o(shell_ready), .sample_i(sample_i),
    .valid_o(raw_valid), .ready_i(raw_ready), .sample_o(sample_o)
  );
endmodule
""")
    executable = tmp_path / "offset.out"
    compile_result = subprocess.run([
        "iverilog", "-g2012", "-D", "DUT_MODULE=offset_adapter", "-I", str(tmp_path),
        "-s", "rrc_stream_tb", "-o", str(executable),
        str(ROOT / "rtl/common/rrc_pkg.sv"), str(ROOT / "rtl/common/rrc_stream_shell.sv"),
        str(adapter), str(ROOT / "rtl/tb/rrc_stream_tb.sv"),
    ], capture_output=True, text=True, check=False)
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(
        ["vvp", str(executable), f"+vector_dir={tmp_path}"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if error is not None:
        assert result.returncode != 0, result.stdout + result.stderr
        assert error in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "compared=29 accepted_beats=33 emitted_beats=29" in result.stdout
        assert ("source_samples=33 flush_samples=0 transport_padding_samples=0 "
                "accepted_input_samples=33 raw_output_samples=29") in result.stdout
