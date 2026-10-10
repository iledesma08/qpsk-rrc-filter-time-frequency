"""Diagnostic RNE width sweep and production Q2.14 validation (T21, #45).

Normative policy: ``docs/contracts/fxp-policy-16.md`` (D1 sweep matrix, D6
split-half check, Acceptance rule and cross-domain amendment) and ADR-0005.
Every swept width runs the accepted production-A integer models of ``fxp.py``
at ``Q2.(W-2)``: RNE at every narrowing, the conservative ``2W+3`` time
accumulator and frequency baseline A, with every stored constant at ``W`` bits.

The results are model-side evidence. Nothing here writes to ``sim/vectors/``;
production expected codes are T22 (#46). Production stays ``W=16`` (``Q2.14``)
and is the only accepted row. The smallest numerically passing width is the
measured precision frontier, never a replacement for production.

A row passes numerically when, on the frames the contract names:

- the per-domain SQNR is at least 40 dB on the canonical frame;
- both halves of the canonical window stay within 0.5 dB of the full-window
  SQNR (D6); the ``sys_corners`` halves are reported as diagnostics;
- no internal overflow occurs on the canonical and the three ``sys_corners``
  frames;
- no output saturation occurs on the canonical frame.

Production also needs the cross-domain SQNR of at least ``40 - 20 log10(2)`` dB
on the canonical frame. The other widths report it without a threshold.
"""

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
from pathlib import Path

import fxpmath
import numpy as np

from fxp import FFT_MODE, PRODUCTION_WIDTH, ROUNDING_MODE, SWEEP_WIDTHS, FxpPolicy, load_f1_frame, measure_frame
from gen_vectors import iter_frames
from sqnr import SPLIT_HALF_TOLERANCE_DB, SQNR_CROSS_MIN_DB, SQNR_MIN_DB, split_half_is_stable


ACCEPTANCE_FRAME = "canonical/none"
PRODUCTION_ROLE = "production"
DIAGNOSTIC_ROLE = "diagnostic_model_only"
DOMAINS = ("time", "frequency")

_SIM_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_DIR = _SIM_DIR / "artifacts" / "t21-width-sweep"
_DEFAULT_VECTORS_DIR = _SIM_DIR.parent / "vectors"
_SOURCE_FILES = ("sweep.py", "fxp.py", "sqnr.py", "rrc_coefs.py", "gen_vectors.py")
_MANIFEST_FILE = "evidence_manifest.json"
_TABLE_FILE = "sweep_table.csv"
_PLOT_FILE = "sqnr_vs_width.png"
_PLOT_MANIFEST_FILE = "plot_manifest.json"
_WINDOW = {"valid_start": 0, "valid_len": 2055}
_HASH_SERIALIZATION = {
    "algorithm": "SHA-256",
    "array_order": "C",
    "byte_order": "little-endian",
    "samples_dtype": "<c16",
    "coefficients_dtype": "<f8",
    "codes_dtype": "<i8",
    "codes_layout": "shape (samples, 2), columns [I, Q]",
}
_TABLE_COLUMNS = (
    "W_common",
    "format",
    "role",
    "frame",
    "sqnr_time_db",
    "sqnr_time_half1_db",
    "sqnr_time_half2_db",
    "sqnr_freq_db",
    "sqnr_freq_half1_db",
    "sqnr_freq_half2_db",
    "sqnr_cross_db",
    "split_half_stable",
    "internal_overflow_time",
    "internal_overflow_freq",
    "output_saturation_time",
    "output_saturation_freq",
    "rne_ties_time",
    "rne_ties_freq",
    "row_numerically_passing",
)

# Plot styling: light chart surface, text inks and the first three categorical
# slots of the validated reference palette (all-pairs CVD-safe). The aqua slot
# is below 3:1 against the surface, so every series also gets its own marker
# and a direct label.
_SURFACE = "#fcfcfb"
_TEXT_PRIMARY = "#0b0b0b"
_TEXT_SECONDARY = "#52514e"
_SERIES = (
    ("sqnr_time_db", "time", "#2a78d6", "o"),
    ("sqnr_freq_db", "frequency", "#eb6834", "s"),
    ("sqnr_cross_db", "cross-domain", "#1baf7a", "^"),
)
_LABEL_GAP_DB = 4.0


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_half_deviation_db(full: float | None, halves: list) -> float | None:
    """Largest distance in dB of a half from the full window; ``None`` (infinite) values match only each other."""
    values = [full, *halves]
    if all(value is None for value in values):
        return 0.0
    if any(value is None for value in values):
        return None
    return max(abs(half - full) for half in halves)


