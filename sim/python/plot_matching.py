"""Review plots of the RTL vector matching evidence (T31 #48 time, T33 #50 and T42 #53 frequency).

Reads the matching evidence written by ``tests/rtl_matching_stage.py
--evidence-dir`` and the RTL outputs its continuous runs captured, checks that
every capture still has the hash the evidence recorded (the hash of the bound
expected codes), then draws one plot per frame: the captured RTL output over
the full causal window, a zoom with the float reference, the expected codes and
the RTL output, and the RTL minus expected error in LSB. A frequency capture has
one more record than the expected codes (the declared block padding): the plots
draw the compared window and the capture hash still covers the whole file. It
writes the plots and
``plot_manifest.json`` next to the evidence. Plots are review evidence, never
vectors.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from gen_vectors import EXPECTED_HEX_FILE, REFERENCE_FILE, read_samples
from plot_vectors import (
    _FRAME_TITLES, _I_COLOR, _LINE_WIDTH, _PERTURBATION_SAMPLE, _PREFIX_SAMPLES, _Q_COLOR, _ZOOM_NOTES, _ZOOM_WINDOWS,
    _style_axes,
)


_SIM_DIR = Path(__file__).resolve().parent
_VECTORS_DIR = _SIM_DIR.parent / "vectors"
_BUILD_MATCHING_DIR = _SIM_DIR.parents[1] / ".build" / "rtl" / "matching"
# variant_id -> (evidence directory, task named in plot_manifest.json)
_VARIANTS = {
    "T-serial": ("t31-time-matching", "T31 (#48)"),
    "F-serial": ("t33-freq-matching", "T33 (#50)"),
    "F-U4": ("t42-freq-opt-matching/F-U4", "T42 (#53)"),
    "F-U8": ("t42-freq-opt-matching/F-U8", "T42 (#53)"),
}
_DEFAULT_VARIANT = "T-serial"
_DEFAULT_EVIDENCE_DIR = _SIM_DIR / "artifacts" / _VARIANTS[_DEFAULT_VARIANT][0]
_DEFAULT_CAPTURE_DIR = _BUILD_MATCHING_DIR / _DEFAULT_VARIANT
_CAPTURE_FILE = "captured.hex"
_DOMAIN_TAG = {"time": "time", "frequency": "freq"}
_FRAC_BITS = 14
_SOURCE_SAMPLES = 2048
_MARKER_EDGE = "#ffffff"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checked(path: Path, expected_sha256: str) -> bytes:
    data = path.read_bytes()
    if _sha256(data) != expected_sha256:
        raise ValueError(f"{path}: hash differs from the one the matching evidence recorded")
    return data


def _codes(data: bytes) -> np.ndarray:
    """Decode packed ``{Q[15:0], I[15:0]}`` records into complex integer codes I + jQ."""
    words = np.array([int(token, 16) for token in data.split()], dtype=np.int64)

    def signed(field: np.ndarray) -> np.ndarray:
        return np.where(field >= 1 << 15, field - (1 << 16), field)

    return signed(words & 0xFFFF) + 1j * signed(words >> 16)


def _plot_iq(ax, index: np.ndarray, values: np.ndarray) -> None:
    """I thick underneath, Q thin dashed on top, as in the T13 plots."""
    ax.plot(index, values.real, color=_I_COLOR, linewidth=2.4, label="I")
    ax.plot(index, values.imag, color=_Q_COLOR, linewidth=_LINE_WIDTH, linestyle=(0, (4, 2)), label="Q")


def _plot_frame(key: tuple[str, str], captured: np.ndarray, expected: np.ndarray, reference: np.ndarray,
                variant_id: str, path: Path) -> None:
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D

    scale = 1 << _FRAC_BITS
    index = np.arange(captured.size)
    error = captured - expected
    exact = int(np.count_nonzero(error == 0))
    zoom_start, zoom_stop = _ZOOM_WINDOWS[key]
    zoom = slice(zoom_start, min(zoom_stop, captured.size))

    fig, (ax_all, ax_zoom, ax_err) = plt.subplots(3, 1, figsize=(10, 9.5), gridspec_kw={"height_ratios": [3, 3, 2]})
    fig.suptitle(f"{variant_id} RTL vs FXP expected codes - {_FRAME_TITLES[key]}", x=0.01, ha="left", fontsize=11)
    _plot_iq(ax_all, index, captured / scale)
    ax_all.set(
        ylabel="RTL output",
        xlabel=f"output sample index ({_SOURCE_SAMPLES} source + {captured.size - _SOURCE_SAMPLES} flush outputs)",
    )

    # Zoom: color says I or Q; the mark says where the value comes from.
    zoom_index = index[zoom]
    for part, color in ((np.real, _I_COLOR), (np.imag, _Q_COLOR)):
        ax_zoom.plot(zoom_index, part(reference[zoom]), color=color, linewidth=_LINE_WIDTH)
        ax_zoom.plot(zoom_index, part(expected[zoom]) / scale, linestyle="None", marker="o", markersize=8,
                     markerfacecolor="none", markeredgecolor=color, markeredgewidth=1.2)
        ax_zoom.plot(zoom_index, part(captured[zoom]) / scale, linestyle="None", marker="o", markersize=3.5,
                     color=color, markeredgecolor=_MARKER_EDGE, markeredgewidth=0.5)
    ax_zoom.set(ylabel="zoom", xlabel="output sample index")
    ax_zoom.set_title(_ZOOM_NOTES[key], loc="left", fontsize=9)
    if key[0] == "canonical":
        ax_zoom.axvspan(0, _PREFIX_SAMPLES, color="0.5", alpha=0.12, linewidth=0)
    keys = [
        Line2D([], [], color=_I_COLOR, linewidth=2.4, label="I"),
        Line2D([], [], color=_Q_COLOR, linewidth=_LINE_WIDTH, linestyle=(0, (4, 2)), label="Q"),
        Line2D([], [], color="0.35", linewidth=_LINE_WIDTH, label="float reference"),
        Line2D([], [], color="0.35", linestyle="None", marker="o", markersize=8, markerfacecolor="none",
               label="FXP expected code"),
        Line2D([], [], color="0.35", linestyle="None", marker="o", markersize=3.5, label="RTL output"),
    ]
    fig.legend(handles=keys, loc="upper right", bbox_to_anchor=(0.99, 0.955), ncol=len(keys), frameon=False,
               fontsize=8)

    _plot_iq(ax_err, index, error)
    ax_err.set(ylim=(-1.5, 1.5), yticks=[-1, 0, 1], ylabel="RTL - expected (LSB)", xlabel="output sample index")
    ax_err.set_title(
        f"{exact}/{captured.size} codes exact, max |RTL - expected| = {int(np.abs(error.real).max(initial=0))} LSB (I), "
        f"{int(np.abs(error.imag).max(initial=0))} LSB (Q)",
        loc="left", fontsize=9,
    )
    if key[1] == "single_symbol_perturbation":
        ax_zoom.axvline(_PERTURBATION_SAMPLE, color="black", linestyle="--", linewidth=0.8)
    for ax in (ax_all, ax_zoom, ax_err):
        _style_axes(ax)
    fig.text(0.99, 0.005, "Values in Q2.14 units (code / 2^14); I and Q coincide where a symbol is +1+j or -1-j",
             ha="right", va="bottom", fontsize=8)
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def generate_matching_plots(evidence_dir: Path = _DEFAULT_EVIDENCE_DIR, capture_dir: Path = _DEFAULT_CAPTURE_DIR,
                            vectors_dir: Path = _VECTORS_DIR) -> Path:
    """Check the captures against the evidence, write one plot per frame and ``plot_manifest.json``."""
    import matplotlib

    matplotlib.use("Agg")
    evidence_dir, capture_dir, vectors_dir = Path(evidence_dir), Path(capture_dir), Path(vectors_dir)
    evidence_bytes = (evidence_dir / "evidence_manifest.json").read_bytes()
    evidence = json.loads(evidence_bytes)
    tag = _DOMAIN_TAG[evidence["model_domain"]]

    plots, max_errors, exact_codes, captured_hashes = [], {}, {}, {}
    for frame_key, frame in sorted(evidence["frames"].items()):
        vector_set, vector_case = frame_key.split("/")
        captured_sha256 = frame["captured_output_sha256"]
        bound_expected = frame["bound_sha256"]["expected_hex"]
        # Time: the capture is the expected codes. Frequency: the capture is the expected codes plus the declared
        # block padding, and the evidence records the hash of the compared window separately.
        window_sha256 = frame.get("captured_valid_window_sha256", captured_sha256)
        if window_sha256 != bound_expected:
            raise ValueError(f"{frame_key}: the evidence does not record a capture equal to the expected codes")
        captured = _codes(_checked(capture_dir / f"{vector_set}-{vector_case}" / _CAPTURE_FILE, captured_sha256))
        expected_path = vectors_dir / "fxp_expected" / vector_set / vector_case / EXPECTED_HEX_FILE.format(tag=tag)
        expected = _codes(_checked(expected_path, bound_expected))
        captured = captured[:expected.size]
        reference_path = vectors_dir / "float_reference" / vector_set / vector_case / REFERENCE_FILE.format(tag=tag)
        digest, _ = reference_path.with_name(reference_path.name + ".sha256").read_text(encoding="utf-8").split()
        _checked(reference_path, digest)
        reference = read_samples(reference_path)
        if not captured.size == expected.size == reference.size:
            raise ValueError(f"{frame_key}: captured, expected and reference lengths differ")
        path = evidence_dir / f"{vector_set}_{vector_case}.png"
        _plot_frame((vector_set, vector_case), captured, expected, reference, evidence["variant_id"], path)
        error = captured - expected
        plots.append(path)
        max_errors[frame_key] = int(max(np.abs(error.real).max(), np.abs(error.imag).max()))
        exact_codes[frame_key] = int(np.count_nonzero(error == 0))
        captured_hashes[frame_key] = captured_sha256

    manifest = {
        "evidence_for": _VARIANTS[evidence["variant_id"]][1],
        "variant_id": evidence["variant_id"],
        "drawn_from": {
            "file": "evidence_manifest.json",
            "sha256": _sha256(evidence_bytes),
            "captured_output_sha256": captured_hashes,
        },
        "plots": [path.name for path in plots],
        "plot_sha256": {path.name: _sha256(path.read_bytes()) for path in plots},
        "max_abs_error_lsb": max_errors,
        "exact_codes": exact_codes,
        "series_colors": {"I": _I_COLOR, "Q": _Q_COLOR},
        "note": "PNG bytes can vary across matplotlib versions; the plot hash is evidence of this run, not a CI check",
        "versions": {"numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "source_sha256": _sha256(Path(__file__).read_bytes()),
    }
    manifest_path = evidence_dir / "plot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot the RTL vector matching evidence (T31, T33, T42)")
    parser.add_argument("--variant", choices=sorted(_VARIANTS), default=_DEFAULT_VARIANT,
                        help="variant whose evidence to plot; sets the default directories")
    parser.add_argument("--evidence-dir", type=Path,
                        help="default: the variant's directory under sim/python/artifacts")
    parser.add_argument("--capture-dir", type=Path,
                        help="build directory where rtl_matching_stage.py --evidence-dir staged and captured each "
                             "frame (default: .build/rtl/matching/<variant>)")
    args = parser.parse_args()
    evidence_dir = args.evidence_dir or _SIM_DIR / "artifacts" / _VARIANTS[args.variant][0]
    capture_dir = args.capture_dir or _BUILD_MATCHING_DIR / args.variant
    try:
        print(generate_matching_plots(evidence_dir, capture_dir))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
