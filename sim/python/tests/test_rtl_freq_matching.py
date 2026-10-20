"""T33 (#50): F-serial vector matching against the committed rtl_matching vectors.

Each frame is staged from ``sim/vectors/rtl_matching/F-serial`` (metadata) and
``sim/vectors/fxp_expected`` (payloads, bound by hash) into ``tmp_path`` and run
on the shared testbench. The negative cases edit only the staged copy.
Standard library only, so it runs in the RTL CI job without NumPy.
"""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtl_matching_stage as matching  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
VARIANT = "F-serial"
EVIDENCE = ROOT / "sim/python/artifacts/t33-freq-matching/evidence_manifest.json"
BLOCKS, HOP, BLOCK_CYCLES, LATENCY = 257, 8, 107, 99
# Last source sample x[2047] to the last valid output y[2054]: one block (107) + the fill (99) + the positions
# of the two inside their blocks (6 - 7). The tail-flush block's cost, unlike the tail to the padding output.
SOURCE_TAIL = 205
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_freq_serial(staged: Path, capture: Path | None = None, vcd: Path | None = None) -> subprocess.CompletedProcess:
    return matching.run_matching("freq_serial", staged, capture, vcd=vcd)


def rehash(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="utf-8")


def edit_svh(staged: Path, **fields: int) -> None:
    """Change localparams of a staged ``.svh`` (test-only metadata) and rehash it."""
    svh = staged / matching.SVH_FILE
    text = svh.read_text(encoding="ascii")
    current = matching.svh_fields(text)
    for name, value in fields.items():
        text = text.replace(f"localparam integer {name} = {current[name]};", f"localparam integer {name} = {value};")
    svh.write_text(text, encoding="ascii")
    rehash(svh)


def copy_vectors(tmp_path: Path) -> Path:
    vectors = tmp_path / "vectors"
    for stage in ("fxp_expected", "rtl_matching"):
        shutil.copytree(matching.VECTORS / stage, vectors / stage)
    return vectors


# Matching of every frame ------------------------------------------------------


@pytest.mark.parametrize("vector_set,vector_case", matching.FRAMES)
@requires_icarus
def test_f_serial_matches_the_t22_frequency_codes_on_every_frame(tmp_path, vector_set, vector_case):
    manifest = matching.load_matching(VARIANT, vector_set, vector_case)["manifest"]
    staged = matching.stage(tmp_path, VARIANT, vector_set, vector_case)
    capture = tmp_path / matching.CAPTURE_FILE
    result = run_freq_serial(staged, capture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: vector window W=16 SPC=1 compared={manifest['valid_len']}" in result.stdout
    # 2056 raw outputs: the first 2055 are the expected codes byte for byte; the last is the block padding
    # of block 257, outside the comparison window.
    captured = capture.read_text(encoding="ascii").split()
    expected = (staged / "expected.hex").read_text(encoding="ascii").split()
    assert captured[:2055] == expected
    # Regression sentinel, not a contract value: y[2055] depends only on the flush zeros, so it is zero in
    # exact arithmetic, but no manifest declares it and the FXP path only happens to give 00000000.
    assert captured[2055:] == ["00000000"]
    report = matching.parse_report(result.stdout)
    for run in ("continuous", "robustness"):
        frame = report[run]
        assert (frame["compared"], frame["accepted_beats"], frame["emitted_beats"]) == (2055, 2056, 2056), run
        # 2048 source records plus 8 flush zeros that complete block 257, one raw output per accepted sample.
        assert (frame["source_samples"], frame["flush_samples"], frame["transport_padding_samples"],
                frame["accepted_input_samples"], frame["raw_output_samples"]) == (2048, 8, 0, 2056, 2056), run
    continuous = report["continuous"]
    assert continuous["measured_latency_cycles"] == manifest["latency_cycles"] == LATENCY
    assert continuous["cycles"] == 27499
    # The serial engine is block-rate limited: no per-sample II exists, the block II does.
    assert continuous["measured_ii"] == "undefined"
    assert report["block_timing"] == {
        "blocks": BLOCKS, "hop": HOP, "block_ii_count": BLOCKS - 1, "block_ii_min": BLOCK_CYCLES,
        "block_ii_max": BLOCK_CYCLES, "fill_latency_cycles": LATENCY, "tail_latency_cycles": LATENCY,
        "source_tail_latency_cycles": SOURCE_TAIL}
    assert report["robustness"]["tail_stalls"] >= 1
    assert report["robustness"]["measured_latency_cycles"] == "undefined"
    assert report["midtraffic_reset"] == {"prefix_accepted": 2, "restart_index": 0}


@requires_icarus
def test_the_vcd_covers_all_257_blocks(tmp_path):
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    vcd = tmp_path / matching.VCD_FILE
    result = run_freq_serial(staged, vcd=vcd)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = matching.summarize_vcd(vcd, BLOCKS)
    assert summary["covers_all_blocks"] is True
    assert summary["engine_state_entries"] == {state: BLOCKS for state in ("load", "run", "emit", "drain")}


# Failures the matching run must report ------------------------------------------


@pytest.mark.parametrize("index", [0, 1027, 2054], ids=["first", "middle", "last"])
@requires_icarus
def test_a_wrong_expected_code_reports_its_absolute_index(tmp_path, index):
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    expected = staged / "expected.hex"
    lines = expected.read_text(encoding="ascii").splitlines()
    captured = lines[index]
    lines[index] = f"{int(captured, 16) ^ 1:08x}"
    expected.write_text("\n".join(lines) + "\n", encoding="ascii")
    rehash(expected)
    result = run_freq_serial(staged)
    assert result.returncode != 0
    assert f"Mismatch index={index} expected={lines[index]} got={captured}" in result.stdout


@pytest.mark.parametrize("latency", [98, 100])
@requires_icarus
def test_a_wrong_declared_latency_fails_the_unstalled_run(tmp_path, latency):
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, latency_cycles=latency)
    result = run_freq_serial(staged)
    assert result.returncode != 0
    assert f"Latency mismatch expected={latency} got={LATENCY}" in result.stdout