def measure_width(frames: dict, policy: FxpPolicy) -> dict:
    """Measure both integer models of ``policy`` on every loaded F1 frame."""
    measured = {}
    for key, frame in frames.items():
        run = measure_frame(frame["samples"], frame["reference"], policy)
        measurement = run["measurement"]
        for domain in DOMAINS:
            entry = measurement[domain]
            entry["split_half_max_deviation_db"] = _split_half_deviation_db(
                entry["sqnr_db"], entry["split_half_sqnr_db"]
            )
            entry["split_half_stable"] = split_half_is_stable(
                frame["reference"][domain], run["results"][domain].decoded()
            )
        measured[key] = measurement
    return measured


def _max_abs(frames: dict, domain: str, prefix: str) -> int:
    """Largest magnitude seen at the ``domain`` datapath points starting with ``prefix`` over all frames."""
    return max(
        max(-point["min"], point["max"])
        for frame in frames.values()
        for name, point in frame[domain]["ranges"].items()
        if name.startswith(prefix)
    )


def build_row(policy: FxpPolicy, frames: dict) -> dict:
    """Return the sweep result row of one width from its per-frame measurements."""
    canonical = frames[ACCEPTANCE_FRAME]
    criteria = {}
    for domain in DOMAINS:
        sqnr = canonical[domain]["sqnr_db"]
        criteria[domain] = {
            "sqnr": sqnr is None or sqnr >= SQNR_MIN_DB,
            "split_half_stable": canonical[domain]["split_half_stable"],
            "zero_internal_overflow": all(frame[domain]["internal_overflow_count"] == 0 for frame in frames.values()),
            "zero_canonical_output_saturation": canonical[domain]["output_saturation_count"] == 0,
        }
    cross = canonical["sqnr_cross_db"]
    production = policy.width == PRODUCTION_WIDTH
    return {
        "role": PRODUCTION_ROLE if production else DIAGNOSTIC_ROLE,
        **policy.manifest_fields(),
        "sqnr_time_db": canonical["time"]["sqnr_db"],
        "sqnr_freq_db": canonical["frequency"]["sqnr_db"],
        "sqnr_cross_db": cross,
        "split_half_sqnr_time_db": canonical["time"]["split_half_sqnr_db"],
        "split_half_sqnr_freq_db": canonical["frequency"]["split_half_sqnr_db"],
        "max_abs_acc_time": _max_abs(frames, "time", "time_accumulator"),
        "max_abs_acc_freq": _max_abs(frames, "frequency", "ifft_stage"),
        "internal_overflow_count": sum(
            frame[domain]["internal_overflow_count"] for frame in frames.values() for domain in DOMAINS
        ),
        "output_saturation_count": sum(canonical[domain]["output_saturation_count"] for domain in DOMAINS),
        **_WINDOW,
        "vector_match_time": "not_run",
        "vector_match_freq": "not_run",
        "power_status": "not_run",
        "criteria": criteria,
        "numerically_passing": all(all(checks.values()) for checks in criteria.values()),
        "sqnr_cross_gated": production,
        "sqnr_cross_passed": cross is None or cross >= SQNR_CROSS_MIN_DB,
    }


def frontier(rows: list[dict]) -> dict:
    """Smallest numerically passing width, in both domains and per domain; ``None`` when no row passes."""

    def smallest(passes) -> int | None:
        widths = [row["W_common"] for row in rows if passes(row)]
        return min(widths) if widths else None

    both = smallest(lambda row: row["numerically_passing"])
    return {
        "rule": "smallest swept W whose row passes numerically; a measured frontier that never replaces production",
        "both_domains_W": both,
        "time_W": smallest(lambda row: all(row["criteria"]["time"].values())),
        "frequency_W": smallest(lambda row: all(row["criteria"]["frequency"].values())),
        "passes_at_every_wider_width": both is not None
        and all(row["numerically_passing"] for row in rows if row["W_common"] >= both),
    }


def production_acceptance(rows: list[dict]) -> dict:
    """Return the T21 numerical acceptance record of the production row."""
    row = next((row for row in rows if row["role"] == PRODUCTION_ROLE), None)
    if row is None:
        raise ValueError("rows: the production width is missing from the sweep")
    criteria = {
        f"{domain}_{name}": passed for domain, checks in row["criteria"].items() for name, passed in checks.items()
    }
    criteria["sqnr_cross"] = row["sqnr_cross_passed"]
    return {
        "W_common": row["W_common"],
        "format": f"Q2.{row['F_data']}",
        "criteria": criteria,
        "passed": all(criteria.values()),
    }


