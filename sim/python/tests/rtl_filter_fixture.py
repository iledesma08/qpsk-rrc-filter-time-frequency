"""Generate T30 structural fixtures for the serial time filter outside sim/vectors.

Expected codes come from an exact integer reference of the accepted time
policy (fxp-policy-16, Numeric Policy): Q2.14 data and coefficients, products
summed at full precision with no rounding between taps, one RNE cast and
saturation to 16 bits. It is independent of the T20 FXP model (``fxp.py``),
which test_rtl_time_serial.py requires it to match, and it never casts the
float reference output. The frames check the datapath, its
rounding/saturation, II and latency; exact matching against the T22 production
vectors and the rtl_matching manifest binding belong to T31 (#48).
"""

import argparse
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
from pathlib import Path
import sys

import numpy as np

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from rrc_coefs import load_rrc8_coefficients  # noqa: E402
from stimulus import generate_canonical_samples  # noqa: E402

# Accepted production time policy (fxp-policy-16, Products and the time-domain accumulator).
WIDTH = 16
FRAC_BITS = WIDTH - 2
W_PRODUCT = 2 * WIDTH
W_ACC_TIME = 2 * WIDTH + 3
TAPS = 8
# T30 design latency (accept edge plus eight MAC edges); the TB measures it.
LATENCY_CYCLES = 9
FLUSH_SAMPLES = TAPS - 1
FRAMES = ("canonical", "impulse", "rne_ties", "saturation", "arbitrary")
MAX_CODE = (1 << (WIDTH - 1)) - 1
MIN_CODE = -(1 << (WIDTH - 1))
_ONE = 1 << FRAC_BITS


def _fits(value: int, width: int) -> bool:
    return -(1 << (width - 1)) <= value < (1 << (width - 1))


def to_code(value: float) -> int:
    """Exact RNE of ``value * 2^FRAC_BITS``; a range violation is an error, never saturation."""
    code = round(Fraction(value) * _ONE)
    if not _fits(code, WIDTH):
        raise ValueError(f"{value!r} is outside the Q2.{FRAC_BITS} range")
    return code


def coefficient_codes() -> list[int]:
    """Q2.14 codes of the frozen float taps, c[k] on delay k."""
    return [to_code(float(h)) for h in load_rrc8_coefficients()]


@dataclass
class CastCounters:
    operations: int = 0
    inexact: int = 0
    ties: int = 0
    saturated: int = 0
    max_abs_accumulator: int = 0


@dataclass
class Reference:
    i_codes: list[int]
    q_codes: list[int]
    counters: CastCounters = field(default_factory=CastCounters)


def output_cast(acc: int, counters: CastCounters | None = None) -> int:
    """Single output cast: exact RNE of ``acc / 2^FRAC_BITS``, then saturation to WIDTH bits."""
    remainder = acc % _ONE
    rounded = round(Fraction(acc, _ONE))
    code = min(max(rounded, MIN_CODE), MAX_CODE)
    if counters is not None:
        counters.operations += 1
        counters.inexact += remainder != 0
        counters.ties += remainder == _ONE // 2
        counters.saturated += code != rounded
    return code


def filter_reference(i_codes, q_codes) -> Reference:
    """Causal 8-tap FIR over the full window (source plus 7 flush zeros), exact integers."""
    coefficients = coefficient_codes()
    counters = CastCounters()
    outputs = {}
    for name, codes in (("i", i_codes), ("q", q_codes)):
        history = [0] * (TAPS - 1) + [int(code) for code in codes] + [0] * (TAPS - 1)
        component = []
        for n in range(len(codes) + TAPS - 1):
            acc = 0
            for k, coefficient in enumerate(coefficients):
                product = history[n + TAPS - 1 - k] * coefficient
                acc += product
                if not _fits(product, W_PRODUCT) or not _fits(acc, W_ACC_TIME):
                    raise ValueError(f"internal overflow at output {n}, tap {k}")
                counters.max_abs_accumulator = max(counters.max_abs_accumulator, abs(acc))
            component.append(output_cast(acc, counters))
        outputs[name] = component
    return Reference(outputs["i"], outputs["q"], counters)


def frame_codes(name: str) -> tuple[list[int], list[int]]:
    """Return the source I/Q input codes of one structural frame."""
    zeros = [(0, 0)] * TAPS
    if name == "canonical":
        samples = generate_canonical_samples()
        return [to_code(v) for v in samples.real], [to_code(v) for v in samples.imag]
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
        signs = [1 if c > 0 else -1 for c in reversed(coefficient_codes())]
        pairs = [(MAX_CODE, MIN_CODE) if s > 0 else (MIN_CODE, MAX_CODE) for s in signs] + zeros
    elif name == "arbitrary":
        rng = np.random.default_rng(47)
        pairs = [tuple(int(v) for v in row) for row in rng.integers(MIN_CODE, MAX_CODE + 1, size=(64, 2))]
    else:
        raise ValueError(f"unknown frame {name!r}; expected one of {FRAMES}")
    return [i for i, _ in pairs], [q for _, q in pairs]


def build_frame(name: str):
    """Return the input codes and the exact reference over the full causal window."""
    i_codes, q_codes = frame_codes(name)
    return i_codes, q_codes, filter_reference(i_codes, q_codes)


def _records(i_codes, q_codes) -> str:
    return "".join(f"{q & 0xffff:04X}{i & 0xffff:04X}\n" for i, q in zip(i_codes, q_codes))


def write_fixture(output: Path, name: str) -> Reference:
    """Write input/expected/manifest plus SHA-256 sidecars; return the reference."""
    golden_dir = SIM_DIR.parent / "vectors"
    output = Path(output).resolve()
    if output == golden_dir or golden_dir in output.parents:
        raise ValueError("structural fixtures must not be written into sim/vectors")
    i_codes, q_codes, reference = build_frame(name)
    source = len(i_codes)
    outputs = source + FLUSH_SAMPLES
    fields = {
        "DATA_WIDTH": WIDTH, "SPC": 1,
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
    manifest = f"// Generated T30 structural fixture '{name}' from an exact integer reference;\n"
    manifest += "// not a T22 expected-code set or a T31 rtl_matching manifest.\n"
    manifest += "`define RRC_TIME_FILTER_FIXTURE\n"
    manifest += "".join(f"localparam integer {key} = {value};\n" for key, value in fields.items())
    contents = {
        "input.hex": _records(i_codes, q_codes),
        "expected.hex": _records(reference.i_codes, reference.q_codes),
        "vector_manifest.svh": manifest,
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, text in contents.items():
        (output / filename).write_text(text, encoding="ascii")
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        (output / f"{filename}.sha256").write_text(f"{digest}  {filename}\n", encoding="ascii")
    return reference


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