@requires_icarus
def test_a_missing_emission_times_out(tmp_path):
    # One raw output more than the 2056 accepted samples can produce.
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, raw_output_samples=2057)
    result = run_freq_serial(staged)
    assert result.returncode != 0
    assert "Timeout sent=2056 received=2056" in result.stdout


@requires_icarus
def test_an_undeclared_extra_block_fails_the_drain_check(tmp_path):
    # Eight more flush zeros make the DUT run a 258th block whose 8 outputs the manifest does not declare.
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, flush_samples=16, accepted_input_samples=2064)
    result = run_freq_serial(staged)
    assert result.returncode != 0
    assert ("Extra or duplicated output after frame" in result.stdout
            or "Unexpected extra output beat" in result.stdout), result.stdout


# Staging: hash binding before any comparison counts -------------------------


def test_staging_copies_exactly_the_bound_payloads_and_metadata(tmp_path):
    for vector_set, vector_case in matching.FRAMES:
        frame = matching.load_matching(VARIANT, vector_set, vector_case)
        staged = matching.stage(tmp_path / vector_case, VARIANT, vector_set, vector_case)
        f2_dir = matching.VECTORS / "fxp_expected" / vector_set / vector_case
        matching_dir = matching.VECTORS / "rtl_matching" / VARIANT / vector_set / vector_case
        assert (staged / "input.hex").read_bytes() == (f2_dir / "input.hex").read_bytes()
        assert (staged / "expected.hex").read_bytes() == (f2_dir / "expected_freq.hex").read_bytes()
        assert (staged / matching.SVH_FILE).read_bytes() == (matching_dir / matching.SVH_FILE).read_bytes()
        fields = matching.svh_fields((staged / matching.SVH_FILE).read_text(encoding="ascii"))
        assert fields == {name: frame["manifest"][name] for name in fields}
        assert (fields["DATA_WIDTH"], fields["SPC"], fields["latency_samples"], fields["latency_cycles"]) == (16, 1, 0, LATENCY)


