"""T41 (#52): time-lane PPA target runs, their activity window and their committed evidence.

The run table (``openlane/ppa_runs.json``), the configs and the SDC pair must
resolve every row at both targets with nothing but the clock changing. The
activity window of the testbench becomes SAIF through ``ppa_activity.py``;
synthetic VCDs check that conversion. The committed evidence of the six time
target runs (executed or unrun) must agree with the table, with its own
OpenLane reports and with the T31/T40 matching evidence of the same RTL, and
``rows.json`` must be what ``ppa_stage.py rows`` computes from it. Standard
library only, so it runs in the RTL CI job without NumPy.
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
TIME_ROWS = {"T-serial": 1, "T-S4P1": 4, "T-S8P1": 8}
MAIN = {"T-serial": "SLOW", "T-S4P1": "FAST", "T-S8P1": "FAST"}
RUNS = [(row, target) for row in TIME_ROWS for target in ("SLOW", "FAST")]
EVIDENCE = ROOT / TABLE["evidence_dirs"]["time"]
MATCHING_EVIDENCE = {
    "T-serial": ROOT / "sim/python/artifacts/t31-time-matching/evidence_manifest.json",
    "T-S4P1": ROOT / "sim/python/artifacts/t40-time-opt-matching/T-S4P1/evidence_manifest.json",
    "T-S8P1": ROOT / "sim/python/artifacts/t40-time-opt-matching/T-S8P1/evidence_manifest.json",
}
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def sdc_body(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]


def evidence(row: str, target: str) -> dict:
    return json.loads((EVIDENCE / row / target.lower() / ppa.EVIDENCE_FILE).read_text(encoding="utf-8"))


def committed_metrics(row: str, target: str) -> dict:
    """The metrics a run ended with: ``final/metrics.json``, or the last state's when the flow wrote no ``final/``."""
    record = evidence(row, target)
    name = "final/metrics.json" if record["metrics_source"] == "final/metrics.json" else "last-state/metrics.json"
    return json.loads((EVIDENCE / row / target.lower() / name).read_text(encoding="utf-8"))


# Run table, configs and SDC ------------------------------------------------------


def test_the_two_sdc_files_differ_only_in_the_clock_period():
    fast, slow = (sdc_body(ROOT / TABLE["targets"][target]["sdc"]) for target in ("FAST", "SLOW"))
    assert len(fast) == len(slow)
    differing = [(a, b) for a, b in zip(fast, slow) if a != b]
    assert differing == [("create_clock -name clk -period 10.000 [get_ports clk]",
                          "create_clock -name clk -period 100.000 [get_ports clk]")]
    for target, clock in TABLE["targets"].items():
        period = re.search(r"-period (\S+)", "\n".join(sdc_body(ROOT / clock["sdc"]))).group(1)
        assert float(period) == clock["clock_period_ns"], target
    assert {name: clock["clock_period_ns"] for name, clock in TABLE["targets"].items()} == {"SLOW": 100.0, "FAST": 10.0}


@pytest.mark.parametrize("row", TIME_ROWS)
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
    # OpenLane only globs inside the design directory: the DUT files are named.
    assert not any("*" in entry for entry in config["VERILOG_FILES"])


@pytest.mark.parametrize("row,pes", TIME_ROWS.items())
def test_synthesis_parameters_are_the_rows_rtl_parameters(row, pes):
    entry = TABLE["rows"][row]
    manifest = matching.load_matching(row, TABLE["activity"]["vector_set"], TABLE["activity"]["vector_case"])["manifest"]
    assert entry["synth_parameters"] == manifest.get("rtl_parameters", {})
    assert entry["factors"] == {"S": pes, "P": 1}
    assert entry["serial"] == "T-serial" and entry["lane"] == "time"
    assert matching.expected_ii(manifest) == 8 // pes


