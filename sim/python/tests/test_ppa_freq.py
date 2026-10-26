"""T43 (#54): frequency-lane PPA target runs, their block timing and their committed evidence.

The run table (``openlane/ppa_runs.json``), the three frequency configs and the SDC pair must resolve
F-serial, F-U4 and F-U8 at both targets with nothing but the clock changing. The frequency engines have no
per-sample II: the gate-level run must show the block II, fill and tail of the row, and the normalized row
takes its throughput from the block II. The committed evidence of the six frequency target runs (executed
or unrun) must agree with the table, with its own OpenLane reports and with the T33/T42 matching evidence
of the same RTL, and ``rows.json`` must be what ``ppa_stage.py rows`` computes from it. The generic
conversion, report and comparison helpers are tested in ``test_ppa_time.py``. Standard library only, so it
runs in the RTL CI job without NumPy.
"""

import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppa_activity as activity  # noqa: E402
import ppa_stage as ppa  # noqa: E402
import rtl_matching_stage as matching  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
TABLE = ppa.load_table()
FREQ_ROWS = {"F-serial": 1, "F-U4": 4, "F-U8": 8}
MAIN = {"F-serial": "SLOW", "F-U4": "FAST", "F-U8": "FAST"}
# Block II = 8 ACCEPT + 1 LOAD + RUN + 8 EMIT + 1 DRAIN, with RUN = 80/U + 9 cycles.
BLOCK_II = {"F-serial": 107, "F-U4": 47, "F-U8": 37}
RUNS = [(row, target) for row in FREQ_ROWS for target in ("SLOW", "FAST")]
EVIDENCE = ROOT / TABLE["evidence_dirs"]["freq"]
MATCHING_EVIDENCE = {
    "F-serial": ROOT / "sim/python/artifacts/t33-freq-matching/evidence_manifest.json",
    "F-U4": ROOT / "sim/python/artifacts/t42-freq-opt-matching/F-U4/evidence_manifest.json",
    "F-U8": ROOT / "sim/python/artifacts/t42-freq-opt-matching/F-U8/evidence_manifest.json",
}
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def evidence(row: str, target: str) -> dict:
    return json.loads((EVIDENCE / row / target.lower() / ppa.EVIDENCE_FILE).read_text(encoding="utf-8"))


def committed_metrics(row: str, target: str) -> dict:
    """The metrics a run ended with: ``final/metrics.json``, or the last state's when the flow wrote no ``final/``."""
    record = evidence(row, target)
    name = "final/metrics.json" if record["metrics_source"] == "final/metrics.json" else "last-state/metrics.json"
    return json.loads((EVIDENCE / row / target.lower() / name).read_text(encoding="utf-8"))


# Run table, configs and rows ----------------------------------------------------------


def test_the_run_table_names_the_frequency_task_and_directory():
    assert TABLE["tasks"] == {"time": "T41", "freq": "T43"}
    assert TABLE["evidence_dirs"]["freq"] == "sim/python/artifacts/t43-freq-ppa"
    assert {row for row, entry in TABLE["rows"].items() if entry["lane"] == "freq"} == set(FREQ_ROWS)


@pytest.mark.parametrize("row", FREQ_ROWS)
def test_each_config_carries_its_rows_main_target_and_the_sizing_rule(row):
    entry = TABLE["rows"][row]
    assert entry["main_target"] == MAIN[row]
    config = json.loads((ROOT / entry["config"]).read_text(encoding="utf-8"))
    main = TABLE["targets"][entry["main_target"]]
    sdc = Path(main["sdc"]).name
    assert config["DESIGN_NAME"] == f"{entry['rtl_variant']}_filter"
    assert config["CLOCK_PERIOD"] == main["clock_period_ns"]
    assert config["PNR_SDC_FILE"] == config["SIGNOFF_SDC_FILE"] == f"dir::../sdc/{sdc}"
    assert (config["FP_SIZING"], config["FP_CORE_UTIL"]) == ("relative", TABLE["sizing"]["FP_CORE_UTIL"])
    assert "DIE_AREA" not in config and "SYNTH_PARAMETERS" not in config
    # OpenLane only globs inside the design directory: the DUT files are named, shared package first.
    assert not any("*" in item for item in config["VERILOG_FILES"])
    names = [Path(item).name for item in config["VERILOG_FILES"]]
    assert names[:4] == ["rrc_pkg.sv", "rrc_reset_sync.sv", "rrc_freq_pkg.sv", "rrc_freq_engine.sv"]
    assert names[4] == f"{entry['rtl_variant']}_filter.sv" and len(names) == 5
    for item in config["VERILOG_FILES"]:
        assert ((ROOT / entry["config"]).parent / item.removeprefix("dir::")).resolve().is_file(), item


