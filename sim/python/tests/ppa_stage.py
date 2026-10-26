"""PPA target runs of the matrix rows (T41 #52 time, T43 #54 frequency): OpenLane, gate-level activity, annotated power and rows.

``openlane/ppa_runs.json`` declares every row (its OpenLane config, synthesis
parameters and main target) and the two targets. A target run is one row at
one target: the row's config with the target's ``CLOCK_PERIOD`` and SDC (the
two SDC files differ only in the period), the row's ``SYNTH_PARAMETERS`` and
the sizing rule, nothing else (ppa-matrix-18, Measurement Conditions).

``run``
    Floorplan pre-pass with the config's relative sizing (``FP_CORE_UTIL``).
    When the sized die is under the 200x200 um PDN floor (openlane-env-19) the
    run gets an absolute die of ``max(sized, floor)`` per side. Then the Classic
    flow, fresh, in ``.build/ppa/<row>/<target>/openlane``, timed.
``collect``
    The final netlist on the shared testbench at the run's period (canonical
    frame, every check of the RTL run, ``II = 8/S`` in the time lane or the
    block timing of the engine in the frequency lane, outputs equal to the
    expected codes), its activity window as SAIF (``ppa_activity.py``),
    OpenSTA power with that activity at the power corner
    (``openlane/scripts/annotated_power.tcl``), and the evidence in
    ``<evidence dir>/<row>/<target>/``: the OpenLane reports of the contract
    plus ``evidence_manifest.json`` with the run's normalized row.
``unrun``
    Records a target run that was not executed, with its reason.
``rows``
    Every row at every target, with deltas against the same-domain serial at
    the same target or ``not-comparable`` and the reason (``rows.json``,
    ``rows.csv`` next to the evidence).

OpenLane and OpenSTA run inside the OpenLane Nix shell (``--openlane-dir``).
Standard library only.
"""

import argparse
import csv
import datetime
import fnmatch
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppa_activity  # noqa: E402
import rtl_matching_stage as matching  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
TABLE = ROOT / "openlane" / "ppa_runs.json"
BUILD = ROOT / ".build" / "ppa"
# OpenSTA read_vcd keeps every value change in memory (about 11.5 bytes of RSS per VCD byte), so the VCD
# cross-check of the SAIF only runs on windows up to this size; the SAIF is the measurement either way.
VCD_CROSS_CHECK_MAX_BYTES = 150_000_000
POWER_SCRIPT = ROOT / "openlane" / "scripts" / "annotated_power.tcl"
NIX_BIN = "/nix/var/nix/profiles/default/bin"
EVIDENCE_FILE = "evidence_manifest.json"
SAIF_FILE = "activity.saif.gz"
STATUSES = ("passed", "failed", "unrun")
# Per-corner reports of the post-PnR STA step that the contract retains (openlane-env-19).
CORNER_REPORTS = ("max.rpt", "min.rpt", "checks.rpt", "power.rpt")
# Committed gzip-compressed, byte-for-byte (D1, approved 2026-10-18): 4-7 MB each per corner.
COMPRESSED_REPORTS = ("max.rpt", "min.rpt")
POWER_GROUPS = ("Sequential", "Combinational", "Clock", "Macro", "Pad", "Total")
# Normalized Row of ppa-matrix-18, in its order.
ROW_FIELDS = (
    "lane", "architecture", "S", "P", "U", "F", "fft_n", "hop",
    "clock_target", "clock_period_ns", "target_class", "target_role", "corner", "workload",
    "run_status", "failure_or_unrun_reason", "timing_status", "vector_status",
    "area_um2", "die_area_um2", "core_area_um2", "utilization",
    "setup_ws_ns", "setup_tns_ns", "hold_ws_ns", "hold_tns_ns", "fmax_mhz", "ii_cycles", "samples_per_cycle",
    "effective_outputs_per_s", "power_total", "power_status", "power_per_valid_output",
    "activity_file", "activity_period_ns", "annotation_coverage",
    "drc", "lvs", "antenna", "run_tag", "serial_run_tag", "comparison_status",
    "comparison_reason", "throughput_delta", "area_delta", "power_per_output_delta",
)
DELTA_CONVENTION = ("candidate minus same-target serial; higher throughput is better, lower area and lower "
                    "energy per valid output are better")
_MEMORY_UNITS = {"B": 1, "KiB": 2 ** 10, "MiB": 2 ** 20, "GiB": 2 ** 30, "TiB": 2 ** 40}
_ACTIVITY_WINDOW = re.compile(r"^Activity window start_ns=(\S+) end_ns=(\S+) cycles=(\d+) period_ns=(\S+)$", re.M)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _repo_path(path: Path) -> str:
    return str(Path(path).resolve().relative_to(ROOT))


# Run table -------------------------------------------------------------------