@pytest.mark.parametrize("row", TIME_ROWS)
def test_the_two_targets_of_a_row_differ_only_in_the_clock(row):
    slow, fast = (ppa.overrides(ppa.target_run(TABLE, row, target)) for target in ("SLOW", "FAST"))
    as_dict = [dict(value.split("=", 1) for value in values) for values in (slow, fast)]
    allowed = {"CLOCK_PERIOD", "PNR_SDC_FILE", "SIGNOFF_SDC_FILE", "SYNTH_PARAMETERS"}
    assert set(as_dict[0]) == set(as_dict[1]) <= allowed
    changed = {key for key in as_dict[0] if as_dict[0][key] != as_dict[1][key]}
    assert changed == {"CLOCK_PERIOD", "PNR_SDC_FILE", "SIGNOFF_SDC_FILE"}
    expected = ",".join(f"{k}={v}" for k, v in sorted(TABLE["rows"][row]["synth_parameters"].items()))
    assert as_dict[0].get("SYNTH_PARAMETERS", "") == expected


def test_target_run_roles_tags_and_unknown_inputs():
    spec = ppa.target_run(TABLE, "T-S4P1", "SLOW")
    assert (spec["target_role"], spec["run_tag"], spec["serial_run_tag"]) == ("secondary", "T-S4P1-SLOW", "T-serial-SLOW")
    assert spec["evidence_dir"] == f"{TABLE['evidence_dirs']['time']}/T-S4P1/slow"
    assert ppa.target_run(TABLE, "T-serial", "SLOW")["target_role"] == "main"
    with pytest.raises(ValueError, match="unknown row"):
        ppa.target_run(TABLE, "T-S2P1", "FAST")
    with pytest.raises(ValueError, match="unknown target"):
        ppa.target_run(TABLE, "T-S4P1", "MEDIUM")


def test_the_die_floor_applies_per_side_only_under_it():
    floor = TABLE["sizing"]["die_floor_um"]
    assert ppa.die_floor([0, 0, 388.88, 399.6], floor) is None
    assert ppa.die_floor([0, 0, 150.0, 160.0], floor) == [0, 0, 200, 200]
    assert ppa.die_floor([0, 0, 190.0, 230.5], floor) == [0, 0, 200, 230.5]
    values = ppa.overrides(ppa.target_run(TABLE, "T-serial", "SLOW"), [0, 0, 200, 200])
    assert values[-2:] == ["FP_SIZING=absolute", "DIE_AREA=0 0 200 200"]


# Activity window to SAIF ----------------------------------------------------------


def write_vcd(path: Path, body: str, header_extra: str = "") -> Path:
    path.write_text(
        "$date\n\tsome day\n$end\n$timescale\n\t1ps\n$end\n"
        "$scope module rrc_stream_tb $end\n$var reg 1 ! clk_tb $end\n"
        "$scope module dut $end\n$var wire 1 \" clk $end\n$var wire 2 # sample_i [1:0] $end\n"
        "$var wire 1 $ \\esc[0] $end\n"
        "$scope module _1_ $end\n$var wire 1 \" CLK $end\n$var wire 1 % Q $end\n"
        "$scope module base $end\n$var wire 1 & hidden $end\n$upscope $end\n$upscope $end\n"
        f"{header_extra}$upscope $end\n$upscope $end\n$enddefinitions $end\n" + body,
        encoding="ascii")
    return path


WINDOW = """#0
$dumpvars
0!
1"
b0 #
0$
x%
0&
$end
#1000
0"
b10 #
0%
#2000
1"
1%
b1x #
#3000
0"
#4000
$dumpoff
x"
$end
"""


def saif_entries(path: Path) -> dict[str, dict[str, int]]:
    text = gzip.open(path, "rt").read() if path.suffix == ".gz" else path.read_text()
    owner, entries = None, {}
    for line in text.splitlines():
        if line.startswith("(INSTANCE "):
            owner = line.split()[1]
        match = re.fullmatch(r"\((\S+) \(T0 (\d+)\) \(T1 (\d+)\) \(TX (\d+)\) \(TC (\d+)\)\)", line)
        if match:
            name = match.group(1) if owner == "dut" else f"{owner}/{match.group(1)}"
            entries[name] = dict(zip(("T0", "T1", "TX", "TC"), map(int, match.groups()[1:])))
    return entries


