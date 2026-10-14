"""Structural fixture for the frequency-domain serial filter (T32, #49).

Builds a vector directory for ``rrc_stream_tb`` from the T22 ``fxp_expected``
vectors already on ``main``: ``input.hex``, ``expected.hex`` (the frequency
domain codes), a metadata-only ``vector_manifest.svh`` and SHA-256 sidecars.
It only reads ``sim/vectors/`` and refuses to write into it. It is not the
``rtl_matching`` stage: the committed per-variant manifest, its hashes and the
formal matching report belong to T33 (#50), and this fixture does not pre-empt
them. Standard library only, so the RTL CI job needs no NumPy.
"""

import argparse
import hashlib
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VECTORS = ROOT / "sim" / "vectors"
FRAMES = {
    "canonical": ("canonical", "none"),
    "corner_repeat": ("sys_corners", "corner_repeat"),
    "max_alternation": ("sys_corners", "max_alternation"),
    "single_symbol_perturbation": ("sys_corners", "single_symbol_perturbation"),
}
# Design latency of freq_serial, measured by the testbench in an unstalled run:
# 8 accept + 1 load + 89 run + 1 output load. The testbench checks it, so a
# change of the schedule fails here until this number is updated on purpose.
LATENCY_CYCLES = 99
# Accepted/raw counts at SPC=1: 2048 source records + 8 flush zeros = 257 blocks.
FIELDS = {
    "DATA_WIDTH": 16, "SPC": 1, "input_samples": 2048, "output_samples": 2055,
    "valid_start": 0, "valid_len": 2055, "flush_samples": 8, "transport_padding_samples": 0,
    "accepted_input_samples": 2056, "raw_output_samples": 2056, "latency_samples": 0,
    "latency_cycles": LATENCY_CYCLES, "FFT_LEN": 16, "HOP": 8, "DISCARD_PREFIX": 8,
    "EMIT_START": 8, "EMIT_LEN": 8, "block_cadence": 8, "fft_pipeline_cycles": 0,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked_source(path: Path) -> Path:
    """Return ``path`` after checking its T22 sidecar, so a stale copy cannot pass."""
    digest, _ = path.with_name(path.name + ".sha256").read_text(encoding="utf-8").split()
    if digest != _sha256(path):
        raise ValueError(f"{path}: hash does not match its sidecar")
    return path


def write_fixture(output: Path, frame: str = "canonical") -> Path:
    """Write the fixture of ``frame`` into ``output`` and return it."""
    if frame not in FRAMES:
        raise ValueError(f"frame: expected one of {sorted(FRAMES)}, got {frame!r}")
    output = Path(output).resolve()
    if output.is_relative_to(VECTORS.resolve()):
        raise ValueError("output: structural fixtures never go into sim/vectors/")
    vector_set, vector_case = FRAMES[frame]
    source = VECTORS / "fxp_expected" / vector_set / vector_case
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_checked_source(source / "input.hex"), output / "input.hex")
    shutil.copyfile(_checked_source(source / "expected_freq.hex"), output / "expected.hex")
    manifest = (
        "// Structural fixture metadata for freq_serial (T32); not an rtl_matching manifest.\n"
        "`define RRC_STRUCTURAL_FIXTURE\n"
        + "".join(f"localparam integer {name} = {value};\n" for name, value in FIELDS.items())
    )
    (output / "vector_manifest.svh").write_text(manifest, encoding="utf-8")
    for name in ("input.hex", "expected.hex", "vector_manifest.svh"):
        (output / f"{name}.sha256").write_text(f"{_sha256(output / name)}  {name}\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a freq_serial structural fixture from the T22 vectors")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame", choices=sorted(FRAMES), default="canonical")
    arguments = parser.parse_args()
    print(write_fixture(arguments.output, arguments.frame))


if __name__ == "__main__":
    main()