def load_table(path: Path = TABLE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def target_run(table: dict, row: str, target: str) -> dict:
    """Return one row at one target as resolved from the table."""
    if row not in table["rows"]:
        raise ValueError(f"unknown row {row}; the table has {sorted(table['rows'])}")
    if target not in table["targets"]:
        raise ValueError(f"unknown target {target}; the table has {sorted(table['targets'])}")
    entry, clock = table["rows"][row], table["targets"][target]
    return {
        "row": row,
        "target": target,
        "lane": entry["lane"],
        "rtl_variant": entry["rtl_variant"],
        "config": entry["config"],
        "factors": entry["factors"],
        "synth_parameters": entry["synth_parameters"],
        "target_role": "main" if target == entry["main_target"] else "secondary",
        "clock_target": clock["clock_target"],
        "clock_period_ns": clock["clock_period_ns"],
        "sdc": clock["sdc"],
        "run_tag": f"{row}-{target}",
        "serial": entry["serial"],
        "serial_run_tag": f"{entry['serial']}-{target}",
        "evidence_dir": f"{table['evidence_dirs'][entry['lane']]}/{row}/{target.lower()}",
    }


def overrides(spec: dict, die_area: list[float] | None = None) -> list[str]:
    """Return the OpenLane ``-c`` overrides of a target run; the row's config supplies everything else."""
    sdc = ROOT / spec["sdc"]
    values = [f"CLOCK_PERIOD={spec['clock_period_ns']}", f"PNR_SDC_FILE={sdc}", f"SIGNOFF_SDC_FILE={sdc}"]
    if spec["synth_parameters"]:
        values.append("SYNTH_PARAMETERS=" + ",".join(
            f"{name}={value}" for name, value in sorted(spec["synth_parameters"].items())))
    if die_area is not None:
        values += ["FP_SIZING=absolute", "DIE_AREA=" + " ".join(f"{value:g}" for value in die_area)]
    return values


def die_floor(bbox: list[float], floor: list[float]) -> list[float] | None:
    """Return the absolute ``DIE_AREA`` when the sized die is under the floor, else None (keep it)."""
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if width >= floor[0] and height >= floor[1]:
        return None
    return [0, 0, max(width, floor[0]), max(height, floor[1])]


# OpenLane --------------------------------------------------------------------


def _nix_shell(openlane_dir: Path, command: str, log: Path) -> int:
    """Run ``command`` in the OpenLane Nix shell, output to ``log``; return its exit code."""
    env = {**os.environ, "PATH": f"{NIX_BIN}:{os.environ.get('PATH', '')}"}
    with open(log, "w", encoding="utf-8") as stream:
        return subprocess.run(["nix-shell", "--pure", "shell.nix", "--run", command], cwd=openlane_dir,
                              env=env, stdout=stream, stderr=subprocess.STDOUT, check=False).returncode


def openlane_arguments(table: dict, spec: dict, run_dir: Path, values: list[str], to: str | None = None) -> list[str]:
    """Return the OpenLane command line of a target run (or of its pre-pass up to ``to``)."""
    arguments = ["openlane", "--pdk", table["pdk"], "--scl", table["scl"], "--flow", table["flow"],
                 "--force-run-dir", str(run_dir)]
    if to is not None:
        arguments += ["--to", to]
    for value in values:
        arguments += ["-c", value]
    return arguments + [str(ROOT / spec["config"])]


def final_state(run_dir: Path) -> dict | None:
    """The views and metrics a run ended with: ``final/`` or, without it, the last step's state.

    A flow that ends with deferred errors (a failed checker such as setup
    violations at the signoff corners) runs every step but writes no
    ``final/``; its last ``state_out.json`` holds the same views and metrics.
    """
    steps = sorted(run_dir.glob("[0-9]*-*/state_out.json"), key=lambda path: int(path.parent.name.split("-")[0]))
    if not steps:
        return None
    state = json.loads(steps[-1].read_text(encoding="utf-8"))
    final = run_dir / "final" / "metrics.json"
    if final.is_file():
        source, metrics = "final/metrics.json", json.loads(final.read_text(encoding="utf-8"))
    else:
        source, metrics = f"{steps[-1].parent.name}/state_out.json (no final/)", state["metrics"]
    return {"source": source, "metrics": metrics, "nl": Path(state["nl"]), "spef": state["spef"]}


def _step_dir(run_dir: Path, step: str) -> Path | None:
    """Return the directory of the last step named ``step`` (``NN-<step>``), or None."""
    matches = sorted(run_dir.glob(f"[0-9]*-{step}"), key=lambda path: int(path.name.split("-")[0]))
    return matches[-1] if matches else None


def _memory_bytes(text: str) -> float:
    match = re.fullmatch(r"([0-9.]+)\s*([KMGT]?i?B)", text)
    if match is None:
        raise ValueError(f"unknown memory size {text!r}")
    return float(match.group(1)) * _MEMORY_UNITS[match.group(2)]


def resource_use(run_dir: Path) -> dict:
    """Peak memory and summed step runtimes of an OpenLane run, from its ``*.process_stats.json``."""
    peak, step, runtime = 0.0, None, 0.0
    for stats_file in sorted(run_dir.rglob("*.process_stats.json")):
        stats = json.loads(stats_file.read_text(encoding="utf-8"))
        rss = _memory_bytes(stats["peak_resources"]["memory_rss"])
        if rss > peak:
            peak, step = rss, str(stats_file.parent.relative_to(run_dir))
    for runtime_file in run_dir.glob("[0-9]*-*/runtime.txt"):
        hours, minutes, seconds = runtime_file.read_text(encoding="utf-8").strip().split(":")
        runtime += int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return {"peak_rss_mib": round(peak / 2 ** 20, 1), "peak_rss_step": step, "summed_step_runtime_s": round(runtime, 1)}


def run(table: dict, spec: dict, openlane_dir: Path) -> Path:
    """Floorplan pre-pass for the die floor, then the full Classic flow; write ``run.json``."""
    base = BUILD / spec["row"] / spec["target"].lower()
    if base.exists():
        shutil.rmtree(base)
    floorplan = base / "floorplan"
    floorplan.mkdir(parents=True)
    pre_values = overrides(spec)
    pre_command = shlex.join(openlane_arguments(table, spec, floorplan, pre_values, to="OpenROAD.Floorplan"))
    clock = time.monotonic()
    if _nix_shell(openlane_dir, pre_command, base / "floorplan.stdout") != 0:
        raise RuntimeError(f"floorplan pre-pass failed, see {base / 'floorplan.stdout'}")
    step = _step_dir(floorplan, "openroad-floorplan")
    metrics = json.loads((step / "state_out.json").read_text(encoding="utf-8"))["metrics"]
    sized = [float(value) for value in metrics["design__die__bbox"].split()]
    prepass_s = round(time.monotonic() - clock, 1)
    die_area = die_floor(sized, table["sizing"]["die_floor_um"])
    values = overrides(spec, die_area)
    run_dir = base / "openlane"
    run_dir.mkdir()
    command = shlex.join(openlane_arguments(table, spec, run_dir, values))
    started, clock = _now(), time.monotonic()
    exit_code = _nix_shell(openlane_dir, command, base / "openlane.stdout")
    record = {
        "row": spec["row"],
        "target": spec["target"],
        "run_tag": spec["run_tag"],
        "openlane_command": command,
        "overrides": values,
        "sizing": {
            "rule": "relative sizing at FP_CORE_UTIL; absolute max(sized, floor) per side under the PDN floor",
            "FP_CORE_UTIL": table["sizing"]["FP_CORE_UTIL"],
            "sized_die_bbox_um": sized,
            "sized_instance_utilization": metrics["design__instance__utilization"],
            "die_floor_um": table["sizing"]["die_floor_um"],
            "floor_applied": die_area is not None,
            "die_area_override": die_area,
            "prepass_wall_time_s": prepass_s,
        },
        "started": started,
        "finished": _now(),
        "wall_time_s": round(time.monotonic() - clock, 1),
        "exit_code": exit_code,
        "machine": {"cpus": os.cpu_count(), "memory_gib": _machine_memory_gib()},
        "resources": resource_use(run_dir),
    }
    _write_json(base / "run.json", record)
    return base / "run.json"


def _machine_memory_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 2 ** 20, 1)
    except OSError:
        return None
    return None