def test_saif_holds_the_window_durations_and_transitions(tmp_path):
    vcd = write_vcd(tmp_path / "a.vcd", WINDOW.replace("#0\n", "#7000\n").replace("#1000", "#8000")
                    .replace("#2000", "#9000").replace("#3000", "#10000").replace("#4000", "#11000"))
    summary = activity.vcd_to_saif(vcd, tmp_path / "a.saif.gz", window_ns=(7.0, 11.0),
                                   window_vcd=tmp_path / "window.vcd")
    assert (summary["window_start_ps"], summary["window_end_ps"], summary["duration_ps"]) == (7000, 11000, 4000)
    entries = saif_entries(tmp_path / "a.saif.gz")
    assert "(DURATION 4000)" in gzip.open(tmp_path / "a.saif.gz", "rt").read()
    # clk: 1 for 1000, 0 for 1000, 1 for 1000, 0 for 1000; three 0/1 transitions.
    assert entries["clk"] == {"T0": 2000, "T1": 2000, "TX": 0, "TC": 3}
    # The cell pin aliases the same VCD code as the net.
    assert entries["_1_/CLK"] == entries["clk"]
    # Q starts at X: X->0 is not a 0/1 transition.
    assert entries["_1_/Q"] == {"T0": 1000, "T1": 2000, "TX": 1000, "TC": 1}
    # Bus bits: b0 -> b10 -> b1x (left-extended, MSB first).
    assert entries["sample_i[1]"] == {"T0": 1000, "T1": 3000, "TX": 0, "TC": 1}
    assert entries["sample_i[0]"] == {"T0": 2000, "T1": 0, "TX": 2000, "TC": 0}
    # Testbench signals and cell model internals stay out; escaped nets cannot be SAIF names.
    assert "clk_tb" not in entries and not any("hidden" in name for name in entries)
    assert summary["unrepresentable_names"] == ["\\esc[0]"]
    assert sorted(summary["written_names"]) == sorted(entries)
    # The window VCD starts at 0 and ends at the window length, without the $dumpoff block.
    shifted = (tmp_path / "window.vcd").read_text()
    assert [line for line in shifted.splitlines() if line.startswith("#")] == ["#0", "#1000", "#2000", "#3000", "#4000"]
    assert "$dumpoff" not in shifted and "$enddefinitions $end" in shifted


def test_saif_follows_opensta_saif_syntax(tmp_path):
    activity.vcd_to_saif(write_vcd(tmp_path / "a.vcd", WINDOW), tmp_path / "a.saif")
    text = (tmp_path / "a.saif").read_text()
    assert text.startswith('(SAIFILE\n(SAIFVERSION "2.0")\n(DIRECTION "backward")\n(DESIGN )\n')
    assert "(DIVIDER / )\n(TIMESCALE 1 ps)\n(DURATION 4000)\n(INSTANCE rrc_stream_tb\n(INSTANCE dut\n" in text
    assert text.count("(") == text.count(")")
    assert "(INSTANCE _1_\n(NET\n" in text


@pytest.mark.parametrize("edit,message", [
    (lambda body: body.replace("$dumpoff\nx\"\n$end\n", ""), "never closed"),
    (lambda body: body.replace("x%\n", ""), "no value at the window start"),
    (lambda body: body.replace("b10 #", "b110 #"), "does not fit"),
])
def test_conversion_refuses_a_broken_window(tmp_path, edit, message):
    with pytest.raises(ValueError, match=message):
        activity.vcd_to_saif(write_vcd(tmp_path / "a.vcd", edit(WINDOW)), tmp_path / "a.saif")


def test_conversion_refuses_a_window_other_than_the_reported_one(tmp_path):
    with pytest.raises(ValueError, match="differs from the reported"):
        activity.vcd_to_saif(write_vcd(tmp_path / "a.vcd", WINDOW), tmp_path / "a.saif", window_ns=(0.0, 5.0))


def test_conversion_refuses_another_timescale(tmp_path):
    vcd = write_vcd(tmp_path / "a.vcd", WINDOW)
    vcd.write_text(vcd.read_text().replace("\t1ps", "\t1ns"))
    with pytest.raises(ValueError, match="1 ps timescale"):
        activity.vcd_to_saif(vcd, tmp_path / "a.saif")


