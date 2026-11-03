"""T44 (#55): PPA comparison table of the six base architectures, from the committed lane rows.

Reads each lane's ``rows.json`` (written by ``ppa_stage.py rows``) and the
evidence manifests next to it, applies the ppa-matrix-18 gates in order
(vector matching, physical signoff, timing at the row's target) and writes:

- ``sim/python/artifacts/t44-ppa/table.json`` / ``table.csv``: the 12 target
  runs of the base matrix with their gate result; runs with no evidence yet
  stay as ``pending`` rows, never as results;
- ``docs/ppa/t44-ppa-table.md``: the readable table, the Pareto front per
  target and the delivery evidence per domain.

Antenna follows the 2026-10-24 amendment of ppa-matrix-18 (Antenna Residual
Tolerance): a run with residual post-route antenna nets passes signoff when
it has at most ``ANTENNA_MAX_NETS`` violating nets, each with a ratio of at
most ``ANTENNA_MAX_RATIO``; the residual nets are always reported. Pareto
fronts are built only among gated runs at the same target, corner, workload
and activity policy. Standard library only.
"""

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppa_stage as ppa  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "sim" / "python" / "artifacts" / "t44-ppa"
DOC = ROOT / "docs" / "ppa" / "t44-ppa-table.md"
# Base matrix of ppa-matrix-18 (Matrix): row -> (lane, main target, factors).
MATRIX = {
    "T-serial": ("time", "SLOW", {"S": 1, "P": 1}),
    "T-S4P1": ("time", "FAST", {"S": 4, "P": 1}),
    "T-S8P1": ("time", "FAST", {"S": 8, "P": 1}),
    "F-serial": ("freq", "SLOW", {"U": 1}),
    "F-U4": ("freq", "FAST", {"U": 4}),
    "F-U8": ("freq", "FAST", {"U": 8}),
}
SERIAL = {"time": "T-serial", "freq": "F-serial"}
TARGETS = ("SLOW", "FAST")
# Amendment 2026-10-24 (Antenna Residual Tolerance), ppa-matrix-18.
ANTENNA_MAX_NETS = 3
ANTENNA_MAX_RATIO = 1.72
TABLE_FIELDS = (
    "run_tag", "lane", "architecture", "target_class", "target_role", "clock_target", "corner",
    "run_status", "vector_gate", "signoff_gate", "timing_gate", "gated", "gate_reason",
    "antenna_nets", "antenna_max_ratio", "antenna_layers",
    "area_um2", "utilization", "setup_ws_ns", "fmax_mhz", "ii_cycles", "effective_outputs_per_s",
    "outputs_per_s_per_um2", "power_total_w", "power_status", "energy_per_output_j",
    "serial_run_tag", "comparison_status", "comparison_reason",
    "throughput_delta", "area_delta", "energy_per_output_delta", "pareto",
)


def _lane_rows(table: dict, lane: str) -> dict[str, dict]:
    """Committed normalized rows of ``lane`` by run tag; empty while the lane has no evidence."""
    folder = table.get("evidence_dirs", {}).get(lane)
    if not folder or not (ROOT / folder / "rows.json").is_file():
        return {}
    data = json.loads((ROOT / folder / "rows.json").read_text(encoding="utf-8"))
    return {row["run_tag"]: row for row in data["rows"]}


def _antenna(table: dict, lane: str, row: dict) -> list[dict]:
    folder = ROOT / table["evidence_dirs"][lane] / row["architecture"] / row["target_class"].lower()
    manifest = json.loads((folder / ppa.EVIDENCE_FILE).read_text(encoding="utf-8"))
    return manifest.get("signoff", {}).get("antenna_violations", [])


