"""T40 (#51): T-S4P1 and T-S8P1 vector matching against the committed rtl_matching vectors.

Both rows come from one source, ``rtl/time_opt/time_opt_filter.sv``; the
manifest's ``rtl_parameters`` selects the row. Each frame is staged from
``sim/vectors/rtl_matching/<row>`` (metadata) and ``sim/vectors/fxp_expected``
(payloads, bound by hash) into ``tmp_path`` and run on the shared testbench.
The two rows emit the same codes with the same latency as each other and bind
the same payloads as T-serial, so the measured II (8/S) is what tells their
runs apart. Standard library only, so it runs in the RTL CI job without NumPy.
"""

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtl_matching_stage as matching  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
ROWS = {"T-S4P1": 4, "T-S8P1": 8}
EVIDENCE_DIR = ROOT / "sim/python/artifacts/t40-time-opt-matching"
T31_EVIDENCE = ROOT / "sim/python/artifacts/t31-time-matching/evidence_manifest.json"
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def rehash(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="utf-8")


def evidence(row: str) -> dict:
    return json.loads((EVIDENCE_DIR / row / "evidence_manifest.json").read_text(encoding="utf-8"))


# Matching of every frame on both rows -------------------------------------------


@pytest.mark.parametrize("vector_set,vector_case", matching.FRAMES)
@pytest.mark.parametrize("row", ROWS)
@requires_icarus
def test_each_row_matches_the_t22_time_codes_on_every_frame(tmp_path, row, vector_set, vector_case):
    manifest = matching.load_matching(row, vector_set, vector_case)["manifest"]
    assert manifest["rtl_parameters"] == {"SYSTOLIC_PES": ROWS[row], "PIPELINE_DEPTH": 1}
    staged = matching.stage(tmp_path, row, vector_set, vector_case)
    capture = tmp_path / matching.CAPTURE_FILE
    result = matching.run_matching("time_opt", staged, capture, manifest["rtl_parameters"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: vector window W=16 SPC=1 compared={manifest['valid_len']}" in result.stdout
    # The captured continuous-run outputs are the expected codes byte for byte,
    # independently of the testbench comparator.
    assert capture.read_bytes() == (staged / "expected.hex").read_bytes()
    report = matching.parse_report(result.stdout)
    assert report["dut_parameters"] == manifest["rtl_parameters"]
    for run in ("continuous", "robustness"):
        frame = report[run]
        assert (frame["compared"], frame["accepted_beats"], frame["emitted_beats"]) == (2055, 2055, 2055), run
        assert (frame["source_samples"], frame["flush_samples"], frame["transport_padding_samples"],
                frame["accepted_input_samples"], frame["raw_output_samples"]) == (2048, 7, 0, 2055, 2055), run
    continuous = report["continuous"]
    # The TB has asserted latency_cycles against the manifest in this unstalled run.
    assert continuous["measured_latency_cycles"] == manifest["latency_cycles"] == 2
    ii = 8 // ROWS[row]
    assert matching.expected_ii(manifest) == ii
    assert (continuous["interval_count"], continuous["ii_min"], continuous["ii_max"],
            continuous["measured_ii"]) == (2054, ii, ii, ii)
    assert report["robustness"]["tail_stalls"] >= 1
    assert report["midtraffic_reset"] == {"prefix_accepted": 2, "restart_index": 0}


# Failures the matching run must report ------------------------------------------


@pytest.mark.parametrize("latency", [1, 3])
@pytest.mark.parametrize("row", ROWS)
@requires_icarus
def test_a_wrong_declared_latency_fails_the_unstalled_run(tmp_path, row, latency):
    staged = matching.stage(tmp_path, row, "canonical", "none")
    svh = staged / matching.SVH_FILE
    svh.write_text(svh.read_text(encoding="ascii").replace(
        "latency_cycles = 2;", f"latency_cycles = {latency};"), encoding="ascii")
    rehash(svh)
    result = matching.run_matching("time_opt", staged, parameters={"SYSTOLIC_PES": ROWS[row], "PIPELINE_DEPTH": 1})
    assert result.returncode != 0
    assert f"Latency mismatch expected={latency} got=2" in result.stdout


@requires_icarus
def test_a_run_without_its_row_is_refused(tmp_path):
    staged = matching.stage(tmp_path, "T-S4P1", "canonical", "none")
    result = matching.run_matching("time_opt", staged)
    assert result.returncode == 2
    assert "--vectors and --capture need --systolic-pes" in result.stderr


@requires_icarus
def test_evidence_refuses_a_run_of_the_other_row(tmp_path, monkeypatch):
    # Same codes, same latency: only the elaborated row and its II tell T-S4P1
    # from T-S8P1, so a swapped runner argument must not produce evidence.
    def swapped(parameters):
        return ["--systolic-pes", str(12 - parameters["SYSTOLIC_PES"]), "--pipeline-depth", "1"]

    monkeypatch.setattr(matching, "runner_arguments", swapped)
    with pytest.raises(RuntimeError, match="elaborated"):
        matching.write_evidence("T-S4P1", tmp_path / "evidence", tmp_path / "build")


def test_runner_arguments_cover_only_known_row_parameters():
    assert matching.runner_arguments({"SYSTOLIC_PES": 4, "PIPELINE_DEPTH": 1}) == [
        "--pipeline-depth", "1", "--systolic-pes", "4"]
    assert matching.runner_arguments({}) == []
    with pytest.raises(ValueError, match="no runner argument"):
        matching.runner_arguments({"S": 4})


# Committed evidence ---------------------------------------------------------------


@pytest.mark.parametrize("row", ROWS)
def test_committed_evidence_binds_the_committed_vectors_row_and_ii(row):
    record = evidence(row)
    parameters = {"SYSTOLIC_PES": ROWS[row], "PIPELINE_DEPTH": 1}
    ii = 8 // ROWS[row]
    assert (record["variant_id"], record["rtl_variant"], record["model_domain"]) == (row, "time_opt", "time")
    assert (record["rtl_parameters"], record["expected_ii"]) == (parameters, ii)
    assert record["vector_generator"]["generator"] == "sim/python/gen_vectors.py"
    assert sorted(record["frames"]) == sorted(f"{s}/{c}" for s, c in matching.FRAMES)
    assert record["summary"] == {
        "frames": 4, "passed": 4, "compared_codes": 4 * 2055, "captured_equal_to_expected": 4, "mismatches": 0,
        "measured_latency_cycles": [2], "measured_ii": [ii],
    }
    for key, frame in record["frames"].items():
        loaded = matching.load_matching(row, *key.split("/"))
        manifest = loaded["manifest"]
        assert manifest["rtl_parameters"] == parameters
        assert frame["result"] == "PASS"
        assert frame["dut_parameters"] == parameters
        assert frame["bound_sha256"] == {
            "vector_manifest_svh": hashlib.sha256(loaded["svh"]).hexdigest(),
            "input_hex": manifest["hashes"]["input_hex_sha256"],
            "expected_hex": manifest["hashes"]["expected_hex_sha256"],
        }
        assert frame["declared"] == {name: manifest[name] for name in frame["declared"]}
        assert frame["captured_output_sha256"] == manifest["hashes"]["expected_hex_sha256"]
        assert frame["continuous"]["measured_latency_cycles"] == manifest["latency_cycles"]
        assert frame["continuous"]["measured_ii"] == ii
        assert frame["continuous"]["compared"] == frame["robustness"]["compared"] == manifest["valid_len"]
        assert frame["robustness"]["tail_stalls"] >= 1


def test_both_rows_captured_the_same_codes_as_t_serial():
    # Bit-exact within the time domain: every frame's RTL capture has one hash
    # across T-serial (T31 evidence), T-S4P1 and T-S8P1.
    serial = json.loads(T31_EVIDENCE.read_text(encoding="utf-8"))["frames"]
    rows = {row: evidence(row)["frames"] for row in ROWS}
    for key, frame in serial.items():
        assert {rows[row][key]["captured_output_sha256"] for row in ROWS} == {frame["captured_output_sha256"]}
