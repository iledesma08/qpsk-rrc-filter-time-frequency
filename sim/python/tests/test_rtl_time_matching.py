"""T31 (#48): T-serial vector matching against the committed rtl_matching vectors.

Each frame is staged from ``sim/vectors/rtl_matching/T-serial`` (metadata) and
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
VARIANT = "T-serial"
EVIDENCE = ROOT / "sim/python/artifacts/t31-time-matching/evidence_manifest.json"
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_time_serial(staged: Path, capture: Path | None = None) -> subprocess.CompletedProcess:
    return matching.run_matching("time_serial", staged, capture)


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
def test_t_serial_matches_the_t22_time_codes_on_every_frame(tmp_path, vector_set, vector_case):
    manifest = matching.load_matching(VARIANT, vector_set, vector_case)["manifest"]
    staged = matching.stage(tmp_path, VARIANT, vector_set, vector_case)
    capture = tmp_path / matching.CAPTURE_FILE
    result = run_time_serial(staged, capture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: vector window W=16 SPC=1 compared={manifest['valid_len']}" in result.stdout
    # The captured continuous-run outputs are the expected codes byte for byte,
    # independently of the testbench comparator.
    assert capture.read_bytes() == (staged / "expected.hex").read_bytes()
    report = matching.parse_report(result.stdout)
    for run in ("continuous", "robustness"):
        frame = report[run]
        assert (frame["compared"], frame["accepted_beats"], frame["emitted_beats"]) == (2055, 2055, 2055), run
        # 2048 source records plus 7 accepted flush zeros, one raw output per accepted sample.
        assert (frame["source_samples"], frame["flush_samples"], frame["transport_padding_samples"],
                frame["accepted_input_samples"], frame["raw_output_samples"]) == (2048, 7, 0, 2055, 2055), run
    continuous = report["continuous"]
    # The TB has asserted latency_cycles against the manifest in this unstalled run.
    assert continuous["measured_latency_cycles"] == manifest["latency_cycles"] == 9
    assert (continuous["interval_count"], continuous["ii_min"], continuous["ii_max"],
            continuous["measured_ii"]) == (2054, 8, 8, 8)
    # The robust run fails unless bubbles, sink stalls and ready_o backpressure occur.
    assert report["robustness"]["tail_stalls"] >= 1
    assert report["robustness"]["measured_latency_cycles"] == "undefined"
    assert report["midtraffic_reset"] == {"prefix_accepted": 2, "restart_index": 0}


# Failures the matching run must report ------------------------------------------


@pytest.mark.parametrize("index", [0, 1027, 2054], ids=["first", "middle", "last-flush"])
@requires_icarus
def test_a_wrong_expected_code_reports_its_absolute_index(tmp_path, index):
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    expected = staged / "expected.hex"
    lines = expected.read_text(encoding="ascii").splitlines()
    captured = lines[index]
    lines[index] = f"{int(captured, 16) ^ 1:08x}"
    expected.write_text("\n".join(lines) + "\n", encoding="ascii")
    rehash(expected)
    result = run_time_serial(staged)
    assert result.returncode != 0
    assert f"Mismatch index={index} expected={lines[index]} got={captured}" in result.stdout


@pytest.mark.parametrize("latency", [8, 10])
@requires_icarus
def test_a_wrong_declared_latency_fails_the_unstalled_run(tmp_path, latency):
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, latency_cycles=latency)
    result = run_time_serial(staged)
    assert result.returncode != 0
    assert f"Latency mismatch expected={latency} got=9" in result.stdout


@requires_icarus
def test_a_missing_emission_times_out(tmp_path):
    # One raw output more than the 2055 accepted samples can produce.
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, raw_output_samples=2056)
    result = run_time_serial(staged)
    assert result.returncode != 0
    assert "Timeout sent=2055 received=2055" in result.stdout


@requires_icarus
def test_an_undeclared_extra_emission_fails_the_drain_check(tmp_path):
    # An eighth flush zero makes the DUT emit a 2056th output the manifest does not declare.
    staged = matching.stage(tmp_path, VARIANT, "canonical", "none")
    edit_svh(staged, flush_samples=8, accepted_input_samples=2056)
    result = run_time_serial(staged)
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
        assert (staged / "expected.hex").read_bytes() == (f2_dir / "expected_time.hex").read_bytes()
        assert (staged / matching.SVH_FILE).read_bytes() == (matching_dir / matching.SVH_FILE).read_bytes()
        for name in ("input.hex", "expected.hex", matching.SVH_FILE):
            assert matching.checked_bytes(staged / name)
        fields = matching.svh_fields((staged / matching.SVH_FILE).read_text(encoding="ascii"))
        assert fields == {name: frame["manifest"][name] for name in fields}
        assert (fields["DATA_WIDTH"], fields["SPC"], fields["latency_samples"]) == (16, 1, 0)


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
        "expected": vectors / "fxp_expected/sys_corners/max_alternation/expected_time.hex",
        "input": vectors / "fxp_expected/sys_corners/max_alternation/input.hex",
        "svh": vectors / "rtl_matching" / VARIANT / "sys_corners/max_alternation" / matching.SVH_FILE,
    }
    path = paths[target]
    if target == "svh":
        path.write_text(path.read_text(encoding="ascii").replace(
            "latency_cycles = 9;", "latency_cycles = 8;"), encoding="ascii")
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
    target = matching.VECTORS / "t31-staged"
    with pytest.raises(ValueError, match="never go into sim/vectors"):
        matching.stage(target, VARIANT, "canonical", "none")
    assert not target.exists()


def test_staging_refuses_a_variant_without_committed_metadata(tmp_path):
    with pytest.raises(ValueError, match="exactly one rtl_matching manifest"):
        matching.stage(tmp_path, "F-U4", "canonical", "none")


# Committed evidence ---------------------------------------------------------------


def test_committed_evidence_binds_the_committed_vectors_and_the_declared_latency():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert (evidence["variant_id"], evidence["rtl_variant"], evidence["model_domain"]) == (VARIANT, "time_serial", "time")
    assert sorted(evidence["frames"]) == sorted(f"{s}/{c}" for s, c in matching.FRAMES)
    assert evidence["summary"] == {
        "frames": 4, "passed": 4, "compared_codes": 4 * 2055, "captured_equal_to_expected": 4, "mismatches": 0,
        "measured_latency_cycles": [9], "measured_ii": [8],
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
        assert frame["captured_output_sha256"] == manifest["hashes"]["expected_hex_sha256"]
        assert frame["continuous"]["measured_latency_cycles"] == manifest["latency_cycles"]
        assert frame["continuous"]["measured_ii"] == 8
        assert frame["continuous"]["compared"] == frame["robustness"]["compared"] == manifest["valid_len"]
        assert frame["robustness"]["tail_stalls"] >= 1
