"""T31 (#48) and T33 (#50): review plots of the RTL vector matching evidence.

The plots draw RTL outputs captured by the matching runs, so they must refuse
any capture whose hash differs from the one the evidence recorded. The
captures here are copies of the committed expected codes (plus the declared
block padding record for the frequency lane), which the committed evidence says
they equal; nothing is simulated.
"""

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import plot_matching


ROOT = Path(__file__).resolve().parents[3]
VECTORS = ROOT / "sim/vectors"
# variant_id -> (evidence directory, domain tag of the expected codes, padding records of the capture)
VARIANTS = {
    "T-serial": (ROOT / "sim/python/artifacts/t31-time-matching", "time", ""),
    "F-serial": (ROOT / "sim/python/artifacts/t33-freq-matching", "freq", "00000000\n"),
}
variants = pytest.mark.parametrize("variant", sorted(VARIANTS))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def evidence_copy(tmp_path, variant):
    """Copy the committed evidence and write one capture per frame from the expected codes."""
    source_dir, tag, padding = VARIANTS[variant]
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    shutil.copyfile(source_dir / "evidence_manifest.json", evidence_dir / "evidence_manifest.json")
    capture_dir = tmp_path / "captures"
    for key in json.loads((evidence_dir / "evidence_manifest.json").read_text())["frames"]:
        vector_set, vector_case = key.split("/")
        target = capture_dir / f"{vector_set}-{vector_case}" / "captured.hex"
        target.parent.mkdir(parents=True)
        expected = (VECTORS / "fxp_expected" / vector_set / vector_case / f"expected_{tag}.hex").read_text()
        target.write_text(expected + padding, encoding="ascii")
    return evidence_dir, capture_dir


@variants
def test_plots_draw_every_frame_and_record_an_exact_match(evidence_copy):
    evidence_dir, capture_dir = evidence_copy
    manifest = json.loads(plot_matching.generate_matching_plots(evidence_dir, capture_dir).read_text())

    frames = ["canonical/none", "sys_corners/corner_repeat", "sys_corners/max_alternation",
              "sys_corners/single_symbol_perturbation"]
    assert manifest["plots"] == [f"{key.replace('/', '_')}.png" for key in frames]
    for name in manifest["plots"]:
        assert manifest["plot_sha256"][name] == _sha256(evidence_dir / name)
    assert manifest["exact_codes"] == dict.fromkeys(frames, 2055)
    assert manifest["max_abs_error_lsb"] == dict.fromkeys(frames, 0)
    assert manifest["drawn_from"]["sha256"] == _sha256(evidence_dir / "evidence_manifest.json")


@variants
def test_plots_refuse_a_capture_the_evidence_does_not_record(evidence_copy):
    evidence_dir, capture_dir = evidence_copy
    capture = capture_dir / "sys_corners-corner_repeat" / "captured.hex"
    lines = capture.read_text(encoding="ascii").splitlines()
    lines[5] = f"{int(lines[5], 16) ^ 1:08x}"
    capture.write_text("\n".join(lines) + "\n", encoding="ascii")

    with pytest.raises(ValueError, match="hash differs"):
        plot_matching.generate_matching_plots(evidence_dir, capture_dir)
    assert not (evidence_dir / "plot_manifest.json").exists()


@variants
def test_committed_plots_were_drawn_from_the_committed_evidence(variant):
    EVIDENCE_DIR = VARIANTS[variant][0]
    manifest = json.loads((EVIDENCE_DIR / "plot_manifest.json").read_text())
    evidence = json.loads((EVIDENCE_DIR / "evidence_manifest.json").read_text())

    assert manifest["drawn_from"]["sha256"] == _sha256(EVIDENCE_DIR / "evidence_manifest.json")
    assert manifest["drawn_from"]["captured_output_sha256"] == {
        key: frame["captured_output_sha256"] for key, frame in evidence["frames"].items()}
    assert set(manifest["max_abs_error_lsb"].values()) == {0}
    for name in manifest["plots"]:
        assert (EVIDENCE_DIR / name).is_file()