def test_bit_names_and_vector_expansion():
    assert activity.bit_names("a", 1, None) == ["a"]
    assert activity.bit_names("a", 1, "[3]") == ["a[3]"]
    assert activity.bit_names("a", 3, "[2:0]") == ["a[2]", "a[1]", "a[0]"]
    assert activity.bit_names("a", 3, "[0:2]") == ["a[0]", "a[1]", "a[2]"]
    with pytest.raises(ValueError):
        activity.bit_names("a", 4, "[2:0]")
    assert activity.expand("1", 4) == "0001"
    assert activity.expand("x1", 4) == "xxx1"
    assert activity.expand("Z", 2) == "zz"


# Committed OpenLane reports -------------------------------------------------------


def test_reports_are_copied_with_max_and_min_compressed_reproducibly(tmp_path):
    run_dir = tmp_path / "run"
    corner = run_dir / "54-openroad-stapostpnr" / "nom_tt_025C_1v80"
    corner.mkdir(parents=True)
    (run_dir / "final").mkdir()
    for name, text in (("resolved.json", "{}"), ("final/metrics.json", "{}"), ("final/metrics.csv", "a,b\n")):
        (run_dir / name).write_text(text)
    (corner.parent / "summary.rpt").write_text("summary\n")
    for name in ppa.CORNER_REPORTS:
        (corner / name).write_text(f"{name} body\n" * 1000)
    copies = []
    for attempt in ("a", "b"):
        out = tmp_path / attempt
        out.mkdir()
        copied = ppa._copy_reports(run_dir, out, None)
        copies.append((out / "openroad-stapostpnr/nom_tt_025C_1v80/max.rpt.gz").read_bytes())
    assert copies[0] == copies[1]
    assert set(copied) == {"resolved.json", "final/metrics.json", "final/metrics.csv", "openroad-stapostpnr/summary.rpt",
                           *(f"openroad-stapostpnr/nom_tt_025C_1v80/{name}" for name in ppa.CORNER_REPORTS)}
    for name in ppa.CORNER_REPORTS:
        report = f"openroad-stapostpnr/nom_tt_025C_1v80/{name}"
        original = (corner / name).read_bytes()
        assert copied[report] == hashlib.sha256(original).hexdigest()
        if name in ppa.COMPRESSED_REPORTS:
            assert gzip.decompress((out / f"{report}.gz").read_bytes()) == original
            assert not (out / report).exists()
        else:
            assert (out / report).read_bytes() == original


# Metrics, power reports and rows --------------------------------------------------


POWER_REPORT = """Group                    Internal    Switching      Leakage        Total
                            Power        Power        Power        Power (Watts)
------------------------------------------------------------------------
Sequential           2.0e-03 1.0e-04 1.0e-09 2.1e-03  40.0%
Combinational        1.0e-03 1.0e-03 1.0e-09 2.0e-03  38.0%
Clock                1.0e-03 1.5e-04 1.0e-09 1.15e-03  22.0%
Macro                0.000000e+00 0.000000e+00 0.000000e+00 0.000000e+00   0.0%
Pad                  0.000000e+00 0.000000e+00 0.000000e+00 0.000000e+00   0.0%
------------------------------------------------------------------------
Total                4.0e-03 1.25e-03 3.0e-09 5.25e-03 100.0%
                            76.2%        23.8%         0.0%
"""


def test_power_report_parsing():
    groups = ppa.parse_power_report(POWER_REPORT)
    assert groups["Total"] == {"internal_w": 4.0e-03, "switching_w": 1.25e-03, "leakage_w": 3.0e-09, "total_w": 5.25e-03}
    assert groups["Clock"]["total_w"] == 1.15e-03
    with pytest.raises(ValueError, match="no Total"):
        ppa.parse_power_report("nothing here")


def synthetic_metrics(ws: dict[str, float], hold: float = 0.3) -> dict:
    metrics = {}
    for corner, slack in ws.items():
        metrics.update({
            f"timing__setup__ws__corner:{corner}": slack,
            f"timing__setup__tns__corner:{corner}": min(slack, 0.0) * 3,
            f"timing__hold__ws__corner:{corner}": hold,
            f"timing__hold__tns__corner:{corner}": 0.0,
            f"timing__setup_vio__count__corner:{corner}": int(slack < 0),
            f"timing__hold_vio__count__corner:{corner}": 0,
        })
    return metrics