# Metrics and reports ---------------------------------------------------------


def timing(metrics: dict, period_ns: float, corners: list[str]) -> dict:
    """Setup/hold slack at the signoff corners, their worst values and fmax from the worst setup slack."""
    per_corner = {}
    for corner in sorted({key.split("corner:")[1] for key in metrics if key.startswith("timing__setup__ws__corner:")}):
        ws = metrics[f"timing__setup__ws__corner:{corner}"]
        per_corner[corner] = {
            "setup_ws_ns": ws,
            "setup_tns_ns": metrics[f"timing__setup__tns__corner:{corner}"],
            "hold_ws_ns": metrics[f"timing__hold__ws__corner:{corner}"],
            "hold_tns_ns": metrics[f"timing__hold__tns__corner:{corner}"],
            "setup_violations": metrics[f"timing__setup_vio__count__corner:{corner}"],
            "hold_violations": metrics[f"timing__hold_vio__count__corner:{corner}"],
            "fmax_mhz": 1000.0 / (period_ns - ws),
        }
    missing = sorted(set(corners) - set(per_corner))
    if missing:
        raise ValueError(f"metrics.json has no timing for the signoff corners {missing}")
    signoff = [per_corner[corner] for corner in corners]
    worst = {name: min(corner[name] for corner in signoff)
             for name in ("setup_ws_ns", "setup_tns_ns", "hold_ws_ns", "hold_tns_ns")}
    return {
        "signoff_corners": corners,
        **worst,
        "fmax_mhz": 1000.0 / (period_ns - worst["setup_ws_ns"]),
        "fmax_rule": "1000 / (CLOCK_PERIOD - worst signed setup slack at the signoff corners)",
        "status": "met" if worst["setup_ws_ns"] >= 0 and worst["hold_ws_ns"] >= 0 else "violated",
        "per_corner": per_corner,
    }


def signoff(metrics: dict) -> dict:
    """Physical signoff counts; the gate is DRC and LVS at zero.

    Residual antenna nets are recorded, not gated: the lane owner took antenna
    out of the T41 gates on 2026-10-18 and left it to the timing review (T44).
    """
    drc = {name: metrics[name] for name in ("magic__drc_error__count", "klayout__drc_error__count", "route__drc_errors")}
    lvs = metrics["design__lvs_error__count"]
    antenna = {name: metrics[name] for name in ("antenna__violating__nets", "antenna__violating__pins")}
    diagnostics = {name: metrics.get(name) for name in (
        "design__xor_difference__count", "magic__illegal_overlap__count", "design__power_grid_violation__count",
        "design__disconnected_pin__count", "design__max_slew_violation__count", "design__max_cap_violation__count",
        "design__max_fanout_violation__count", "route__antenna_violation__count")}
    return {
        "drc": sum(drc.values()),
        "drc_counts": drc,
        "lvs": lvs,
        "antenna": antenna["antenna__violating__nets"],
        "antenna_counts": antenna,
        "diagnostics": diagnostics,
        "status": "clean" if sum(drc.values()) == 0 and lvs == 0 else "violated",
        "antenna_status": "reported, not gated: pending the timing review (T44)",
    }


def antenna_violations(text: str) -> list[dict]:
    """Rows of OpenLane's post-route ``antenna_summary.rpt``: ratio, partial and required area, net, pin, layer."""
    rows = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("│").split("│")]
        if len(cells) == 6:
            try:
                ratio, partial, required = (float(value) for value in cells[:3])
            except ValueError:
                continue
            net, pin, layer = (cell.replace("\\", "") for cell in cells[3:])
            rows.append({"ratio": ratio, "partial": partial, "required": required, "net": net, "pin": pin,
                         "layer": layer})
    return rows


def parse_power_report(text: str) -> dict:
    """Return internal/switching/leakage/total power in W per group of an OpenSTA ``report_power``."""
    groups = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0] in POWER_GROUPS:
            try:
                groups[fields[0]] = dict(zip(("internal_w", "switching_w", "leakage_w", "total_w"),
                                             map(float, fields[1:5])))
            except ValueError:
                continue
    if "Total" not in groups:
        raise ValueError("report_power output has no Total row")
    return groups


def synthesis_multipliers(log: str) -> int:
    """Count the multipliers Yosys still had at its ALUMACC pass (one ``$macc`` cell or model per ``$mul``)."""
    return len(set(re.findall(r"creating \$macc (?:cell|model) for (\$mul\$\S+?\.sv:\d+\$\d+)", log)))


# Gate-level simulation and power ---------------------------------------------