def gates(row: dict, violations: list[dict]) -> dict:
    """Gate results of one executed run, in the ppa-matrix-18 order, with the antenna amendment."""
    reasons = []
    vector = row["vector_status"] == "pass"
    if not vector:
        reasons.append(f"vector matching {row['vector_status']}")
    ratio = max((item["ratio"] for item in violations), default=0.0)
    # The check lists one entry per violating pin; the row counts nets.
    if len({item["net"] for item in violations}) != row["antenna"]:
        raise ValueError(f"{row['run_tag']}: antenna count and listed nets disagree")
    antenna_ok = row["antenna"] <= ANTENNA_MAX_NETS and ratio <= ANTENNA_MAX_RATIO
    signoff = row["drc"] == 0 and row["lvs"] == 0 and antenna_ok
    if row["drc"] or row["lvs"]:
        reasons.append(f"DRC {row['drc']} / LVS {row['lvs']}")
    if not antenna_ok:
        reasons.append(f"antenna {row['antenna']} nets, max ratio {ratio:.2f} over the amendment bound")
    timing = row["timing_status"] == "met"
    if not timing:
        reasons.append(f"timing {row['timing_status']} (setup WS {row['setup_ws_ns']:+.3f} ns)")
    return {
        "vector_gate": "pass" if vector else "fail",
        "signoff_gate": ("pass" if signoff else "fail") + (" (antenna amendment)" if signoff and row["antenna"] else ""),
        "timing_gate": "pass" if timing else "fail",
        "gated": vector and signoff and timing,
        "gate_reason": "; ".join(reasons),
        "antenna_nets": row["antenna"],
        "antenna_max_ratio": ratio,
        "antenna_layers": ",".join(sorted({item["layer"] for item in violations})),
    }


def pending(name: str, target: str) -> dict:
    lane, main, _ = MATRIX[name]
    spec = ppa.load_table()["targets"][target]
    entry = {field: None for field in TABLE_FIELDS}
    entry.update({
        "run_tag": f"{name}-{target}", "lane": lane, "architecture": name, "target_class": target,
        "target_role": "main" if target == main else "secondary", "clock_target": spec["clock_target"],
        "run_status": "pending", "gated": False, "gate_reason": "no committed evidence yet (T43 frequency runs)",
        "serial_run_tag": f"{SERIAL[lane]}-{target}", "comparison_status": "not-comparable",
        "comparison_reason": "candidate or serial has no evidence", "pareto": False,
    })
    return entry


def unrun(row: dict) -> dict:
    """A run recorded as not executed: kept with its reason, never a result."""
    entry = {field: None for field in TABLE_FIELDS}
    entry.update({name: row[name] for name in (
        "run_tag", "lane", "architecture", "target_class", "target_role", "clock_target", "corner", "run_status",
        "serial_run_tag")})
    entry.update({"gated": False, "gate_reason": row["failure_or_unrun_reason"], "pareto": False,
                  "comparison_status": "not-comparable", "comparison_reason": "candidate or serial not executed"})
    return entry


def executed(table: dict, row: dict) -> dict:
    entry = {field: None for field in TABLE_FIELDS}
    entry.update({name: row[name] for name in (
        "run_tag", "lane", "architecture", "target_class", "target_role", "clock_target", "corner", "run_status",
        "area_um2", "utilization", "setup_ws_ns", "fmax_mhz", "ii_cycles", "effective_outputs_per_s",
        "power_status", "serial_run_tag", "throughput_delta", "area_delta")})
    entry.update(gates(row, _antenna(table, row["lane"], row)))
    entry["outputs_per_s_per_um2"] = row["effective_outputs_per_s"] / row["area_um2"] if row["area_um2"] and row["effective_outputs_per_s"] else None
    entry["power_total_w"] = row["power_total"]
    # ppa_stage names it power_per_valid_output; it is energy per valid output in J.
    entry["energy_per_output_j"] = row["power_per_valid_output"]
    entry["energy_per_output_delta"] = row["power_per_output_delta"]
    entry["comparison_status"], entry["comparison_reason"] = row["comparison_status"], row["comparison_reason"]
    entry["pareto"] = False
    return entry


def _regate_comparisons(rows: list[dict]) -> None:
    """A delta stands only when both runs pass every gate; otherwise it is not comparable (D7)."""
    by_tag = {row["run_tag"]: row for row in rows}
    for row in rows:
        if row["run_tag"] == row["serial_run_tag"]:
            row["comparison_status"], row["comparison_reason"] = "serial-baseline", "same-domain serial reference"
            continue
        serial = by_tag[row["serial_run_tag"]]
        failed = [item["run_tag"] for item in (serial, row) if not item["gated"]]
        if failed:
            row["comparison_status"] = "not-comparable"
            row["comparison_reason"] = "not gated: " + ", ".join(failed)
            row["throughput_delta"] = row["area_delta"] = row["energy_per_output_delta"] = None