def test_timing_gates_on_the_signoff_corners_only():
    corners = TABLE["signoff"]["timing_corners"]
    metrics = synthetic_metrics({"nom_tt_025C_1v80": 0.135, "min_tt_025C_1v80": 0.221, "max_tt_025C_1v80": 0.023,
                                 "nom_ss_100C_1v60": -9.2})
    result = ppa.timing(metrics, 10.0, corners)
    assert result["status"] == "met"
    assert result["setup_ws_ns"] == 0.023
    assert result["fmax_mhz"] == pytest.approx(1000 / (10.0 - 0.023))
    # The slow corner is reported, not gated.
    assert result["per_corner"]["nom_ss_100C_1v60"]["fmax_mhz"] == pytest.approx(1000 / 19.2)
    failing = ppa.timing(synthetic_metrics({corner: -0.5 for corner in corners}), 10.0, corners)
    assert (failing["status"], failing["setup_tns_ns"]) == ("violated", -1.5)
    with pytest.raises(ValueError, match="no timing for the signoff corners"):
        ppa.timing(synthetic_metrics({"nom_tt_025C_1v80": 1.0}), 10.0, corners)


def test_signoff_gates_drc_and_lvs_and_records_antenna():
    clean = {"magic__drc_error__count": 0, "klayout__drc_error__count": 0, "route__drc_errors": 0,
             "design__lvs_error__count": 0, "antenna__violating__nets": 0, "antenna__violating__pins": 0}
    assert ppa.signoff(clean)["status"] == "clean"
    for name in ("magic__drc_error__count", "klayout__drc_error__count", "route__drc_errors",
                 "design__lvs_error__count"):
        assert ppa.signoff({**clean, name: 2})["status"] == "violated", name
    # Residual antenna nets are recorded for the timing review, not gated (2026-10-18).
    antenna = ppa.signoff({**clean, "antenna__violating__nets": 3, "antenna__violating__pins": 3})
    assert (antenna["status"], antenna["antenna"]) == ("clean", 3)


def test_antenna_report_rows_are_parsed_with_unescaped_names():
    report = """┏━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┓
┃ P / R ┃ Partial ┃ Required ┃ Net                     ┃ Pin       ┃ Layer ┃
┡━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━┩
│ 1.64  │ 656.67  │ 400.00   │ net198                  │ _6867_/A  │ met1  │
│ 1.03  │ 410.22  │ 400.00   │ g_pe[5\\].pe_next_q[20\\] │ _13139_/A │ met1  │
└───────┴─────────┴──────────┴─────────────────────────┴───────────┴───────┘
"""
    assert ppa.antenna_violations(report) == [
        {"ratio": 1.64, "partial": 656.67, "required": 400.0, "net": "net198", "pin": "_6867_/A", "layer": "met1"},
        {"ratio": 1.03, "partial": 410.22, "required": 400.0, "net": "g_pe[5].pe_next_q[20]", "pin": "_13139_/A",
         "layer": "met1"},
    ]
    assert ppa.antenna_violations("no table") == []


def test_synthesis_multiplier_count_reads_the_alumacc_pass():
    log = ("  creating $macc cell for $mul$/x/time_opt_filter.sv:118$345: $auto$alumacc.cc:365:replace_macc$689\n"
           "  creating $macc cell for $mul$/x/time_opt_filter.sv:119$346: $auto$alumacc.cc:365:replace_macc$690\n"
           "  creating $alu cell for $add$/x/rrc_pkg.sv:50$325: $auto$alumacc.cc:485:replace_alu$697\n")
    assert ppa.synthesis_multipliers(log) == 2
    # A product merged into the MAC adder is a $macc model, still one multiplier.
    merged = ("  creating $macc model for $mul$/x/time_serial_filter.sv:84$20 ($mul).\n"
              "  merging $macc model for $mul$/x/time_serial_filter.sv:84$20 into $add$/x/time_serial_filter.sv:91$26.\n")
    assert ppa.synthesis_multipliers(merged + log) == 3


