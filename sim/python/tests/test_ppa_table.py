"""T44 (#55): the committed PPA table is what ``ppa_table.py`` computes from the lane rows.

Checks the gate order with the 2026-10-24 antenna amendment, that runs with
no evidence stay pending (never results), that deltas stand only between
gated runs and that the Pareto front holds only non-dominated gated runs at
one target. Standard library only.
"""

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppa_stage as ppa  # noqa: E402
import ppa_table as t44  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
RESULT = t44.build(ppa.load_table())
ROWS = {row["run_tag"]: row for row in RESULT["rows"]}


def test_committed_table_is_regenerated():
    committed = json.loads((t44.OUT / "table.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(RESULT))
    assert t44.DOC.read_text(encoding="utf-8") == t44.markdown(RESULT)


def test_twelve_target_runs_of_the_base_matrix():
    assert len(RESULT["rows"]) == 12
    assert {(row["architecture"], row["target_class"]) for row in RESULT["rows"]} == {
        (name, target) for name in t44.MATRIX for target in t44.TARGETS}
    for row in RESULT["rows"]:
        main = t44.MATRIX[row["architecture"]][1]
        assert row["target_role"] == ("main" if row["target_class"] == main else "secondary")


def test_runs_without_evidence_are_pending_not_results():
    for row in RESULT["rows"]:
        if row["run_status"] == "pending":
            assert not row["gated"] and not row["pareto"]
            assert row["area_um2"] is None and row["throughput_delta"] is None


BASE = {"run_tag": "X-SLOW", "vector_status": "pass", "drc": 0, "lvs": 0, "antenna": 0,
        "timing_status": "met", "setup_ws_ns": 1.0}


def _nets(*ratios):
    return [{"layer": "met1", "net": f"n{i}", "ratio": ratio} for i, ratio in enumerate(ratios)]


@pytest.mark.parametrize("ratios, gated", [
    ((), True),
    ((1.0, 1.64, 1.72), True),
    ((1.73,), False),
    ((1.0, 1.0, 1.0, 1.0), False),
])
def test_antenna_amendment_bound(ratios, gated):
    row = dict(BASE, antenna=len(ratios))
    result = t44.gates(row, _nets(*ratios))
    assert result["gated"] is gated
    assert result["signoff_gate"].startswith("pass" if gated else "fail")


def test_drc_lvs_vector_and_timing_still_gate():
    for change in ({"drc": 1}, {"lvs": 2}, {"vector_status": "fail"}, {"timing_status": "violated"}):
        assert not t44.gates(dict(BASE, **change), [])["gated"]


def test_antenna_count_must_match_listed_nets():
    with pytest.raises(ValueError):
        t44.gates(dict(BASE, antenna=2), _nets(1.1))


def test_deltas_only_between_gated_runs():
    for row in RESULT["rows"]:
        if row["comparison_status"] == "comparable":
            assert row["gated"] and ROWS[row["serial_run_tag"]]["gated"]
        elif row["comparison_status"] == "not-comparable":
            assert row["throughput_delta"] is None and row["area_delta"] is None


def test_pareto_front_is_non_dominated_and_gated():
    for target, front in RESULT["pareto"].items():
        group = [row for row in RESULT["rows"] if row["gated"] and row["target_class"] == target]
        for row in group:
            dominated = any(t44._dominates(other, row, True) for other in group if other is not row)
            assert (row["run_tag"] in front) is not dominated


def test_dominated_run_leaves_the_front():
    rows = copy.deepcopy([ROWS["T-S4P1-SLOW"], ROWS["T-S8P1-SLOW"]])
    rows[0]["area_um2"] = rows[1]["area_um2"] + 1.0
    assert t44.pareto(rows)["SLOW"] == ["T-S8P1-SLOW"]


def test_failed_main_goal_is_not_hidden_by_a_secondary_pass():
    assert not ROWS["T-S4P1-FAST"]["gated"] and ROWS["T-S4P1-SLOW"]["gated"]
    assert "T-S4P1-FAST: FAILED" in t44.DOC.read_text(encoding="utf-8")


def test_antenna_counts_nets_not_pins():
    nets = _nets(1.1, 1.2) + [{"layer": "met1", "net": "n0", "ratio": 1.3}]
    assert t44.gates(dict(BASE, antenna=2), nets)["antenna_max_ratio"] == 1.3