def gate_level(spec: dict, resolved: dict, netlist: Path, base: Path, table: dict) -> dict:
    """Run the netlist on the canonical frame at the run's period, with the activity window dump."""
    activity = table["activity"]
    frame = matching.load_matching(spec["row"], activity["vector_set"], activity["vector_case"])
    manifest = frame["manifest"]
    if manifest.get("rtl_parameters", {}) != spec["synth_parameters"]:
        raise ValueError(f"{spec['row']}: rtl_parameters {manifest.get('rtl_parameters')} differ from the table")
    gl = base / "gl"
    if gl.exists():
        shutil.rmtree(gl)
    staged = matching.stage(gl / "vectors", spec["row"], activity["vector_set"], activity["vector_case"])
    models = sorted({Path(path).parent for path in resolved["CELL_VERILOG_MODELS"]})
    if len(models) != 1:
        raise ValueError(f"cell Verilog models in more than one directory: {models}")
    capture, vcd = gl / matching.CAPTURE_FILE, gl / "activity.vcd"
    arguments = ["--vectors", str(staged), *matching.runner_arguments(manifest.get("rtl_parameters", {})),
                 "--clock-period-ns", f"{spec['clock_period_ns']:g}", "--netlist", str(netlist),
                 "--cell-models", str(models[0]), "--capture", str(capture), "--activity-vcd", str(vcd)]
    env = {key: value for key, value in os.environ.items() if key != "LD_LIBRARY_PATH"}
    started = time.monotonic()
    result = subprocess.run(["bash", str(ROOT / "rtl" / "run_variant.sh"), spec["rtl_variant"], *arguments],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=6 * 3600, check=False)
    log = result.stdout + result.stderr
    (gl / "gate_level.log").write_text(log, encoding="utf-8")
    outcome = {"command": ["rtl/run_variant.sh", spec["rtl_variant"], *[_display_path(item) for item in arguments]],
               "netlist_sha256": _file_sha256(netlist), "wall_time_s": round(time.monotonic() - started, 1),
               "log_sha256": _sha256(log.encode("utf-8")), "expected_ii": matching.expected_ii(manifest),
               "expected_block_timing": matching.expected_block_timing(manifest),
               "testbench_sha256": {name: _file_sha256(ROOT / name)
                                    for name in ("rtl/tb/rrc_stream_tb.sv", "rtl/run_variant.sh")},
               "declared_latency_cycles": manifest["latency_cycles"], "failures": []}
    report = matching.parse_report(result.stdout)
    window = _ACTIVITY_WINDOW.search(result.stdout)
    if result.returncode != 0 or "pass" not in report:
        fatal = [line for line in log.splitlines() if "FATAL" in line.upper() or "error" in line.lower()]
        outcome["failures"].append("gate-level testbench failed: " + (fatal[0] if fatal else f"exit {result.returncode}"))
        return outcome
    continuous = report["continuous"]
    outcome.update({"pass_line": report["pass"], "continuous": continuous, "robustness": report["robustness"],
                    "midtraffic_reset": report["midtraffic_reset"]})
    if continuous["measured_latency_cycles"] != manifest["latency_cycles"]:
        outcome["failures"].append("measured latency differs from the rtl_matching manifest")
    block = outcome["expected_block_timing"]
    if block is None:
        if continuous["measured_ii"] != outcome["expected_ii"]:
            outcome["failures"].append(f"measured II {continuous['measured_ii']} is not {outcome['expected_ii']}")
    else:
        # The block engines have no per-sample II: the block II, the fill and the tail are the row's identity.
        wanted = {"blocks": block["blocks"], "block_ii_count": block["block_ii_count"], "block_ii_min": block["block_ii"],
                  "block_ii_max": block["block_ii"], "fill_latency_cycles": block["fill_latency_cycles"],
                  "tail_latency_cycles": block["tail_latency_cycles"],
                  "source_tail_latency_cycles": block["source_tail_latency_cycles"]}
        measured = {name: (report.get("block_timing") or {}).get(name) for name in wanted}
        outcome["block_timing"] = report.get("block_timing")
        if measured != wanted:
            outcome["failures"].append(f"block timing {measured} is not {wanted}")
    outcome["captured_output_sha256"] = _file_sha256(capture)
    # As in rtl_matching_stage: only the records of the valid window are expected codes; any others are the
    # declared block padding (the last frequency output), recorded in the capture but never compared.
    records = capture.read_text(encoding="ascii").split()
    first = manifest["valid_start"] - manifest["latency_samples"]
    window_records = records[first:first + manifest["valid_len"]]
    window_sha256 = _sha256(("\n".join(window_records) + "\n").encode("ascii"))
    if len(records) != manifest["raw_output_samples"]:
        outcome["failures"].append(f"{len(records)} captured gate-level outputs, {manifest['raw_output_samples']} declared")
    elif window_sha256 != manifest["hashes"]["expected_hex_sha256"]:
        outcome["failures"].append("captured gate-level outputs differ from the bound expected codes")
    if window is None:
        outcome["failures"].append("the testbench reported no activity window")
        return outcome
    start_ns, end_ns, cycles, period_ns = (float(window.group(1)), float(window.group(2)), int(window.group(3)),
                                           float(window.group(4)))
    if period_ns != spec["clock_period_ns"] or cycles != continuous["cycles"]:
        outcome["failures"].append("activity window period or cycles differ from the run")
    outcome["window"] = {"start_ns": start_ns, "end_ns": end_ns, "cycles": cycles, "period_ns": period_ns}
    outcome["vcd"] = vcd
    return outcome


def _display_path(item: str) -> str:
    path = Path(item)
    if path.is_absolute():
        try:
            return _repo_path(path)
        except ValueError:
            return item
    return item