def row(run_tag: str, status: str = "passed", throughput: float = 1.25e6, area: float = 20000.0,
        power: float = 1e-3, power_status: str = "annotated", period: float = 100.0) -> dict:
    return {"run_tag": run_tag, "run_status": status, "clock_period_ns": period, "effective_outputs_per_s": throughput,
            "area_um2": area, "power_status": power_status, "power_per_valid_output": power / throughput}


def test_a_comparable_pair_reports_signed_deltas():
    result = ppa.compare(row("T-S8P1-SLOW", throughput=1e7, area=70000.0, power=2e-3), row("T-serial-SLOW"), True)
    assert result["comparison_status"] == "comparable"
    assert result["throughput_delta"] == {"abs": 1e7 - 1.25e6, "pct": pytest.approx(700.0), "unit": "valid outputs/s"}
    assert result["area_delta"]["pct"] == pytest.approx(250.0)
    assert result["power_per_output_delta"]["abs"] == pytest.approx(2e-3 / 1e7 - 1e-3 / 1.25e6)
    assert result["power_per_output_delta"]["unit"] == "J/valid output"


@pytest.mark.parametrize("candidate,serial,same,reason", [
    (row("T-S4P1-FAST", period=10.0), row("T-serial-FAST", status="failed", period=10.0), True, "serial T-serial-FAST is failed"),
    (row("T-S4P1-FAST", period=10.0), row("T-serial-FAST", status="unrun", period=10.0), True, "is unrun"),
    (row("T-S4P1-FAST", status="failed", period=10.0), row("T-serial-FAST", period=10.0), True, "candidate"),
    (row("T-S4P1-SLOW"), row("T-serial-SLOW"), False, "flow, PDK or SDC differ"),
])
def test_failed_unrun_or_unmatched_pairs_are_not_comparable(candidate, serial, same, reason):
    result = ppa.compare(candidate, serial, same)
    assert result["comparison_status"] == "not-comparable"
    assert reason in result["comparison_reason"]
    assert result["throughput_delta"] is result["area_delta"] is result["power_per_output_delta"] is None


def test_missing_activity_makes_only_the_power_delta_not_comparable():
    result = ppa.compare(row("T-S4P1-SLOW"), row("T-serial-SLOW", power_status="partially-annotated"), True)
    assert result["comparison_status"] == "comparable"
    assert result["throughput_delta"] is not None
    assert result["power_per_output_delta"] == "not-comparable: annotated activity missing for T-serial-SLOW"


def test_comparisons_never_cross_targets():
    with pytest.raises(ValueError, match="same target"):
        ppa.compare(row("T-S4P1-FAST", period=10.0), row("T-serial-SLOW"), True)


def test_rows_need_every_run_recorded_and_unrun_needs_a_reason(tmp_path):
    table = copy.deepcopy(TABLE)
    table["evidence_dirs"]["time"] = str(tmp_path)
    with pytest.raises(ValueError, match="has no evidence"):
        ppa.rows(table, "time")
    with pytest.raises(ValueError, match="needs its reason"):
        ppa.unrun(table, ppa.target_run(table, "T-serial", "FAST"), " ")
    for run_row, target in RUNS:
        ppa.unrun(table, ppa.target_run(table, run_row, target), "not executed in this test")
    result = {entry["run_tag"]: entry for entry in ppa.rows(table, "time")}
    assert sorted(result) == sorted(f"{r}-{t}" for r, t in RUNS)
    assert all(entry["run_status"] == "unrun" for entry in result.values())
    assert result["T-serial-SLOW"]["comparison_status"] == "serial-baseline"
    assert result["T-S8P1-FAST"]["comparison_status"] == "not-comparable"
    assert result["T-S8P1-FAST"]["timing_status"] == result["T-S8P1-FAST"]["vector_status"] == "not-run"
    assert list(result["T-S4P1-SLOW"]) == list(ppa.ROW_FIELDS)


# Testbench and runner -------------------------------------------------------------