@pytest.mark.parametrize("row,lanes", FREQ_ROWS.items())
def test_synthesis_parameters_are_the_rows_rtl_parameters(row, lanes):
    entry = TABLE["rows"][row]
    manifest = matching.load_matching(row, TABLE["activity"]["vector_set"], TABLE["activity"]["vector_case"])["manifest"]
    assert entry["synth_parameters"] == manifest.get("rtl_parameters", {}) == ({"U": lanes} if lanes > 1 else {})
    assert entry["factors"] == {"U": lanes, "fft_n": 16, "hop": 8}
    assert entry["serial"] == "F-serial" and entry["lane"] == "freq"
    timing = matching.expected_block_timing(manifest)
    assert timing["block_ii"] == BLOCK_II[row]
    assert matching.expected_ii(manifest) is None


@pytest.mark.parametrize("row", FREQ_ROWS)
def test_the_two_targets_of_a_row_differ_only_in_the_clock(row):
    slow, fast = (ppa.overrides(ppa.target_run(TABLE, row, target)) for target in ("SLOW", "FAST"))
    as_dict = [dict(value.split("=", 1) for value in values) for values in (slow, fast)]
    allowed = {"CLOCK_PERIOD", "PNR_SDC_FILE", "SIGNOFF_SDC_FILE", "SYNTH_PARAMETERS"}
    assert set(as_dict[0]) == set(as_dict[1]) <= allowed
    changed = {key for key in as_dict[0] if as_dict[0][key] != as_dict[1][key]}
    assert changed == {"CLOCK_PERIOD", "PNR_SDC_FILE", "SIGNOFF_SDC_FILE"}
    expected = ",".join(f"{k}={v}" for k, v in sorted(TABLE["rows"][row]["synth_parameters"].items()))
    assert as_dict[0].get("SYNTH_PARAMETERS", "") == expected


def test_target_run_roles_tags_and_the_serial_reference():
    spec = ppa.target_run(TABLE, "F-U4", "SLOW")
    assert (spec["target_role"], spec["run_tag"], spec["serial_run_tag"]) == ("secondary", "F-U4-SLOW", "F-serial-SLOW")
    assert spec["evidence_dir"] == f"{TABLE['evidence_dirs']['freq']}/F-U4/slow"
    assert [ppa.target_run(TABLE, row, MAIN[row])["target_role"] for row in FREQ_ROWS] == ["main"] * 3
    assert ppa.target_run(TABLE, "F-serial", "FAST")["target_role"] == "secondary"
    with pytest.raises(ValueError, match="unknown row"):
        ppa.target_run(TABLE, "F-U2", "FAST")


# Normalized row of a block engine ------------------------------------------------------


def synthetic_gate_level(row: str, failures: list[str] | None = None) -> dict:
    ii = BLOCK_II[row]
    return {"failures": failures or [], "continuous": {"measured_ii": "undefined", "compared": 2055},
            "block_timing": {"blocks": 257, "hop": 8, "block_ii_count": 256, "block_ii_min": ii, "block_ii_max": ii}}


@pytest.mark.parametrize("row,target", [("F-serial", "SLOW"), ("F-U8", "FAST")])
def test_a_block_engine_row_takes_its_ii_and_throughput_from_the_block(row, target):
    spec = ppa.target_run(TABLE, row, target)
    entry = ppa.normalized_row(TABLE, spec, "passed", [], None, None, None, synthetic_gate_level(row), None, None)
    assert (entry["lane"], entry["architecture"], entry["U"], entry["S"], entry["fft_n"], entry["hop"]) == (
        "freq", row, FREQ_ROWS[row], None, 16, 8)
    assert entry["workload"] == TABLE["activity"]["workload_by_lane"]["freq"] and "257 blocks" in entry["workload"]
    ii = BLOCK_II[row]
    assert entry["ii_cycles"] == ii
    assert entry["samples_per_cycle"] == pytest.approx(8 / ii)
    assert entry["effective_outputs_per_s"] == pytest.approx(1e9 / spec["clock_period_ns"] * 8 / ii)
    assert entry["vector_status"] == "pass"