def _db_text(value: float | None) -> str:
    return "inf" if value is None else f"{value:.4f}"


def _ties(measurement: dict) -> int:
    return sum(counts["ties"] for counts in measurement["rounding"].values())


def _table_csv(rows: list[dict], measurements: dict) -> str:
    """Return the bits-to-SQNR table: one line per width and frame, canonical first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_TABLE_COLUMNS)
    for row in rows:
        for key, frame in measurements[str(row["W_common"])].items():
            time, frequency = frame["time"], frame["frequency"]
            writer.writerow(
                (
                    row["W_common"],
                    f"Q2.{row['F_data']}",
                    row["role"],
                    key,
                    _db_text(time["sqnr_db"]),
                    *(_db_text(value) for value in time["split_half_sqnr_db"]),
                    _db_text(frequency["sqnr_db"]),
                    *(_db_text(value) for value in frequency["split_half_sqnr_db"]),
                    _db_text(frame["sqnr_cross_db"]),
                    time["split_half_stable"] and frequency["split_half_stable"],
                    time["internal_overflow_count"],
                    frequency["internal_overflow_count"],
                    time["output_saturation_count"],
                    frequency["output_saturation_count"],
                    _ties(time),
                    _ties(frequency),
                    row["numerically_passing"],
                )
            )
    return buffer.getvalue()


def _git_commit() -> str | None:
    """Commit checked out at generation time; the exact sources are pinned by ``source_sha256``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_SIM_DIR, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def generate_sweep_evidence(output_dir: Path = _DEFAULT_OUTPUT_DIR, vectors_dir: Path = _DEFAULT_VECTORS_DIR) -> Path:
    """Run the required width sweep on the F1 frames; write the evidence manifest and the table."""
    output_dir = Path(output_dir)
    if output_dir.resolve().is_relative_to(_DEFAULT_VECTORS_DIR.resolve()):
        raise ValueError("output_dir: sweep results are model-side evidence and never go into sim/vectors/")
    frames = {
        f"{vector_set}/{vector_case}": load_f1_frame(Path(vectors_dir), vector_set, vector_case)
        for vector_set, vector_case in iter_frames()
    }
    measurements = {}
    rows = []
    for width in SWEEP_WIDTHS:
        policy = FxpPolicy(width)
        measured = measure_width(frames, policy)
        measurements[str(width)] = measured
        rows.append(build_row(policy, measured))

    output_dir.mkdir(parents=True, exist_ok=True)
    table_path = output_dir / _TABLE_FILE
    table_path.write_text(_table_csv(rows, measurements), encoding="utf-8")

    manifest = {
        "evidence_version": "t21-width-sweep-v1",
        "stage": "fxp_width_sweep",
        "scope": "model-side diagnostic RNE width sweep and production Q2.14 validation; "
        "not fxp_expected vectors (T22, #46)",
        "hash_serialization": _HASH_SERIALIZATION,
        "sweep": {
            "widths": list(SWEEP_WIDTHS),
            "format": "Q2.(W-2) for data, coefficients, twiddles and H[k]",
            "rounding_mode": ROUNDING_MODE,
            "time_accumulator": "2W+3 (conservative base)",
            "fft_mode": FFT_MODE,
            "production_width": PRODUCTION_WIDTH,
            "optional_experiments": "not run: truncation/wrap controls, 33/34-bit accumulators and frequency B; "
            "Q1 sensitivity is outside base",
        },
        "freeze": "production-A integer freeze accepted 2026-10-09 "
        "(fxp-policy-16.md T20 amendment, sign-offs on PR #78)",
        "window": _WINDOW,
        "thresholds": {
            "sqnr_min_db": SQNR_MIN_DB,
            "sqnr_cross_min_db": SQNR_CROSS_MIN_DB,
            "split_half_tolerance_db": SPLIT_HALF_TOLERANCE_DB,
        },
        "gate_frames": {
            "sqnr": ACCEPTANCE_FRAME,
            "split_half": ACCEPTANCE_FRAME,
            "internal_overflow": list(frames),
            "output_saturation": ACCEPTANCE_FRAME,
            "sqnr_cross": f"{ACCEPTANCE_FRAME}, production width only",
        },
        "row_field_scope": {
            "sqnr_*_db, split_half_sqnr_*_db": ACCEPTANCE_FRAME,
            "internal_overflow_count": "sum over all frames and both domains",
            "output_saturation_count": f"sum over both domains on {ACCEPTANCE_FRAME}",
            "max_abs_acc_time": "largest |partial sum| of the time accumulator over all frames",
            "max_abs_acc_freq": "largest |value| over every IFFT stage (rotated and butterfly outputs), all frames",
            "stimulus_manifest_sha256": "recorded once as f1_manifest_sha256, shared by every row",
            "sys_corners": "per-domain and cross-domain SQNR and split halves are diagnostics without a threshold",
        },
        "omitted_row_fields": {
            "vector_manifest_sha256": "added after the T22 (#46) fxp_expected export",
            "latency_samples": "measured per RTL variant in F3, never guessed",
            "latency_cycles": "measured per RTL variant in F3, never guessed",
            "area_um2": "populated only after 100% vector matching",
            "fmax_mhz": "populated only after 100% vector matching",
        },
        "sqnr_reference": {
            "per_domain": "each domain against its own F1 float reference",
            "cross_domain": "time F1 float reference as common signal power",
            "null_db": "zero quantization error (infinite SQNR)",
        },
        "f1_manifest_sha256": {key: frame["manifest_sha256"] for key, frame in frames.items()},
        "rows": rows,
        "frames": measurements,
        "frontier": frontier(rows),
        "production_acceptance": production_acceptance(rows),
        "table": {"file": _TABLE_FILE, "sha256": _sha256_bytes(table_path.read_bytes())},
        "provenance": {
            "git_commit": _git_commit(),
            "source_sha256": {name: _sha256_bytes((_SIM_DIR / name).read_bytes()) for name in _SOURCE_FILES},
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "fxpmath": fxpmath.__version__,
            },
        },
    }
    manifest_path = output_dir / _MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest_path


