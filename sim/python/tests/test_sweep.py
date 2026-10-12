"""T21 width sweep: required rows, frontier, production Q2.14 acceptance and evidence currency."""

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

import sweep
from fxp import SWEEP_WIDTHS, FxpPolicy
from sqnr import SQNR_CROSS_MIN_DB, SQNR_MIN_DB
from sweep import (
    ACCEPTANCE_FRAME,
    DIAGNOSTIC_ROLE,
    PRODUCTION_ROLE,
    build_row,
    frontier,
    generate_sweep_evidence,
    production_acceptance,
)


_SIM_DIR = Path(sweep.__file__).resolve().parent
_COMMITTED_EVIDENCE = _SIM_DIR / "artifacts" / "t21-width-sweep"
_T20_EVIDENCE = _SIM_DIR / "artifacts" / "t20-fxp" / "evidence_manifest.json"
_VECTORS_DIR = _SIM_DIR.parent / "vectors"
_FRAMES = (
    "canonical/none",
    "sys_corners/corner_repeat",
    "sys_corners/max_alternation",
    "sys_corners/single_symbol_perturbation",
)


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    return generate_sweep_evidence(tmp_path_factory.mktemp("t21-width-sweep"))


@pytest.fixture(scope="module")
def manifest(evidence):
    return json.loads(evidence.read_text(encoding="utf-8"))


def _rows(manifest: dict) -> dict:
    return {row["W_common"]: row for row in manifest["rows"]}


