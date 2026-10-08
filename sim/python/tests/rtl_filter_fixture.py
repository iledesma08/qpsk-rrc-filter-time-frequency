"""Generate T30 structural fixtures for the serial time filter outside sim/vectors.

Expected codes come from the T20 integer time model (``fxp.filter_time_fxp``),
never from a cast of the float reference. The frames check the datapath, its
rounding/saturation, II and latency; exact matching against the T22 production
vectors and the rtl_matching manifest binding belong to T31 (#48).
"""

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from fxp import (  # noqa: E402
    FILTER_LENGTH, PRODUCTION_POLICY, decode, filter_time_fxp, quantize_coefficients, quantize_samples,
)
from stimulus import generate_canonical_samples  # noqa: E402

# T30 design latency (accept edge plus eight MAC edges); the TB measures it.
LATENCY_CYCLES = 9
FLUSH_SAMPLES = FILTER_LENGTH - 1
FRAMES = ("canonical", "impulse", "rne_ties", "saturation", "arbitrary")
_MAX_CODE = (1 << (PRODUCTION_POLICY.width - 1)) - 1
_MIN_CODE = -(1 << (PRODUCTION_POLICY.width - 1))
_ONE = 1 << PRODUCTION_POLICY.fraction_bits


def frame_codes(name: str) -> tuple[np.ndarray, np.ndarray]:
    """Return the source I/Q input codes of one structural frame."""
    zeros = [(0, 0)] * FILTER_LENGTH
    if name == "canonical":
        i_codes, q_codes = quantize_samples(generate_canonical_samples())
        return i_codes.astype(np.int64), q_codes.astype(np.int64)
    if name == "impulse":
        # x[0] = 1 - j, so y[0:8] = c * (1 - j) exposes every coefficient on I and Q.
        pairs = [(_ONE, -_ONE)] + zeros
    elif name == "rne_ties":
        # +/-0.5 impulses: odd c[k] * 2^13 ends in exactly half an LSB, so the
        # cast rounds both up and down to the even code.
        half = _ONE // 2
        pairs = [(half, -half)] + zeros + [(-half, half)] + zeros
    elif name == "saturation":
        # Full-scale inputs aligned with the coefficient signs drive y[7] past
        # both output limits (I positive, Q negative).
        signs = np.sign(quantize_coefficients().astype(np.int64))[::-1]
        pairs = [(_MAX_CODE, _MIN_CODE) if s > 0 else (_MIN_CODE, _MAX_CODE) for s in signs] + zeros
    elif name == "arbitrary":
        rng = np.random.default_rng(47)
        pairs = [tuple(int(v) for v in row) for row in rng.integers(_MIN_CODE, _MAX_CODE + 1, size=(64, 2))]
    else:
        raise ValueError(f"unknown frame {name!r}; expected one of {FRAMES}")
    codes = np.array(pairs, dtype=np.int64)
    return codes[:, 0], codes[:, 1]


def build_frame(name: str):
    """Return the input codes and the integer model result (full causal window)."""
    i_codes, q_codes = frame_codes(name)
    result = filter_time_fxp(decode(i_codes, q_codes, PRODUCTION_POLICY.fraction_bits))
    if result.monitor.internal_overflow_count:
        raise ValueError(f"frame {name!r}: internal overflow in the integer model")
    return i_codes, q_codes, result


def _records(i_codes, q_codes) -> str:
    return "".join(f"{int(q) & 0xffff:04X}{int(i) & 0xffff:04X}\n" for i, q in zip(i_codes, q_codes))


def write_fixture(output: Path, name: str):
    """Write input/expected/manifest plus SHA-256 sidecars; return the model result."""
    golden_dir = SIM_DIR.parent / "vectors"
    output = Path(output).resolve()
    if output == golden_dir or golden_dir in output.parents:
        raise ValueError("structural fixtures must not be written into sim/vectors")
    i_codes, q_codes, result = build_frame(name)
    source = int(i_codes.size)
    outputs = source + FLUSH_SAMPLES
    fields = {
        "DATA_WIDTH": PRODUCTION_POLICY.width, "SPC": 1,
        "input_samples": source, "output_samples": outputs,
        "valid_start": 0, "valid_len": outputs,
        "flush_samples": FLUSH_SAMPLES, "transport_padding_samples": 0,
        "accepted_input_samples": outputs, "raw_output_samples": outputs,
        "latency_samples": 0, "latency_cycles": LATENCY_CYCLES,
        # Accepted baseline mirrored from rrc_pkg.sv; the TB checks agreement.
        "FFT_LEN": 16, "HOP": 8, "DISCARD_PREFIX": 8,
        "EMIT_START": 8, "EMIT_LEN": 8,
        "block_cadence": 8, "fft_pipeline_cycles": 0,
    }
    manifest = f"// Generated T30 structural fixture '{name}' from the T20 integer time model;\n"
    manifest += "// not a T22 expected-code set or a T31 rtl_matching manifest.\n"
    manifest += "`define RRC_TIME_FILTER_FIXTURE\n"
    manifest += "".join(f"localparam integer {key} = {value};\n" for key, value in fields.items())
    contents = {
        "input.hex": _records(i_codes, q_codes),
        "expected.hex": _records(result.i_codes, result.q_codes),
        "vector_manifest.svh": manifest,
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, text in contents.items():
        (output / filename).write_text(text, encoding="ascii")
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        (output / f"{filename}.sha256").write_text(f"{digest}  {filename}\n", encoding="ascii")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame", choices=FRAMES, default="canonical")
    args = parser.parse_args()
    try:
        write_fixture(args.output, args.frame)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