def _dominates(a: dict, b: dict, energy: bool) -> bool:
    better_or_equal = [a["area_um2"] <= b["area_um2"], a["effective_outputs_per_s"] >= b["effective_outputs_per_s"]]
    strictly = [a["area_um2"] < b["area_um2"], a["effective_outputs_per_s"] > b["effective_outputs_per_s"]]
    if energy:
        better_or_equal.append(a["energy_per_output_j"] <= b["energy_per_output_j"])
        strictly.append(a["energy_per_output_j"] < b["energy_per_output_j"])
    return all(better_or_equal) and any(strictly)


def pareto(rows: list[dict]) -> dict[str, list[str]]:
    """Pareto front per target among gated runs (area vs throughput, plus energy when all annotated)."""
    fronts = {}
    for target in TARGETS:
        group = [row for row in rows if row["gated"] and row["target_class"] == target]
        conditions = {(row["corner"],) for row in group}
        if len(conditions) > 1:
            raise ValueError(f"{target}: gated runs at different corners cannot share a Pareto front")
        energy = all(row["power_status"] == "annotated" for row in group)
        front = [row for row in group if not any(_dominates(other, row, energy) for other in group if other is not row)]
        for row in front:
            row["pareto"] = True
        fronts[target] = [row["run_tag"] for row in front]
    return fronts


def delivery(rows: list[dict]) -> dict[str, str]:
    """D7: at least one optimized candidate per domain improves at least one axis against a comparable serial."""
    result = {}
    for lane in ("time", "freq"):
        wins = []
        for row in rows:
            if row["lane"] != lane or row["comparison_status"] != "comparable":
                continue
            axes = []
            if row["throughput_delta"]["pct"] > 0:
                axes.append("throughput")
            if row["area_delta"]["pct"] < 0:
                axes.append("area")
            energy = row["energy_per_output_delta"]
            if isinstance(energy, dict) and energy["pct"] < 0:
                axes.append("energy/output")
            if axes:
                wins.append(f"{row['run_tag']} ({', '.join(axes)})")
        result[lane] = "met: " + "; ".join(wins) if wins else "not yet demonstrated"
    return result


def build(table: dict) -> dict:
    evidence = {lane: _lane_rows(table, lane) for lane in SERIAL}
    rows = []
    for name, (lane, _, _) in MATRIX.items():
        for target in TARGETS:
            row = evidence[lane].get(f"{name}-{target}")
            if not row:
                rows.append(pending(name, target))
            else:
                rows.append(unrun(row) if row["run_status"] == "unrun" else executed(table, row))
    _regate_comparisons(rows)
    return {
        "antenna_amendment": {"max_nets": ANTENNA_MAX_NETS, "max_ratio": ANTENNA_MAX_RATIO,
                              "source": "docs/contracts/ppa-matrix-18.md, Amendment 2026-10-24"},
        "delta_convention": ppa.DELTA_CONVENTION,
        "fields": list(TABLE_FIELDS),
        "pareto": pareto(rows),
        "delivery": delivery(rows),
        "rows": rows,
    }


# Rendering -------------------------------------------------------------------


def _num(value, digits: int = 1, scale: float = 1.0, sign: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value * scale:{'+' if sign else ''},.{digits}f}"


def _pct(delta) -> str:
    return f"{delta['pct']:+.1f}%" if isinstance(delta, dict) else "—"


def _status(row: dict) -> str:
    if row["run_status"] in ("pending", "unrun"):
        return row["run_status"]
    if row["gated"]:
        return "**pass**" + (" ¹" if row["antenna_nets"] else "")
    return "FAIL: " + row["gate_reason"]