def annotated_power(table: dict, resolved: dict, state: dict, base: Path, saif: Path, window_vcd: Path | None,
                    openlane_dir: Path) -> dict:
    """OpenSTA power at the power corner: unannotated, with the SAIF and, when given, with the window VCD (cross-check)."""
    corner = table["signoff"]["power_corner"]
    top = resolved["DESIGN_NAME"]
    libs = [lib for pattern, files in resolved["LIB"].items() if fnmatch.fnmatch(corner, pattern) for lib in files]
    if not libs:
        raise ValueError(f"no liberty for {corner} in resolved.json")
    out = base / "power"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rc = corner.split("_")[0]
    spef = [Path(path) for pattern, paths in state["spef"].items() if fnmatch.fnmatch(corner, pattern)
            for path in ([paths] if isinstance(paths, str) else paths)]
    if len(spef) != 1:
        raise ValueError(f"expected one SPEF for {corner}, got {spef}")
    inputs = {
        "top": top,
        "corner": corner,
        "libs": libs,
        "netlist": str(state["nl"]),
        "spef": str(spef[0]),
        "sdc": resolved["SIGNOFF_SDC_FILE"],
        "saif": str(saif),
        "scope": table["activity"]["scope"],
        "out": str(out),
    }
    if window_vcd is not None:
        inputs["vcd"] = str(window_vcd)
    lines = [f"set ppa({name}) {{{' '.join(value) if isinstance(value, list) else value}}}"
             for name, value in inputs.items()]
    lines.append(f"source {{{POWER_SCRIPT}}}")
    (out / "run.tcl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = f"sta -version > {shlex.quote(str(out / 'sta_version.txt'))} && " \
              f"sta -no_splash -exit {shlex.quote(str(out / 'run.tcl'))}"
    exit_code = _nix_shell(openlane_dir, command, out / "sta.log")
    if exit_code != 0:
        raise RuntimeError(f"OpenSTA failed, see {out / 'sta.log'}")
    directions = dict(line.split() for line in (out / "pins.txt").read_text(encoding="utf-8").splitlines())
    vcd_annotated = re.search(r"^Annotated (\d+) pin activities\.$", (out / "sta.log").read_text(encoding="utf-8"),
                              re.M)
    return {
        "corner": corner,
        "liberty": [Path(lib).name for lib in libs],
        "spef": f"{spef[0].parent.parent.name}/{rc}/{spef[0].name}",
        "netlist": f"{state['nl'].parent.name}/{state['nl'].name}",
        "sta_version": (out / "sta_version.txt").read_text(encoding="utf-8").strip(),
        "unannotated": parse_power_report((out / "power_unannotated.rpt").read_text(encoding="utf-8")),
        "annotated": parse_power_report((out / "power_annotated.rpt").read_text(encoding="utf-8")),
        "vcd_check": parse_power_report((out / "power_vcd_check.rpt").read_text(encoding="utf-8"))
        if window_vcd is not None else None,
        "vcd_annotated_pins": int(vcd_annotated.group(1)) if vcd_annotated else None,
        # Liberty internal pins (a flop's IQ/IQ_N state) are no netlist ports and get no activity.
        "pins": {name for name, direction in directions.items() if direction != "internal"},
        "internal_pins": sum(direction == "internal" for direction in directions.values()),
        "out": out,
    }


# Collect ---------------------------------------------------------------------


def _check_resolved(spec: dict, resolved: dict) -> list[str]:
    """Return how the resolved configuration differs from the target run it claims to be."""
    problems = []
    if float(resolved["CLOCK_PERIOD"]) != spec["clock_period_ns"]:
        problems.append(f"CLOCK_PERIOD {resolved['CLOCK_PERIOD']} is not {spec['clock_period_ns']}")
    # resolved.json holds absolute paths of the machine that ran the flow.
    for name in ("PNR_SDC_FILE", "SIGNOFF_SDC_FILE"):
        if not resolved[name].endswith("/" + spec["sdc"]):
            problems.append(f"{name} is {resolved[name]}, not {spec['sdc']}")
    wanted = sorted(f"{name}={value}" for name, value in spec["synth_parameters"].items())
    if sorted(resolved.get("SYNTH_PARAMETERS") or []) != wanted:
        problems.append(f"SYNTH_PARAMETERS {resolved.get('SYNTH_PARAMETERS')} are not {wanted}")
    config = json.loads((ROOT / spec["config"]).read_text(encoding="utf-8"))
    if resolved["DESIGN_NAME"] != config["DESIGN_NAME"]:
        problems.append(f"DESIGN_NAME {resolved['DESIGN_NAME']} is not {config['DESIGN_NAME']}")
    return problems


def _copy_reports(run_dir: Path, out: Path, state: dict | None) -> dict[str, str]:
    """Copy the contract's OpenLane evidence of one run into ``out``; return path -> SHA-256 of its content.

    ``max.rpt`` and ``min.rpt`` are stored as ``<name>.gz`` (gzip, no timestamp)
    and keep the SHA-256 of the uncompressed report. Without ``final/`` the
    metrics of the last state go to ``last-state/metrics.json``, never to the
    contract's ``final/`` paths.
    """
    copied = {}
    if state is not None and not (run_dir / "final" / "metrics.json").is_file():
        target = out / "last-state" / "metrics.json"
        target.parent.mkdir(parents=True)
        _write_json(target, state["metrics"])
        copied["last-state/metrics.json"] = _file_sha256(target)
    sources = [("resolved.json", run_dir / "resolved.json"),
               ("final/metrics.json", run_dir / "final" / "metrics.json"),
               ("final/metrics.csv", run_dir / "final" / "metrics.csv")]
    sta = _step_dir(run_dir, "openroad-stapostpnr")
    if sta is not None:
        sources.append(("openroad-stapostpnr/summary.rpt", sta / "summary.rpt"))
        for corner in sorted(path.name for path in sta.iterdir() if path.is_dir()):
            sources += [(f"openroad-stapostpnr/{corner}/{name}", sta / corner / name) for name in CORNER_REPORTS]
    for name, source in sources:
        if source.is_file():
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.name in COMPRESSED_REPORTS:
                data = source.read_bytes()
                target.with_name(target.name + ".gz").write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
                copied[name] = _sha256(data)
            else:
                shutil.copyfile(source, target)
                copied[name] = _file_sha256(target)
    # Logs stay out of git (*.log) but next to the evidence, as in T31/T40.
    for name in ("flow.log", "error.log", "warning.log"):
        if (run_dir / name).is_file():
            shutil.copyfile(run_dir / name, out / f"openlane-{name}")
    return copied


def _openlane_errors(run_dir: Path) -> list[str]:
    error_log = run_dir / "error.log"
    if not error_log.is_file():
        return []
    return [line.strip() for line in error_log.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()][:20]


def _dut_sources(resolved: dict) -> dict[str, str]:
    return {_repo_path(Path(path)): _file_sha256(Path(path)) for path in resolved["VERILOG_FILES"]}


def collect(table: dict, spec: dict, openlane_dir: Path, keep_vcd: bool = False,
            skip_activity: str | None = None) -> Path:
    """Gate-level activity, annotated power and the committed evidence of one executed target run.

    ``skip_activity`` (a reason) records the flow's reports without the gate-level run and the power: the
    row then has ``vector_status`` and ``power_status`` ``not-run`` and the reason.
    """
    base = BUILD / spec["row"] / spec["target"].lower()
    record = json.loads((base / "run.json").read_text(encoding="utf-8"))
    run_dir = base / "openlane"
    out = ROOT / spec["evidence_dir"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    resolved = json.loads((run_dir / "resolved.json").read_text(encoding="utf-8"))
    mismatch = _check_resolved(spec, resolved)
    if mismatch:
        raise ValueError(f"{run_dir} is not the run of {spec['run_tag']}: {mismatch}")
    state = final_state(run_dir)
    copied = _copy_reports(run_dir, out, state)
    reasons = []
    if record["exit_code"] != 0:
        errors = _openlane_errors(run_dir)
        reasons.append(f"OpenLane exited {record['exit_code']}" + (f": {errors[0]}" if errors else ""))
    metrics = state["metrics"] if state is not None else None
    evidence = {
        "evidence_for": f"{table['tasks'][spec['lane']]} target run {spec['run_tag']} "
                        f"({spec['target_role']} target of {spec['row']})",
        "run_tag": spec["run_tag"],
        "spec": {key: spec[key] for key in ("row", "target", "lane", "rtl_variant", "config", "factors",
                                            "synth_parameters", "target_role", "clock_target", "clock_period_ns",
                                            "sdc", "serial_run_tag")},
        "run": {key: record[key] for key in ("openlane_command", "overrides", "sizing", "started", "finished",
                                             "wall_time_s", "exit_code", "machine", "resources")},
        "openlane_version": resolved["meta"]["openlane_version"],
        "pdk": {"pdk": resolved["PDK"], "scl": resolved["STD_CELL_LIBRARY"], "pdk_root": resolved["PDK_ROOT"]},
        "sdc_sha256": _file_sha256(ROOT / spec["sdc"]),
        "config_sha256": _file_sha256(ROOT / spec["config"]),
        "dut_sources_sha256": _dut_sources(resolved),
        "openlane_errors": _openlane_errors(run_dir),
        "committed_reports_sha256": copied,
        "compressed_reports": sorted(name for name in copied if Path(name).name in COMPRESSED_REPORTS),
        "metrics_source": state["source"] if state is not None else None,
    }
    gl = power = activity = None
    if metrics is None:
        reasons.append("the flow produced no metrics")
    else:
        evidence["timing"] = timing(metrics, spec["clock_period_ns"], table["signoff"]["timing_corners"])
        evidence["signoff"] = signoff(metrics)
        log = (_step_dir(run_dir, "yosys-synthesis") / "yosys-synthesis.log").read_text(encoding="utf-8")
        evidence["synthesis"] = {"multipliers_at_alumacc": synthesis_multipliers(log),
                                 "stat": {name: metrics.get(name) for name in (
                                     "design__instance__count__stdcell",
                                     "design__instance__count__class:sequential_cell",
                                     "design__instance__count__class:multi_input_combinational_cell",
                                     "design__instance__count__class:clock_buffer",
                                     "design__instance__count__class:timing_repair_buffer")}}
        if evidence["timing"]["status"] != "met":
            reasons.append("timing violated at the signoff corners " + ", ".join(table["signoff"]["timing_corners"]))
        if evidence["signoff"]["status"] != "clean":
            reasons.append(f"physical signoff not clean: DRC {evidence['signoff']['drc']}, LVS "
                           f"{evidence['signoff']['lvs']}")
        antenna_step = _step_dir(run_dir, "openroad-checkantennas-1")
        antenna_report = antenna_step / "reports" / "antenna_summary.rpt" if antenna_step else None
        if antenna_report is not None and antenna_report.is_file():
            target = out / "openroad-checkantennas" / "antenna_summary.rpt"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(antenna_report, target)
            evidence["signoff"]["antenna_violations"] = antenna_violations(target.read_text(encoding="utf-8"))
            evidence["signoff"]["antenna_report"] = "openroad-checkantennas/antenna_summary.rpt"
            evidence["signoff"]["antenna_report_sha256"] = _file_sha256(target)
        if skip_activity:
            evidence["activity_skipped"] = skip_activity
            reasons.append(f"gate-level activity and power not run: {skip_activity}")
        else:
            gl = gate_level(spec, resolved, state["nl"], base, table)
            reasons += gl["failures"]
        if gl is not None and "window" in gl:
            saif, window_vcd = out / SAIF_FILE, base / "gl" / "window.vcd"
            vcd_bytes = gl["vcd"].stat().st_size
            cross_check = vcd_bytes <= VCD_CROSS_CHECK_MAX_BYTES
            activity = ppa_activity.vcd_to_saif(gl["vcd"], saif, tuple(table["activity"]["scope"].split("/")),
                                                (gl["window"]["start_ns"], gl["window"]["end_ns"]),
                                                window_vcd if cross_check else None)
            activity["vcd_bytes"] = vcd_bytes
            if not cross_check:
                window_vcd = None
            power = annotated_power(table, resolved, state, base, saif, window_vcd, openlane_dir)
            if not keep_vcd:
                gl["vcd"].unlink()
                if window_vcd is not None:
                    window_vcd.unlink()
    evidence["gate_level"] = None if gl is None else {key: value for key, value in gl.items() if key != "vcd"}
    if power is not None:
        written = set(activity["written_names"])
        annotated = power["pins"] & written
        coverage = len(annotated) / len(power["pins"])
        vcd_total = power["vcd_check"]["Total"]["total_w"] if power["vcd_check"] else None
        openlane_power = _step_dir(run_dir, "openroad-stapostpnr") / power["corner"] / "power.rpt"
        reference = parse_power_report(openlane_power.read_text(encoding="utf-8"))["Total"]["total_w"]
        reproduced = power["unannotated"]["Total"]["total_w"]
        report_names = ["power_unannotated.rpt", "power_annotated.rpt"]
        if vcd_total is not None:
            report_names.append("power_vcd_check.rpt")
        for name in report_names:
            target = out / "power" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(power["out"] / name, target)
        shutil.copyfile(power["out"] / "run.tcl", out / "power" / "run.tcl")
        evidence["activity"] = {
            "file": SAIF_FILE,
            "sha256": _file_sha256(out / SAIF_FILE),
            "source": "gate-level simulation of the run's final netlist at its period, continuous canonical run, "
                      "from its first cycle to the negedge after its last output (whole cycles)",
            "scope": activity["scope"],
            "window_ps": [activity["window_start_ps"], activity["window_end_ps"]],
            "duration_ps": activity["duration_ps"],
            "period_ns": gl["window"]["period_ns"],
            "cycles": gl["window"]["cycles"],
            "vcd_bytes": activity["vcd_bytes"],
            "saif_names": len(written),
            # Escaped net names a SAIF identifier cannot carry; nets are not annotated anyway.
            "unrepresentable_names": len(activity["unrepresentable_names"]),
        }
        evidence["power"] = {
            "corner": power["corner"],
            "liberty": power["liberty"],
            "netlist": power["netlist"],
            "spef": power["spef"],
            "sta_version": power["sta_version"],
            "annotated_w": power["annotated"],
            "unannotated_w": power["unannotated"],
            "openlane_power_rpt_total_w": reference,
            "unannotated_reproduces_openlane": abs(reproduced - reference) <= 1e-4 * abs(reference),
            "leaf_pins": len(power["pins"]),
            "liberty_internal_pins_excluded": power["internal_pins"],
            "annotated_pins": len(annotated),
            "annotation_coverage": coverage,
            "unannotated_pins_sample": sorted(power["pins"] - written)[:20],
            "vcd_cross_check": {
                "executed": vcd_total is not None,
                "method": "the same window as a VCD from time 0, read with OpenSTA read_vcd after the SAIF"
                if vcd_total is not None else
                f"skipped: the window VCD is {activity['vcd_bytes']} bytes, above the "
                f"{VCD_CROSS_CHECK_MAX_BYTES} bytes read_vcd is run on (it keeps every value change in memory); "
                "the SAIF is the measurement",
                "total_w": vcd_total,
                "opensta_annotated_pins": power["vcd_annotated_pins"],
                "agrees": None if vcd_total is None else
                abs(vcd_total - power["annotated"]["Total"]["total_w"]) <= 1e-4 * vcd_total
                and power["vcd_annotated_pins"] == len(annotated),
            },
            "reports": [f"power/{name}" for name in report_names] + ["power/run.tcl"],
            "scope": "core + clock tree (report_power Total; this design has no Pad or Macro power)",
        }
    evidence["row"] = normalized_row(table, spec, "failed" if reasons else "passed", reasons, metrics,
                                     evidence.get("timing"), evidence.get("signoff"), gl, evidence.get("power"),
                                     evidence.get("activity"))
    _write_json(out / EVIDENCE_FILE, evidence)
    return out / EVIDENCE_FILE


def normalized_row(table: dict, spec: dict, status: str, reasons: list[str], metrics: dict | None,
                   timing_result: dict | None, signoff_result: dict | None, gl: dict | None,
                   power: dict | None, activity: dict | None) -> dict:
    """The run's Normalized Row (ppa-matrix-18); comparison fields are filled by ``rows``."""
    factors = spec["factors"]
    row = dict.fromkeys(ROW_FIELDS)
    row.update({
        "lane": spec["lane"], "architecture": spec["row"],
        "S": factors.get("S"), "P": factors.get("P"), "U": factors.get("U"), "F": factors.get("F"),
        "fft_n": factors.get("fft_n"), "hop": factors.get("hop"),
        "clock_target": spec["clock_target"], "clock_period_ns": spec["clock_period_ns"],
        "target_class": spec["target"], "target_role": spec["target_role"],
        "corner": table["signoff"]["corner"],
        "workload": table["activity"].get("workload_by_lane", {}).get(spec["lane"], table["activity"]["workload"]),
        "run_status": status, "failure_or_unrun_reason": "; ".join(reasons) or None,
        "timing_status": timing_result["status"] if timing_result else "not-run",
        "run_tag": spec["run_tag"], "serial_run_tag": spec["serial_run_tag"],
        "power_status": "not-run",
    })
    if gl is not None:
        row["vector_status"] = "fail" if gl["failures"] else "pass"
    else:
        row["vector_status"] = "not-run"
    if metrics is not None:
        row.update({
            "area_um2": metrics["design__instance__area"],
            "die_area_um2": metrics["design__die__area"],
            "core_area_um2": metrics["design__core__area"],
            "utilization": metrics["design__instance__utilization"],
            "setup_ws_ns": timing_result["setup_ws_ns"], "setup_tns_ns": timing_result["setup_tns_ns"],
            "hold_ws_ns": timing_result["hold_ws_ns"], "hold_tns_ns": timing_result["hold_tns_ns"],
            "fmax_mhz": timing_result["fmax_mhz"],
            "drc": signoff_result["drc"], "lvs": signoff_result["lvs"], "antenna": signoff_result["antenna"],
        })
    if gl is not None and gl.get("block_timing"):
        # A block engine issues a work group (HOP samples) every block II: that is its II and its throughput.
        timing_block = gl["block_timing"]
        ii = timing_block["block_ii_min"]
        row["ii_cycles"] = ii
        row["samples_per_cycle"] = timing_block["hop"] / ii
        row["effective_outputs_per_s"] = 1e9 / spec["clock_period_ns"] * timing_block["hop"] / ii
    elif gl is not None and "continuous" in gl:
        ii = gl["continuous"]["measured_ii"]
        if isinstance(ii, int):
            row["ii_cycles"] = ii
            row["samples_per_cycle"] = 1 / ii
            row["effective_outputs_per_s"] = 1e9 / spec["clock_period_ns"] / ii
    if power is not None:
        coverage = power["annotation_coverage"]
        row.update({
            "power_total": power["annotated_w"]["Total"]["total_w"],
            "power_status": "annotated" if coverage >= table["signoff"]["min_annotation_coverage"]
            and power["vcd_cross_check"]["agrees"] is not False else "partially-annotated",
            "activity_file": f"{spec['evidence_dir']}/{activity['file']}",
            "activity_period_ns": activity["period_ns"],
            "annotation_coverage": coverage,
        })
        if row["effective_outputs_per_s"]:
            row["power_per_valid_output"] = row["power_total"] / row["effective_outputs_per_s"]
    return row


def unrun(table: dict, spec: dict, reason: str) -> Path:
    """Record a target run that was not executed."""
    if not reason.strip():
        raise ValueError("an unrun target run needs its reason")
    out = ROOT / spec["evidence_dir"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    evidence = {
        "evidence_for": f"{table['tasks'][spec['lane']]} target run {spec['run_tag']} "
                        f"({spec['target_role']} target of {spec['row']})",
        "run_tag": spec["run_tag"],
        "spec": {key: spec[key] for key in ("row", "target", "lane", "rtl_variant", "config", "factors",
                                            "synth_parameters", "target_role", "clock_target", "clock_period_ns",
                                            "sdc", "serial_run_tag")},
        "recorded": _now(),
        "row": normalized_row(table, spec, "unrun", [reason], None, None, None, None, None, None),
    }
    _write_json(out / EVIDENCE_FILE, evidence)
    return out / EVIDENCE_FILE


# Rows and deltas -------------------------------------------------------------


def _delta(candidate: float, serial: float, unit: str) -> dict:
    return {"abs": candidate - serial, "pct": 100.0 * (candidate - serial) / serial, "unit": unit}


def compare(candidate: dict, serial: dict, same_conditions: bool) -> dict:
    """Comparison fields of a candidate row against its same-domain serial at the same target."""
    if candidate["clock_period_ns"] != serial["clock_period_ns"]:
        raise ValueError("comparisons are only at the same target")
    reasons = []
    if serial["run_status"] != "passed":
        reasons.append(f"serial {serial['run_tag']} is {serial['run_status']}")
    if candidate["run_status"] != "passed":
        reasons.append(f"candidate {candidate['run_tag']} is {candidate['run_status']}")
    if not same_conditions:
        reasons.append("flow, PDK or SDC differ between the two runs")
    if reasons:
        return {"comparison_status": "not-comparable", "comparison_reason": "; ".join(reasons),
                "throughput_delta": None, "area_delta": None, "power_per_output_delta": None}
    fields = {
        "comparison_status": "comparable",
        "comparison_reason": DELTA_CONVENTION,
        "throughput_delta": _delta(candidate["effective_outputs_per_s"], serial["effective_outputs_per_s"],
                                   "valid outputs/s"),
        "area_delta": _delta(candidate["area_um2"], serial["area_um2"], "um^2"),
        "power_per_output_delta": "not-comparable: annotated activity missing for "
        + ", ".join(row["run_tag"] for row in (candidate, serial) if row["power_status"] != "annotated"),
    }
    if candidate["power_status"] == serial["power_status"] == "annotated":
        fields["power_per_output_delta"] = _delta(candidate["power_per_valid_output"],
                                                  serial["power_per_valid_output"], "J/valid output")
    return fields


def _conditions(evidence: dict) -> tuple:
    return (evidence.get("openlane_version"), json.dumps(evidence.get("pdk"), sort_keys=True), evidence.get("sdc_sha256"))


def rows(table: dict, lane: str) -> list[dict]:
    """Every row of ``lane`` at every target, from its evidence, with same-target serial comparisons."""
    evidence = {}
    for row in table["rows"]:
        if table["rows"][row]["lane"] != lane:
            continue
        for target in table["targets"]:
            spec = target_run(table, row, target)
            path = ROOT / spec["evidence_dir"] / EVIDENCE_FILE
            if not path.is_file():
                raise ValueError(f"{spec['run_tag']} has no evidence: collect it or record it as unrun")
            evidence[spec["run_tag"]] = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for run_tag, entry in evidence.items():
        row = {name: entry["row"][name] for name in ROW_FIELDS}
        if row["serial_run_tag"] == run_tag:
            row.update({"comparison_status": "serial-baseline", "comparison_reason": "same-domain serial reference"})
        else:
            serial = evidence[row["serial_run_tag"]]
            # Unrun entries have no flow to compare; their status already makes the pair not comparable.
            executed = "run" in entry and "run" in serial
            row.update(compare(row, serial["row"], not executed or _conditions(entry) == _conditions(serial)))
        result.append(row)
    return result


def write_rows(table: dict, lane: str) -> list[Path]:
    result = rows(table, lane)
    out = ROOT / table["evidence_dirs"][lane]
    _write_json(out / "rows.json", {"fields": list(ROW_FIELDS), "delta_convention": DELTA_CONVENTION, "rows": result})
    with open(out / "rows.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(ROW_FIELDS)
        for row in result:
            writer.writerow([_csv_value(row[name]) for name in ROW_FIELDS])
    return [out / "rows.json", out / "rows.csv"]


def _csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return f"{value['pct']:+.2f}%"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="PPA target runs of the matrix rows (T41 time, T43 frequency)")
    parser.add_argument("command", choices=("run", "collect", "unrun", "rows"))
    parser.add_argument("--row", help="matrix row, e.g. T-S8P1")
    parser.add_argument("--target", choices=("SLOW", "FAST"))
    parser.add_argument("--reason", help="why an unrun target run was not executed")
    parser.add_argument("--lane", default="time")
    parser.add_argument("--openlane-dir", type=Path, default=Path.home() / "openlane2")
    parser.add_argument("--skip-activity", action="store_true",
                        help="collect: record the flow without the gate-level run and the power (needs --reason)")
    parser.add_argument("--keep-vcd", action="store_true", help="keep the gate-level VCD after writing the SAIF")
    arguments = parser.parse_args()
    table = load_table()
    try:
        if arguments.command == "rows":
            for path in write_rows(table, arguments.lane):
                print(path)
            return
        if not arguments.row or not arguments.target:
            parser.error(f"{arguments.command} needs --row and --target")
        spec = target_run(table, arguments.row, arguments.target)
        if arguments.command == "run":
            print(run(table, spec, arguments.openlane_dir))
        elif arguments.command == "collect":
            if arguments.skip_activity and not (arguments.reason or "").strip():
                parser.error("--skip-activity needs --reason")
            print(collect(table, spec, arguments.openlane_dir, arguments.keep_vcd,
                          arguments.reason if arguments.skip_activity else None))
        else:
            print(unrun(table, spec, arguments.reason or ""))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