def _spread_labels(values: list[float], gap: float) -> list[float]:
    """Move end-of-line label positions apart by at least ``gap``, keeping their order."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    placed = list(values)
    for previous, current in zip(order, order[1:]):
        placed[current] = max(placed[current], placed[previous] + gap)
    return placed


def plot_sweep(manifest_path: Path) -> Path:
    """Draw SQNR versus W on the canonical frame from a sweep manifest; return the plot manifest path.

    The plot sits next to the manifest it was drawn from. PNG bytes can vary
    across matplotlib versions, so its hash is evidence of this run only.
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    manifest_path = Path(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    rows = manifest["rows"]
    widths = [row["W_common"] for row in rows]
    production = manifest["production_acceptance"]
    smallest = manifest["frontier"]["both_domains_W"]

    fig, ax = plt.subplots(figsize=(9, 5.4))
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    ax.axvspan(production["W_common"] - 0.8, production["W_common"] + 0.8, color="0.5", alpha=0.12, linewidth=0)
    ax.axhline(SQNR_MIN_DB, color=_TEXT_SECONDARY, linestyle="--", linewidth=1.0)
    ax.axhline(SQNR_CROSS_MIN_DB, color=_TEXT_SECONDARY, linestyle=":", linewidth=1.2)

    ends = []
    for field, label, color, marker in _SERIES:
        values = [np.nan if row[field] is None else row[field] for row in rows]
        ax.plot(
            widths,
            values,
            color=color,
            linewidth=2.0,
            marker=marker,
            markersize=8,
            markeredgecolor=_SURFACE,
            markeredgewidth=1.5,
            solid_joinstyle="round",
            solid_capstyle="round",
            label=label,
        )
        ends.append((label, values[-1]))

    for (label, value), position in zip(ends, _spread_labels([value for _, value in ends], _LABEL_GAP_DB)):
        ax.annotate(
            f"{label} {value:.2f}",
            xy=(widths[-1], value),
            xytext=(widths[-1] + 0.35, position),
            va="center",
            fontsize=9,
            color=_TEXT_SECONDARY,
        )

    right = widths[-1] + 2.5
    ax.text(right, SQNR_MIN_DB + 0.6, "per-domain gate 40 dB", ha="right", va="bottom", fontsize=8, color=_TEXT_SECONDARY)
    ax.text(
        right,
        SQNR_CROSS_MIN_DB - 0.6,
        f"cross-domain gate {SQNR_CROSS_MIN_DB:.2f} dB",
        ha="right",
        va="top",
        fontsize=8,
        color=_TEXT_SECONDARY,
    )
    top = max(row[field] for row in rows for field, *_ in _SERIES if row[field] is not None)
    ax.text(
        production["W_common"],
        top + 6,
        f"production Q2.{production['W_common'] - 2}",
        ha="center",
        fontsize=9,
        color=_TEXT_PRIMARY,
    )
    if smallest is not None:
        smallest_row = next(row for row in rows if row["W_common"] == smallest)
        ax.annotate(
            f"frontier W={smallest}:\nsmallest width passing both domains",
            xy=(smallest, min(smallest_row["sqnr_time_db"], smallest_row["sqnr_freq_db"])),
            xytext=(smallest + 0.3, SQNR_MIN_DB + 1.2),
            va="bottom",
            fontsize=8,
            color=_TEXT_SECONDARY,
            arrowprops={"arrowstyle": "-", "color": _TEXT_SECONDARY, "linewidth": 0.8, "shrinkB": 5},
        )
    for row in rows:
        if row["numerically_passing"]:
            continue
        failed = [domain for domain, checks in row["criteria"].items() if not all(checks.values())]
        ax.annotate(
            f"W={row['W_common']} fails: {', '.join(failed)}",
            xy=(row["W_common"], row["sqnr_freq_db"]),
            xytext=(row["W_common"] + 0.6, SQNR_CROSS_MIN_DB - 1.2),
            va="top",
            fontsize=8,
            color=_TEXT_SECONDARY,
            arrowprops={"arrowstyle": "-", "color": _TEXT_SECONDARY, "linewidth": 0.8, "shrinkB": 5},
        )

    ax.set_xticks(widths, [f"{width}\nQ2.{width - 2}" for width in widths])
    ax.set_xlim(widths[0] - 0.6, widths[-1] + 2.6)
    ax.set_ylim(SQNR_CROSS_MIN_DB - 6, top + 12)
    ax.set_xlabel("common width W (format)", color=_TEXT_PRIMARY)
    ax.set_ylabel("SQNR on the canonical frame (dB)", color=_TEXT_PRIMARY)
    ax.tick_params(colors=_TEXT_SECONDARY)
    ax.grid(axis="y", alpha=0.25, linewidth=0.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_TEXT_SECONDARY)
    production_row = next(row for row in rows if row["W_common"] == production["W_common"])
    ax.set_title(
        "T21 width sweep: SQNR vs common width (RNE, 2W+3 time accumulator, FFT baseline A)\n"
        f"production W={production['W_common']} passes: time {production_row['sqnr_time_db']:.2f}, "
        f"frequency {production_row['sqnr_freq_db']:.2f}, cross-domain {production_row['sqnr_cross_db']:.2f} dB",
        loc="left",
        fontsize=10,
        color=_TEXT_PRIMARY,
    )
    legend = ax.legend(loc="upper left", frameon=False, fontsize=9)
    for text in legend.get_texts():
        text.set_color(_TEXT_PRIMARY)
    fig.tight_layout()
    plot_path = manifest_path.with_name(_PLOT_FILE)
    fig.savefig(plot_path, dpi=150, facecolor=_SURFACE)
    plt.close(fig)

    plot_manifest = {
        "evidence_for": "T21 (#45)",
        "plot": plot_path.name,
        "plot_sha256": _sha256_bytes(plot_path.read_bytes()),
        "drawn_from": {"file": manifest_path.name, "sha256": _sha256_bytes(manifest_bytes)},
        "frame": ACCEPTANCE_FRAME,
        "series_colors": {label: color for _, label, color, _ in _SERIES},
        "note": "PNG bytes can vary across matplotlib versions; the plot hash is evidence of this run, not a CI check",
        "versions": {"numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "source_sha256": _sha256_bytes(Path(__file__).read_bytes()),
    }
    plot_manifest_path = manifest_path.with_name(_PLOT_MANIFEST_FILE)
    plot_manifest_path.write_text(json.dumps(plot_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return plot_manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the T21 width sweep and production Q2.14 validation")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--vectors-dir", type=Path, default=_DEFAULT_VECTORS_DIR)
    parser.add_argument("--plot", action="store_true", help="also draw sqnr_vs_width.png from the written manifest")
    args = parser.parse_args()
    manifest_path = generate_sweep_evidence(args.output_dir, args.vectors_dir)
    print(manifest_path)
    if args.plot:
        print(plot_sweep(manifest_path))


if __name__ == "__main__":
    main()