def test_the_time_rows_keep_their_workload_and_per_sample_ii():
    spec = ppa.target_run(TABLE, "T-S8P1", "FAST")
    gl = {"failures": [], "continuous": {"measured_ii": 1}}
    entry = ppa.normalized_row(TABLE, spec, "passed", [], None, None, None, gl, None, None)
    assert entry["workload"] == TABLE["activity"]["workload"] and "257" not in entry["workload"]
    assert (entry["ii_cycles"], entry["effective_outputs_per_s"]) == (1, 1e8)


def test_a_failed_gate_level_run_marks_the_vector_status():
    spec = ppa.target_run(TABLE, "F-U4", "FAST")
    entry = ppa.normalized_row(TABLE, spec, "failed", ["gate-level"], None, None, None,
                               synthetic_gate_level("F-U4", ["block timing differs"]), None, None)
    assert entry["vector_status"] == "fail"


def test_rows_need_every_run_recorded_and_the_serial_baseline_is_f_serial(tmp_path):
    table = copy.deepcopy(TABLE)
    table["evidence_dirs"]["freq"] = str(tmp_path)
    with pytest.raises(ValueError, match="has no evidence"):
        ppa.rows(table, "freq")
    for row, target in RUNS:
        ppa.unrun(table, ppa.target_run(table, row, target), "not executed in this test")
    result = {entry["run_tag"]: entry for entry in ppa.rows(table, "freq")}
    assert sorted(result) == sorted(f"{r}-{t}" for r, t in RUNS)
    assert result["F-serial-SLOW"]["comparison_status"] == "serial-baseline"
    assert result["F-U8-FAST"]["comparison_status"] == "not-comparable"
    assert result["F-U4-FAST"]["serial_run_tag"] == "F-serial-FAST"
    assert list(result["F-U8-SLOW"]) == list(ppa.ROW_FIELDS)
    # The evidence names the frequency task, not the time one.
    record = json.loads((tmp_path / "F-U4" / "fast" / ppa.EVIDENCE_FILE).read_text(encoding="utf-8"))
    assert record["evidence_for"].startswith("T43 target run F-U4-FAST")


# Testbench and runner ------------------------------------------------------------------


