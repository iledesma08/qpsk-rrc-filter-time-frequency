"""Evidence plots of the F1 float-reference vectors (T13).

Reads the payloads written by ``gen_vectors.py`` and writes plots plus an
``evidence_manifest.json`` under ``sim/python/artifacts/``. Plots are review
evidence, not vectors: they never go into ``sim/vectors/``.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from gen_vectors import INPUT_FILE, REFERENCE_FILE, iter_frames, read_samples


_DEFAULT_PLOTS_DIR = Path(__file__).resolve().parent / "artifacts" / "t13-reference-vectors"
_I_COLOR = "#0057B8"
_Q_COLOR = "#E65100"
_ERROR_COLOR = "#0057B8"
_LINE_WIDTH = 1.0
_ATOL = 1e-12
_PREFIX_SAMPLES = 80  # 40 edge-pattern symbols * 2 samples per symbol
_PERTURBATION_SAMPLE = 1024  # symbol 512 * 2 samples per symbol
_FRAME_TITLES = {
    ("canonical", "none"): "canonical: edge patterns + 984 seeded random symbols",
    ("sys_corners", "corner_repeat"): "sys_corners / corner_repeat: +1+j x 1024 (sustained build-up)",
    ("sys_corners", "max_alternation"): "sys_corners / max_alternation: +1+j, -1-j alternating (maximum swing)",
    ("sys_corners", "single_symbol_perturbation"): "sys_corners / single_symbol_perturbation: symbol 512 = -1-j",
}
# Zoom window (sample indices) that shows what each frame is designed to stress.
_ZOOM_WINDOWS = {
    ("canonical", "none"): (0, _PREFIX_SAMPLES + 16),
    ("sys_corners", "corner_repeat"): (0, 48),
    ("sys_corners", "max_alternation"): (0, 48),
    ("sys_corners", "single_symbol_perturbation"): (_PERTURBATION_SAMPLE - 16, _PERTURBATION_SAMPLE + 32),
}
_ZOOM_NOTES = {
    ("canonical", "none"): "zoom: 40 edge-pattern symbols (shaded) + first random symbols",
    ("sys_corners", "corner_repeat"): "zoom: filter fills over the 8 taps, then holds",
    ("sys_corners", "max_alternation"): "zoom: I and Q flip every symbol",
    ("sys_corners", "single_symbol_perturbation"): "zoom: one symbol spreads through the 8 taps (dashed = sample 1024)",
}


def _frame_dir(vectors_dir: Path, vector_set: str, vector_case: str) -> Path:
    return vectors_dir / "float_reference" / vector_set / vector_case


def _style_axes(ax) -> None:
    ax.grid(alpha=0.25, linewidth=0.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _plot_iq(ax, values: np.ndarray, start: int = 0, markers: bool = False, points_only: bool = False) -> None:
    """Draw I thick underneath and Q thin dashed on top, so I stays visible where I == Q."""
    index = np.arange(start, start + values.size)
    style = {"linestyle": "None"} if points_only else {}
    if markers or points_only:
        style |= {"marker": "o" if markers else ".", "markersize": 3.5 if markers else 2.5}
    i_width, q_width = (_LINE_WIDTH, _LINE_WIDTH) if points_only else (2.4, _LINE_WIDTH)
    ax.plot(index, values.real, color=_I_COLOR, linewidth=i_width, label="I", **style)
    q_style = style if points_only else style | {"linestyle": (0, (4, 2))}
    ax.plot(index, values.imag, color=_Q_COLOR, linewidth=q_width, label="Q", **q_style)


def _plot_frame(vectors_dir: Path, vector_set: str, vector_case: str, path: Path) -> None:
    from matplotlib import pyplot as plt

    frame = _frame_dir(vectors_dir, vector_set, vector_case)
    samples = read_samples(frame / INPUT_FILE)
    reference = read_samples(frame / REFERENCE_FILE.format(tag="time"))
    zoom_start, zoom_stop = _ZOOM_WINDOWS[(vector_set, vector_case)]

    fig, (ax_in, ax_ref, ax_zoom) = plt.subplots(3, 1, figsize=(10, 9))
    _plot_iq(ax_in, samples, points_only=True)
    ax_in.set_title(_FRAME_TITLES[(vector_set, vector_case)], loc="left")
    ax_in.set(ylabel="input (2048 samples)")
    _plot_iq(ax_ref, reference)
    ax_ref.set(ylabel="float reference (2055 samples)", xlabel="sample index")
    stop = min(zoom_stop, reference.size)
    _plot_iq(ax_zoom, reference[zoom_start:stop], start=zoom_start, markers=True)
    ax_zoom.set(ylabel="reference, zoom", xlabel="sample index", title=_ZOOM_NOTES[(vector_set, vector_case)])
    if vector_set == "canonical":
        for ax in (ax_in, ax_ref, ax_zoom):
            ax.axvspan(0, _PREFIX_SAMPLES, color="0.5", alpha=0.12, linewidth=0)
    if vector_case == "single_symbol_perturbation":
        ax_zoom.axvline(_PERTURBATION_SAMPLE, color="black", linestyle="--", linewidth=0.8)
    for ax in (ax_in, ax_ref, ax_zoom):
        _style_axes(ax)
    ax_in.legend(loc="lower right", bbox_to_anchor=(1, 1.02), ncol=2, frameon=False)
    fig.text(0.99, 0.005, "I and Q coincide where a symbol is +1+j or -1-j", ha="right", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_agreement(vectors_dir: Path, path: Path) -> dict[str, float]:
    from matplotlib import pyplot as plt

    frames = iter_frames()
    fig, axes = plt.subplots(len(frames), 1, figsize=(10, 9), sharex=True, sharey=True)
    max_errors = {}
    for ax, (vector_set, vector_case) in zip(axes, frames, strict=True):
        frame = _frame_dir(vectors_dir, vector_set, vector_case)
        time_reference = read_samples(frame / REFERENCE_FILE.format(tag="time"))
        frequency_reference = read_samples(frame / REFERENCE_FILE.format(tag="freq"))
        error = np.abs(time_reference - frequency_reference)
        max_errors[f"{vector_set}/{vector_case}"] = float(error.max())
        ax.semilogy(np.arange(error.size), np.maximum(error, 1e-18), color=_ERROR_COLOR, linewidth=_LINE_WIDTH)
        ax.axhline(_ATOL, color="black", linestyle="--", linewidth=0.8)
        ax.set(ylim=(1e-18, 1e-10), ylabel="|time - freq|")
        ax.set_title(f"{vector_set} / {vector_case}  (max {error.max():.1e})", loc="left", fontsize=9)
        _style_axes(ax)
    axes[0].annotate("atol = 1e-12", xy=(1, _ATOL), xycoords=("axes fraction", "data"), ha="right", va="bottom")
    axes[-1].set_xlabel("output sample index (2055, full causal window)")
    fig.suptitle("Float time vs frequency golden: absolute error per frame (exact zeros drawn at the 1e-18 floor)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return max_errors


def generate_vector_plots(vectors_dir: Path, plots_dir: Path = _DEFAULT_PLOTS_DIR) -> Path:
    """Write per-frame plots, the agreement plot and the evidence manifest."""
    import matplotlib

    matplotlib.use("Agg")
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_paths = []
    for vector_set, vector_case in iter_frames():
        path = plots_dir / f"{vector_set}_{vector_case}.png"
        _plot_frame(vectors_dir, vector_set, vector_case, path)
        plot_paths.append(path)
    agreement_path = plots_dir / "time_frequency_agreement.png"
    max_errors = _plot_agreement(vectors_dir, agreement_path)
    plot_paths.append(agreement_path)

    payload_sha256 = {
        str(path.relative_to(vectors_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((vectors_dir / "float_reference").rglob("*.c16.bin"))
    }
    manifest = {
        "artifact_stage": "float_reference",
        "evidence_for": "T13 (#43)",
        "frames": [f"{vector_set}/{vector_case}" for vector_set, vector_case in iter_frames()],
        "interpolation": "none",
        "max_abs_time_frequency_error": max_errors,
        "atol": _ATOL,
        "plots": [path.name for path in plot_paths],
        "plot_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in plot_paths},
        "vector_payload_sha256": payload_sha256,
        "series_colors": {"I": _I_COLOR, "Q": _Q_COLOR},
        "versions": {"numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    manifest_path = plots_dir / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path