@requires_icarus
def test_slow_period_run_matches_and_dumps_a_whole_cycle_window(tmp_path):
    staged = matching.stage(tmp_path / "vectors", "T-serial", "canonical", "none")
    capture, vcd = tmp_path / "captured.hex", tmp_path / "activity.vcd"
    result = subprocess.run(
        ["bash", str(ROOT / "rtl/run_variant.sh"), "time_serial", "--vectors", str(staged),
         "--clock-period-ns", "100", "--capture", str(capture), "--activity-vcd", str(vcd)],
        cwd=ROOT, capture_output=True, text=True, timeout=600, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    report = matching.parse_report(result.stdout)
    continuous = report["continuous"]
    assert (continuous["measured_ii"], continuous["measured_latency_cycles"], continuous["compared"]) == (8, 9, 2055)
    assert capture.read_bytes() == (staged / "expected.hex").read_bytes()
    window = re.search(r"Activity window start_ns=(\S+) end_ns=(\S+) cycles=(\d+) period_ns=(\S+)", result.stdout)
    start, end, cycles, period = float(window.group(1)), float(window.group(2)), int(window.group(3)), float(window.group(4))
    assert (cycles, period) == (continuous["cycles"], 100.0)
    assert end - start == pytest.approx(cycles * period)
    summary = activity.vcd_to_saif(vcd, tmp_path / "activity.saif", window_ns=(start, end))
    clk = saif_entries(tmp_path / "activity.saif")["clk"]
    # The window opens just after a falling edge and closes before the next one.
    assert clk == {"T0": summary["duration_ps"] // 2, "T1": summary["duration_ps"] // 2, "TX": 0, "TC": 2 * cycles - 1}


@requires_icarus
def test_default_runs_keep_the_10ns_clock_and_dump_nothing(tmp_path):
    staged = matching.stage(tmp_path / "vectors", "T-S8P1", "canonical", "none")
    result = matching.run_matching("time_opt", staged, parameters={"SYSTOLIC_PES": 8, "PIPELINE_DEPTH": 1})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Activity window" not in result.stdout
    assert not list(tmp_path.rglob("*.vcd"))
    # 2057 cycles of the continuous run end at the same simulated time as before T41.
    assert "measured_ii=1" in result.stdout and "cycles=2057" in result.stdout


@pytest.mark.parametrize("arguments,message", [
    (["--clock-period-ns", "0"], "--clock-period-ns must be a positive number"),
    (["--clock-period-ns", "-10"], "--clock-period-ns must be a positive number"),
    (["--clock-period-ns", "fast"], "--clock-period-ns must be a positive number"),
    (["--netlist", "x.nl.v"], "--netlist needs --vectors and --cell-models"),
    (["--cell-models", "models"], "--cell-models applies only to --netlist"),
    (["--activity-vcd"], "Missing value for --activity-vcd"),
])
def test_runner_rejects_bad_ppa_arguments(tmp_path, arguments, message):
    result = subprocess.run(["bash", str(ROOT / "rtl/run_variant.sh"), "time_serial", *arguments],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert message in result.stderr


# Committed evidence ---------------------------------------------------------------


@pytest.mark.parametrize("row_id,target", RUNS)
def test_every_target_run_is_recorded_with_its_status(row_id, target):
    record = evidence(row_id, target)
    spec = ppa.target_run(TABLE, row_id, target)
    entry = record["row"]
    assert set(entry) == set(ppa.ROW_FIELDS)
    assert entry["run_status"] in ppa.STATUSES
    assert (entry["architecture"], entry["lane"], entry["S"], entry["P"]) == (row_id, "time", TIME_ROWS[row_id], 1)
    assert (entry["target_class"], entry["target_role"], entry["clock_period_ns"]) == (
        target, spec["target_role"], spec["clock_period_ns"])
    assert (entry["run_tag"], entry["serial_run_tag"]) == (spec["run_tag"], spec["serial_run_tag"])
    if entry["run_status"] != "passed":
        assert entry["failure_or_unrun_reason"]
    else:
        assert entry["failure_or_unrun_reason"] is None
        assert (entry["timing_status"], entry["vector_status"]) == ("met", "pass")
        assert entry["drc"] == entry["lvs"] == 0


@pytest.mark.parametrize("row_id", TIME_ROWS)
def test_every_main_target_run_was_executed(row_id):
    assert evidence(row_id, MAIN[row_id])["row"]["run_status"] in ("passed", "failed")


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
    # Same RTL as the vector-matched rows (T31/T40 evidence).
    snapshot = json.loads(MATCHING_EVIDENCE[row_id].read_text(encoding="utf-8"))["rtl_snapshot_sha256"]
    assert record["dut_sources_sha256"] == {path: snapshot[path] for path in record["dut_sources_sha256"]}
    assert len(record["dut_sources_sha256"]) == 3
    # Antenna is recorded per run, with the nets of OpenLane's post-route check.
    violations = record["signoff"]["antenna_violations"]
    assert len({item["net"] for item in violations}) == record["row"]["antenna"]
    # The report rounds the ratio to two decimals (401.68/400 prints 1.00), so check the areas.
    assert all(item["partial"] > item["required"] for item in violations)
    assert hashlib.sha256((out / record["signoff"]["antenna_report"]).read_bytes()).hexdigest() == \
        record["signoff"]["antenna_report_sha256"]
    # max.rpt/min.rpt are committed as gzip (D1); the hash is that of the report itself.
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
        # OpenLane writes no final/ when the flow ends with deferred errors: never a passed run.
        assert record["row"]["run_status"] == "failed" and record["run"]["exit_code"] != 0
    corners = {name.split("/")[1] for name in record["committed_reports_sha256"] if name.count("/") == 2}
    assert len(corners) == 9
    sizing = record["run"]["sizing"]
    assert sizing["floor_applied"] == (sizing["die_area_override"] is not None)


@pytest.mark.parametrize("row_id,target", list(executed_runs()))
def test_executed_rows_follow_from_their_reports(row_id, target):
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
        ii = 8 // TIME_ROWS[row_id]
        assert entry["ii_cycles"] == gl["continuous"]["measured_ii"] == ii
        assert entry["effective_outputs_per_s"] == pytest.approx(1e9 / period / ii)
        assert gl["continuous"]["compared"] == gl["robustness"]["compared"] == 2055
        manifest = matching.load_matching(row_id, "canonical", "none")["manifest"]
        assert gl["captured_output_sha256"] == manifest["hashes"]["expected_hex_sha256"]
    if entry["power_status"] == "annotated":
        power, window = record["power"], record["activity"]
        assert entry["activity_period_ns"] == window["period_ns"] == period
        assert window["duration_ps"] == window["cycles"] * period * 1000
        assert entry["power_per_valid_output"] == pytest.approx(entry["power_total"] / entry["effective_outputs_per_s"])
        assert entry["annotation_coverage"] >= TABLE["signoff"]["min_annotation_coverage"]
        assert power["unannotated_reproduces_openlane"] and power["vcd_cross_check"]["agrees"]
        saif = out / window["file"]
        assert hashlib.sha256(saif.read_bytes()).hexdigest() == window["sha256"]
        annotated = ppa.parse_power_report((out / "power/power_annotated.rpt").read_text(encoding="utf-8"))
        assert entry["power_total"] == annotated["Total"]["total_w"]


def test_committed_rows_are_what_the_evidence_gives():
    committed = json.loads((EVIDENCE / "rows.json").read_text(encoding="utf-8"))
    assert committed["fields"] == list(ppa.ROW_FIELDS)
    assert committed["rows"] == json.loads(json.dumps(ppa.rows(TABLE, "time")))


def test_each_optimized_row_compares_only_with_the_serial_at_its_own_target():
    committed = {entry["run_tag"]: entry for entry in json.loads((EVIDENCE / "rows.json").read_text())["rows"]}
    for run_tag, entry in committed.items():
        if entry["architecture"] == "T-serial":
            assert entry["comparison_status"] == "serial-baseline"
            continue
        assert entry["serial_run_tag"] == f"T-serial-{entry['target_class']}"
        assert entry["comparison_status"] in ("comparable", "not-comparable")
        if entry["comparison_status"] == "not-comparable":
            assert entry["throughput_delta"] is None and entry["comparison_reason"]