def markdown(result: dict) -> str:
    rows = result["rows"]
    lines = [
        "# T44 — PPA comparison of the six base architectures",
        "",
        "Generated by `python sim/python/tests/ppa_table.py` from the committed lane rows "
        "(`sim/python/artifacts/<lane evidence>/rows.json`). Do not edit by hand.",
        "",
        "Conditions: OpenLane 2.3.10 Classic, sky130A / sky130_fd_sc_hd, canonical #15 frame, "
        "**signoff and power at the typical corner `tt_025C_1v80` only** (not worst case: the FAST "
        "runs miss by ~9-10 ns at `ss_100C_1v60`). Power is OpenSTA with gate-level SAIF activity at the run's period.",
        "",
        "## All target runs",
        "",
        "| Run | Role | Gates | Cell area (µm²) | Util | Setup WS (ns) | fmax (MHz) | II | Throughput (MS/s) "
        "| MS/s per mm² | Power (mW) | Energy/output (nJ) | Antenna nets (max ratio) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        antenna = "—" if row["antenna_nets"] is None else (
            f"{row['antenna_nets']} ({row['antenna_max_ratio']:.2f}, {row['antenna_layers']})" if row["antenna_nets"] else "0")
        lines.append(" | ".join([
            f"| {row['run_tag']}", row["target_role"], _status(row), _num(row["area_um2"]),
            _num(row["utilization"], 3), _num(row["setup_ws_ns"], 3, sign=True), _num(row["fmax_mhz"]),
            _num(row["ii_cycles"], 0), _num(row["effective_outputs_per_s"], 2, 1e-6),
            _num(row["outputs_per_s_per_um2"], 1, 1.0),
            _num(row["power_total_w"], 2, 1e3), _num(row["energy_per_output_j"], 3, 1e9), antenna + " |",
        ]))
    lines += [
        "",
        f"¹ Passes physical signoff under the antenna amendment: residual post-route nets ≤ {ANTENNA_MAX_NETS}, "
        f"ratio ≤ {ANTENNA_MAX_RATIO}. The nets stay reported in each run's `evidence_manifest.json`.",
        "",
        "MS/s per mm² is effective valid outputs per second over cell area (×10⁻⁶ outputs/s per µm² = MS/s per mm²).",
        "",
        "## Optimized vs same-domain serial (same target)",
        "",
        "| Candidate | Serial | Status | Throughput Δ | Area Δ | Energy/output Δ | Reason |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        if row["run_tag"] == row["serial_run_tag"]:
            continue
        reason = "" if row["comparison_status"] == "comparable" else row["comparison_reason"]
        lines.append(f"| {row['run_tag']} | {row['serial_run_tag']} | {row['comparison_status']} | "
                     f"{_pct(row['throughput_delta'])} | {_pct(row['area_delta'])} | "
                     f"{_pct(row['energy_per_output_delta'])} | {reason} |")
    lines += ["", "Δ = candidate minus serial; higher throughput, lower area and lower energy per output are better.", "",
              "## Pareto front per target (gated runs only)", ""]
    for target, front in result["pareto"].items():
        lines.append(f"- **{target}**: " + (", ".join(front) if front else "no gated run yet"))
    lines += ["", "Axes: cell area vs effective throughput, plus energy per output (all gated runs annotated).",
              "Cross-target runs never share a front.", "", "## Main goals", ""]
    for row in rows:
        if row["target_role"] == "main":
            state = row["run_status"] if row["run_status"] in ("pending", "unrun") else ("met" if row["gated"] else "FAILED")
            lines.append(f"- {row['run_tag']}: {state}")
    lines += ["", "## Delivery evidence (D7: one improved axis per domain)", ""]
    for lane, state in result["delivery"].items():
        lines.append(f"- **{lane}**: {state}")
    lines.append("")
    return "\n".join(lines)


def _csv(value) -> str:
    if isinstance(value, dict):
        return f"{value['pct']:+.2f}%"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return ppa._csv_value(value)


def write(result: dict) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    ppa._write_json(OUT / "table.json", result)
    with open(OUT / "table.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(TABLE_FIELDS)
        for row in result["rows"]:
            writer.writerow([_csv(row[name]) for name in TABLE_FIELDS])
    DOC.write_text(markdown(result), encoding="utf-8")
    return [OUT / "table.json", OUT / "table.csv", DOC]


def main() -> None:
    argparse.ArgumentParser(description="T44 PPA table of the base matrix").parse_args()
    for path in write(build(ppa.load_table())):
        print(path)


if __name__ == "__main__":
    main()