@requires_icarus
@pytest.mark.parametrize("row,rtl_variant,parameters", [("F-serial", "freq_serial", None), ("F-U8", "freq_opt", {"U": 8})])
def test_slow_period_run_matches_and_dumps_the_whole_257_block_window(tmp_path, row, rtl_variant, parameters):
    staged = matching.stage(tmp_path / "vectors", row, "canonical", "none")
    capture, vcd = tmp_path / "captured.hex", tmp_path / "activity.vcd"
    result = subprocess.run(
        ["bash", str(ROOT / "rtl/run_variant.sh"), rtl_variant, "--vectors", str(staged),
         *matching.runner_arguments(parameters or {}), "--clock-period-ns", "100", "--capture", str(capture),
         "--activity-vcd", str(vcd)],
        cwd=ROOT, capture_output=True, text=True, timeout=900, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    report = matching.parse_report(result.stdout)
    continuous = report["continuous"]
    manifest = matching.load_matching(row, "canonical", "none")["manifest"]
    block = matching.expected_block_timing(manifest)
    assert (continuous["measured_ii"], continuous["measured_latency_cycles"], continuous["compared"]) == (
        "undefined", manifest["latency_cycles"], 2055)
    assert report["block_timing"]["blocks"] == 257 and report["block_timing"]["block_ii_min"] == BLOCK_II[row] == block["block_ii"]
    window = re.search(r"Activity window start_ns=(\S+) end_ns=(\S+) cycles=(\d+) period_ns=(\S+)", result.stdout)
    start, end, cycles, period = float(window.group(1)), float(window.group(2)), int(window.group(3)), float(window.group(4))
    assert (cycles, period) == (continuous["cycles"], 100.0)
    assert end - start == pytest.approx(cycles * period)
    summary = activity.vcd_to_saif(vcd, tmp_path / "activity.saif", window_ns=(start, end))
    assert summary["duration_ps"] == pytest.approx(cycles * 100000)


# Committed evidence --------------------------------------------------------------------


@pytest.mark.parametrize("row_id,target", RUNS)
def test_every_target_run_is_recorded_with_its_status(row_id, target):
    record = evidence(row_id, target)
    spec = ppa.target_run(TABLE, row_id, target)
    entry = record["row"]
    assert set(entry) == set(ppa.ROW_FIELDS)
    assert entry["run_status"] in ppa.STATUSES
    assert (entry["architecture"], entry["lane"], entry["U"], entry["S"]) == (row_id, "freq", FREQ_ROWS[row_id], None)
    assert (entry["target_class"], entry["target_role"], entry["clock_period_ns"]) == (
        target, spec["target_role"], spec["clock_period_ns"])
    assert (entry["run_tag"], entry["serial_run_tag"]) == (spec["run_tag"], spec["serial_run_tag"])
    assert record["evidence_for"].startswith("T43 target run")
    if entry["run_status"] != "passed":
        assert entry["failure_or_unrun_reason"]
    else:
        assert entry["failure_or_unrun_reason"] is None
        assert (entry["timing_status"], entry["vector_status"]) == ("met", "pass")
        assert entry["drc"] == entry["lvs"] == 0


@pytest.mark.parametrize("row_id,target", RUNS)
def test_unexecuted_runs_say_why_and_carry_no_measurement(row_id, target):
    entry = evidence(row_id, target)["row"]
    if entry["run_status"] == "unrun":
        assert entry["failure_or_unrun_reason"]
        assert entry["area_um2"] is None and entry["power_total"] is None and entry["timing_status"] == "not-run"


def test_every_main_target_run_is_recorded_executed_or_with_its_reason():
    for row_id in FREQ_ROWS:
        entry = evidence(row_id, MAIN[row_id])["row"]
        assert entry["run_status"] in ppa.STATUSES and entry["target_role"] == "main"
        if entry["run_status"] == "unrun":
            assert entry["failure_or_unrun_reason"]


def executed_runs():
    for row_id, target in RUNS:
        path = EVIDENCE / row_id / target.lower() / ppa.EVIDENCE_FILE
        if path.is_file() and json.loads(path.read_text(encoding="utf-8"))["row"]["run_status"] != "unrun":
            yield row_id, target


@pytest.mark.parametrize("row_id,target", list(executed_runs()))
def test_executed_runs_are_the_declared_target_runs_of_the_matched_rtl(row_id, target):
    record = evidence(row_id, target)
    spec = ppa.target_run(TABLE, row_id, target)
    out = EVIDENCE / row_id / target.lower()
    resolved = json.loads((out / "resolved.json").read_text(encoding="utf-8"))
    assert ppa._check_resolved(spec, resolved) == []
    clock, pnr, signoff_sdc = record["run"]["overrides"][:3]
    assert clock == f"CLOCK_PERIOD={spec['clock_period_ns']}"
    assert pnr.endswith("/" + spec["sdc"]) and signoff_sdc.endswith("/" + spec["sdc"])
    assert record["sdc_sha256"] == hashlib.sha256((ROOT / spec["sdc"]).read_bytes()).hexdigest()
    # Same RTL as the vector-matched rows (T33/T42 evidence): the five DUT sources have the hashes it recorded.
    snapshot = json.loads(MATCHING_EVIDENCE[row_id].read_text(encoding="utf-8"))["rtl_snapshot_sha256"]
    assert record["dut_sources_sha256"] == {path: snapshot[path] for path in record["dut_sources_sha256"]}
    assert len(record["dut_sources_sha256"]) == 5
    violations = record["signoff"]["antenna_violations"]
    assert len({item["net"] for item in violations}) == record["row"]["antenna"]
    assert all(item["partial"] > item["required"] for item in violations)
    assert hashlib.sha256((out / record["signoff"]["antenna_report"]).read_bytes()).hexdigest() == \
        record["signoff"]["antenna_report_sha256"]
    for name, digest in record["committed_reports_sha256"].items():
        compressed = name in record["compressed_reports"]
        assert compressed == (Path(name).name in ppa.COMPRESSED_REPORTS), name
        data = gzip.decompress((out / f"{name}.gz").read_bytes()) if compressed else (out / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        if compressed:
            assert not (out / name).exists(), name
    metrics = (["final/metrics.json", "final/metrics.csv"] if record["metrics_source"] == "final/metrics.json"
               else ["last-state/metrics.json"])
    for name in ("resolved.json", "openroad-stapostpnr/summary.rpt", *metrics):
        assert name in record["committed_reports_sha256"], name
    if record["metrics_source"] != "final/metrics.json":
        assert record["row"]["run_status"] == "failed" and record["run"]["exit_code"] != 0
    corners = {name.split("/")[1] for name in record["committed_reports_sha256"] if name.count("/") == 2}
    assert len(corners) == 9
    sizing = record["run"]["sizing"]
    assert sizing["floor_applied"] == (sizing["die_area_override"] is not None)


@pytest.mark.parametrize("row_id,target", list(executed_runs()))
def test_executed_rows_follow_from_their_reports_and_the_block_timing(row_id, target):
    record = evidence(row_id, target)
    entry = record["row"]
    out = EVIDENCE / row_id / target.lower()
    metrics = committed_metrics(row_id, target)
    period = entry["clock_period_ns"]
    timing = ppa.timing(metrics, period, TABLE["signoff"]["timing_corners"])
    assert entry["setup_ws_ns"] == timing["setup_ws_ns"] and entry["fmax_mhz"] == pytest.approx(timing["fmax_mhz"])
    assert entry["area_um2"] == metrics["design__instance__area"]
    assert entry["die_area_um2"] == metrics["design__die__area"]
    assert entry["utilization"] == metrics["design__instance__utilization"]
    gl = record["gate_level"]
    if entry["vector_status"] == "pass":
        ii = BLOCK_II[row_id]
        assert gl["continuous"]["measured_ii"] == "undefined"
        assert entry["ii_cycles"] == gl["block_timing"]["block_ii_min"] == gl["block_timing"]["block_ii_max"] == ii
        assert entry["samples_per_cycle"] == pytest.approx(8 / ii)
        assert entry["effective_outputs_per_s"] == pytest.approx(1e9 / period * 8 / ii)
        assert gl["continuous"]["compared"] == gl["robustness"]["compared"] == 2055
        assert gl["block_timing"]["blocks"] == 257
        manifest = matching.load_matching(row_id, "canonical", "none")["manifest"]
        assert gl["captured_output_sha256"] == manifest["hashes"]["expected_hex_sha256"]
    if entry["power_status"] in ("annotated", "partially-annotated"):
        power, window = record["power"], record["activity"]
        assert entry["activity_period_ns"] == window["period_ns"] == period
        # The window covers the 27 499 cycles of the whole 257-block frame at the run's period.
        assert window["cycles"] == gl["continuous"]["cycles"]
        assert window["duration_ps"] == window["cycles"] * period * 1000
        assert entry["power_per_valid_output"] == pytest.approx(entry["power_total"] / entry["effective_outputs_per_s"])
        assert power["unannotated_reproduces_openlane"]
        check = power["vcd_cross_check"]
        assert check["agrees"] or check.get("skipped")
        saif = out / window["file"]
        assert hashlib.sha256(saif.read_bytes()).hexdigest() == window["sha256"]
        annotated = ppa.parse_power_report((out / "power/power_annotated.rpt").read_text(encoding="utf-8"))
        assert entry["power_total"] == annotated["Total"]["total_w"]


def test_committed_rows_are_what_the_evidence_gives():
    committed = json.loads((EVIDENCE / "rows.json").read_text(encoding="utf-8"))
    assert committed["fields"] == list(ppa.ROW_FIELDS)
    assert committed["rows"] == json.loads(json.dumps(ppa.rows(TABLE, "freq")))


def test_each_optimized_row_compares_only_with_the_serial_at_its_own_target():
    committed = {entry["run_tag"]: entry for entry in json.loads((EVIDENCE / "rows.json").read_text())["rows"]}
    assert sorted(committed) == sorted(f"{r}-{t}" for r, t in RUNS)
    for run_tag, entry in committed.items():
        if entry["architecture"] == "F-serial":
            assert entry["comparison_status"] == "serial-baseline"
            continue
        assert entry["serial_run_tag"] == f"F-serial-{entry['target_class']}"
        assert entry["comparison_status"] in ("comparable", "not-comparable")
        if entry["comparison_status"] == "not-comparable":
            assert entry["throughput_delta"] is None and entry["comparison_reason"]