def _without_provenance(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.pop("provenance")
    return document


def _tree_sha256(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# Required rows -------------------------------------------------------------


def test_rows_cover_the_required_widths_with_the_base_policy(manifest):
    rows = manifest["rows"]
    assert [row["W_common"] for row in rows] == [8, 10, 12, 14, 16, 18] == list(SWEEP_WIDTHS)
    for row in rows:
        policy = FxpPolicy(row["W_common"])
        assert {name: row[name] for name in policy.manifest_fields()} == policy.manifest_fields()
        assert row["rounding_mode"] == "RNE"
        assert row["W_acc_time"] == 2 * row["W_common"] + 3
        assert row["fft_mode"] == "baseline_A_grow_by_stage"
        assert (row["valid_start"], row["valid_len"]) == (0, 2055)
        assert (row["vector_match_time"], row["vector_match_freq"], row["power_status"]) == ("not_run",) * 3
        assert not {"latency_samples", "latency_cycles", "area_um2", "fmax_mhz"} & set(row)
    assert set(manifest["frames"]) == {str(width) for width in SWEEP_WIDTHS}
    assert all(set(frames) == set(_FRAMES) for frames in manifest["frames"].values())


def test_only_w16_is_the_production_row(manifest):
    roles = {width: row["role"] for width, row in _rows(manifest).items()}
    assert roles == {width: PRODUCTION_ROLE if width == 16 else DIAGNOSTIC_ROLE for width in SWEEP_WIDTHS}
    assert {width for width, row in _rows(manifest).items() if row["sqnr_cross_gated"]} == {16}


# Production acceptance -----------------------------------------------------


def test_production_q2_14_is_numerically_accepted(manifest):
    acceptance = manifest["production_acceptance"]
    assert (acceptance["W_common"], acceptance["format"]) == (16, "Q2.14")
    assert acceptance["passed"] is True
    assert all(acceptance["criteria"].values())
    row = _rows(manifest)[16]
    assert row["sqnr_time_db"] >= SQNR_MIN_DB and row["sqnr_freq_db"] >= SQNR_MIN_DB
    assert row["sqnr_cross_db"] >= SQNR_CROSS_MIN_DB
    assert row["internal_overflow_count"] == 0
    assert row["output_saturation_count"] == 0
    for frame in manifest["frames"]["16"].values():
        assert frame["time"]["internal_overflow_count"] == frame["frequency"]["internal_overflow_count"] == 0


def test_production_row_reproduces_the_t20_evidence(manifest):
    t20 = json.loads(_T20_EVIDENCE.read_text(encoding="utf-8"))
    assert manifest["hash_serialization"] == t20["hash_serialization"]
    assert manifest["f1_manifest_sha256"] == {key: frame["f1_manifest_sha256"] for key, frame in t20["frames"].items()}
    for key, frame in t20["frames"].items():
        swept = manifest["frames"]["16"][key]
        assert swept["sqnr_cross_db"] == frame["sqnr_cross_db"]
        for domain in ("time", "frequency"):
            assert {name: swept[domain][name] for name in frame[domain]} == frame[domain]


def test_production_needs_the_cross_domain_gate(manifest):
    frames = copy.deepcopy(manifest["frames"]["16"])
    frames[ACCEPTANCE_FRAME]["sqnr_cross_db"] = SQNR_CROSS_MIN_DB - 0.01
    row = build_row(FxpPolicy(16), frames)
    assert row["numerically_passing"] is True
    assert row["sqnr_cross_passed"] is False
    acceptance = production_acceptance([row])
    assert acceptance["criteria"]["sqnr_cross"] is False
    assert acceptance["passed"] is False
    # A diagnostic width reports the same cross-domain value without a threshold.
    diagnostic = build_row(FxpPolicy(10), frames)
    assert diagnostic["sqnr_cross_gated"] is False
    assert diagnostic["numerically_passing"] is True


def test_production_acceptance_requires_the_production_row(manifest):
    diagnostic_rows = [row for row in manifest["rows"] if row["role"] == DIAGNOSTIC_ROLE]
    with pytest.raises(ValueError, match="production width"):
        production_acceptance(diagnostic_rows)


# Row gates -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("frame", "domain", "field", "value", "failed_check"),
    [
        (ACCEPTANCE_FRAME, "time", "sqnr_db", SQNR_MIN_DB - 0.01, "sqnr"),
        (ACCEPTANCE_FRAME, "frequency", "split_half_stable", False, "split_half_stable"),
        (ACCEPTANCE_FRAME, "frequency", "output_saturation_count", 1, "zero_canonical_output_saturation"),
        (ACCEPTANCE_FRAME, "time", "internal_overflow_count", 1, "zero_internal_overflow"),
        ("sys_corners/max_alternation", "frequency", "internal_overflow_count", 1, "zero_internal_overflow"),
        ("sys_corners/corner_repeat", "time", "output_saturation_count", 3, None),
        ("sys_corners/single_symbol_perturbation", "frequency", "split_half_stable", False, None),
        ("sys_corners/corner_repeat", "frequency", "sqnr_db", SQNR_MIN_DB - 10, None),
    ],
)
def test_row_gates_use_the_frames_the_contract_names(manifest, frame, domain, field, value, failed_check):
    frames = copy.deepcopy(manifest["frames"]["16"])
    frames[frame][domain][field] = value
    row = build_row(FxpPolicy(16), frames)
    failed = [(name, check) for name, checks in row["criteria"].items() for check, ok in checks.items() if not ok]
    if failed_check is None:
        # sys_corners SQNR, split halves and output saturation are diagnostics.
        assert failed == []
        assert row["numerically_passing"] is True
    else:
        assert failed == [(domain, failed_check)]
        assert row["numerically_passing"] is False


def test_split_half_is_gated_on_the_canonical_frame_only(manifest):
    for width, frames in manifest["frames"].items():
        for domain in ("time", "frequency"):
            canonical = frames[ACCEPTANCE_FRAME][domain]
            assert canonical["split_half_stable"] is True, (width, domain)
            assert canonical["split_half_max_deviation_db"] <= 0.5
    # The one unstable estimate: at W=18 the single perturbed symbol dominates a
    # ~118 dB error budget and straddles the half boundary. It stays a diagnostic.
    corner = manifest["frames"]["18"]["sys_corners/single_symbol_perturbation"]["frequency"]
    assert corner["split_half_stable"] is False
    assert corner["split_half_max_deviation_db"] > 0.5
    assert _rows(manifest)[18]["numerically_passing"] is True


# Frontier ------------------------------------------------------------------


def test_measured_frontier_does_not_replace_production(manifest):
    result = manifest["frontier"]
    assert (result["both_domains_W"], result["time_W"], result["frequency_W"]) == (10, 8, 10)
    assert result["passes_at_every_wider_width"] is True
    # Gating every row on the cross-domain SQNR would not move the frontier.
    assert result["both_domains_with_cross_gate_W"] == 10
    assert min(row["sqnr_cross_db"] for row in manifest["rows"]) >= SQNR_CROSS_MIN_DB
    w8 = _rows(manifest)[8]
    failed = [(name, check) for name, checks in w8["criteria"].items() for check, ok in checks.items() if not ok]
    assert failed == [("frequency", "sqnr")]
    assert manifest["production_acceptance"]["W_common"] == 16


def _synthetic_row(width: int, time_passes: bool, frequency_passes: bool) -> dict:
    def checks(passes: bool) -> dict:
        return {
            "sqnr": passes,
            "split_half_stable": True,
            "zero_internal_overflow": True,
            "zero_canonical_output_saturation": True,
        }

    return {
        "W_common": width,
        "criteria": {"time": checks(time_passes), "frequency": checks(frequency_passes)},
        "numerically_passing": time_passes and frequency_passes,
        "sqnr_cross_passed": True,
    }


def test_frontier_reports_no_width_when_nothing_passes():
    result = frontier([_synthetic_row(width, False, False) for width in (8, 10)])
    assert (result["both_domains_W"], result["time_W"], result["frequency_W"]) == (None, None, None)
    assert result["both_domains_with_cross_gate_W"] is None
    assert result["passes_at_every_wider_width"] is False


def test_frontier_reports_the_cross_gated_width_separately():
    rows = [_synthetic_row(width, True, True) for width in (8, 10, 12)]
    rows[0]["sqnr_cross_passed"] = False
    result = frontier(rows)
    assert (result["both_domains_W"], result["both_domains_with_cross_gate_W"]) == (8, 10)


def test_frontier_flags_a_non_monotonic_sweep():
    rows = [
        _synthetic_row(8, True, False),
        _synthetic_row(10, True, True),
        _synthetic_row(12, False, True),
        _synthetic_row(14, True, True),
    ]
    result = frontier(rows)
    assert (result["both_domains_W"], result["time_W"], result["frequency_W"]) == (10, 8, 10)
    assert result["passes_at_every_wider_width"] is False


# Coefficient quantization --------------------------------------------------


def test_time_error_is_the_coefficient_quantization(manifest):
    # +/-1 and 0 input codes keep the time accumulator on multiples of 2^F, so
    # the output cast never drops a nonzero bit and only the stored taps differ.
    for width, frames in manifest["frames"].items():
        for frame in frames.values():
            assert frame["time"]["rounding"]["output_cast"]["inexact"] == 0, width
    rows = _rows(manifest)
    for row in rows.values():
        assert abs(row["sqnr_time_db"] - row["coefficient_sqnr_db"]) < 0.1, row["W_common"]
    # The uneven SQNR steps between widths come from where the eight taps land
    # on each grid, not from a per-bit noise model.
    steps = [rows[width + 2]["coefficient_sqnr_db"] - rows[width]["coefficient_sqnr_db"] for width in SWEEP_WIDTHS[:-1]]
    assert max(steps) - min(steps) > 10


# Evidence ------------------------------------------------------------------


def test_table_lists_every_width_and_frame(manifest, evidence):
    table_path = evidence.with_name(manifest["table"]["file"])
    assert hashlib.sha256(table_path.read_bytes()).hexdigest() == manifest["table"]["sha256"]
    with table_path.open(encoding="utf-8", newline="") as handle:
        lines = list(csv.DictReader(handle))
    assert [(int(line["W_common"]), line["frame"]) for line in lines] == [
        (width, frame) for width in SWEEP_WIDTHS for frame in _FRAMES
    ]
    rows = _rows(manifest)
    for line in lines:
        if line["frame"] != ACCEPTANCE_FRAME:
            continue
        row = rows[int(line["W_common"])]
        assert line["sqnr_time_db"] == f"{row['sqnr_time_db']:.4f}"
        assert line["sqnr_freq_db"] == f"{row['sqnr_freq_db']:.4f}"
        assert line["sqnr_cross_db"] == f"{row['sqnr_cross_db']:.4f}"
        assert line["row_numerically_passing"] == str(row["numerically_passing"])


def test_regeneration_is_byte_identical_and_leaves_sim_vectors_untouched(evidence, tmp_path):
    vectors_before = _tree_sha256(_VECTORS_DIR)
    again = generate_sweep_evidence(tmp_path)
    assert again.read_bytes() == evidence.read_bytes()
    assert (tmp_path / "sweep_table.csv").read_bytes() == evidence.with_name("sweep_table.csv").read_bytes()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["evidence_manifest.json", "sweep_table.csv"]
    assert _tree_sha256(_VECTORS_DIR) == vectors_before


def test_committed_evidence_is_current(evidence):
    committed = _COMMITTED_EVIDENCE / "evidence_manifest.json"
    assert _without_provenance(committed) == _without_provenance(evidence)
    committed_sources = json.loads(committed.read_text(encoding="utf-8"))["provenance"]["source_sha256"]
    fresh_sources = json.loads(evidence.read_text(encoding="utf-8"))["provenance"]["source_sha256"]
    assert committed_sources == fresh_sources
    assert (_COMMITTED_EVIDENCE / "sweep_table.csv").read_bytes() == evidence.with_name("sweep_table.csv").read_bytes()


def test_sweep_refuses_to_write_into_sim_vectors():
    with pytest.raises(ValueError, match="never go into sim/vectors"):
        generate_sweep_evidence(_VECTORS_DIR / "t21-width-sweep")
    assert not (_VECTORS_DIR / "t21-width-sweep").exists()


def test_cli_writes_the_evidence_and_the_plot(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["sweep.py", "--output-dir", str(tmp_path), "--plot"])
    sweep.main()
    printed = capsys.readouterr().out.split()
    assert [Path(path).name for path in printed] == ["evidence_manifest.json", "plot_manifest.json"]
    plot_manifest = json.loads((tmp_path / "plot_manifest.json").read_text(encoding="utf-8"))
    plot = tmp_path / plot_manifest["plot"]
    assert plot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert plot_manifest["plot_sha256"] == hashlib.sha256(plot.read_bytes()).hexdigest()
    evidence_bytes = (tmp_path / "evidence_manifest.json").read_bytes()
    assert plot_manifest["drawn_from"]["sha256"] == hashlib.sha256(evidence_bytes).hexdigest()
    assert plot_manifest["frame"] == ACCEPTANCE_FRAME