@pytest.mark.parametrize("target,rehash_it,error", [
    ("expected", False, "hash does not match its sidecar"),
    ("expected", True, "expected_hex_sha256"),
    ("input", True, "input_hex_sha256"),
    ("svh", False, "hash does not match its sidecar"),
    ("svh", True, "vector_manifest_svh_sha256"),
])
def test_staging_refuses_payloads_or_metadata_the_manifest_does_not_bind(tmp_path, target, rehash_it, error):
    vectors = copy_vectors(tmp_path)
    paths = {
        "expected": vectors / "fxp_expected/sys_corners/max_alternation/expected_freq.hex",
        "input": vectors / "fxp_expected/sys_corners/max_alternation/input.hex",
        "svh": vectors / "rtl_matching" / VARIANT / "sys_corners/max_alternation" / matching.SVH_FILE,
    }
    path = paths[target]
    if target == "svh":
        path.write_text(path.read_text(encoding="ascii").replace(
            f"latency_cycles = {LATENCY};", f"latency_cycles = {LATENCY - 1};"), encoding="ascii")
    else:
        lines = path.read_text(encoding="ascii").splitlines()
        lines[3] = f"{int(lines[3], 16) ^ 1:08x}"
        path.write_text("\n".join(lines) + "\n", encoding="ascii")
    if rehash_it:
        rehash(path)
    with pytest.raises(ValueError, match=error):
        matching.stage(tmp_path / "staged", VARIANT, "sys_corners", "max_alternation", vectors)
    assert not (tmp_path / "staged").exists()


def test_staging_refuses_the_protected_vector_directory():
    target = matching.VECTORS / "t33-staged"
    with pytest.raises(ValueError, match="never go into sim/vectors"):
        matching.stage(target, VARIANT, "canonical", "none")
    assert not target.exists()


# Expected block timing is the serial engine's own ---------------------------------


def test_expected_block_timing_is_scoped_to_the_serial_engine():
    manifest = matching.load_matching(VARIANT, "canonical", "none")["manifest"]
    timing = matching.expected_block_timing(manifest)
    assert (timing["block_ii"], timing["tail_latency_cycles"], timing["source_tail_latency_cycles"]) == (
        BLOCK_CYCLES, LATENCY, SOURCE_TAIL)
    # An unrolled variant (T42) must not inherit the serial schedule, nor a time variant any block timing.
    assert matching.expected_block_timing({**manifest, "rtl_variant": "freq_unrolled"}) is None
    assert matching.expected_block_timing({**manifest, "model_domain": "time", "rtl_variant": "time_serial"}) is None


# Committed evidence ---------------------------------------------------------------


def test_committed_evidence_binds_the_committed_vectors_and_the_measured_timing():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert (evidence["variant_id"], evidence["rtl_variant"], evidence["model_domain"]) == (VARIANT, "freq_serial", "frequency")
    assert sorted(evidence["frames"]) == sorted(f"{s}/{c}" for s, c in matching.FRAMES)
    assert evidence["summary"] == {
        "frames": 4, "passed": 4, "compared_codes": 4 * 2055, "captured_equal_to_expected": 4, "mismatches": 0,
        "measured_latency_cycles": [LATENCY], "measured_ii": ["undefined"], "measured_block_ii": [BLOCK_CYCLES],
        "fill_latency_cycles": [LATENCY], "tail_latency_cycles": [LATENCY], "source_tail_latency_cycles": [SOURCE_TAIL],
        "vcd_covers_all_blocks": True,
    }
    for key, frame in evidence["frames"].items():
        loaded = matching.load_matching(VARIANT, *key.split("/"))
        manifest = loaded["manifest"]
        assert frame["result"] == "PASS"
        assert frame["bound_sha256"] == {
            "vector_manifest_svh": hashlib.sha256(loaded["svh"]).hexdigest(),
            "input_hex": manifest["hashes"]["input_hex_sha256"],
            "expected_hex": manifest["hashes"]["expected_hex_sha256"],
        }
        assert frame["declared"] == {name: manifest[name] for name in frame["declared"]}
        assert frame["captured_valid_window_sha256"] == manifest["hashes"]["expected_hex_sha256"]
        # Regression sentinel, not a contract value (see the matching test above).
        assert frame["block_padding_records"] == ["00000000"]
        assert frame["block_timing"]["blocks"] == BLOCKS
        assert frame["continuous"]["compared"] == frame["robustness"]["compared"] == manifest["valid_len"]
        assert frame["robustness"]["tail_stalls"] >= 1
    assert evidence["frames"]["canonical/none"]["vcd"]["covers_all_blocks"] is True
