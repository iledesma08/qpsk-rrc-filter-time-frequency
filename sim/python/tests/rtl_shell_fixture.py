"""Generate transport-only fixtures outside the protected RRC golden directory."""

import argparse
import hashlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-width", type=int, default=16)
    parser.add_argument("--spc", type=int, default=1)
    parser.add_argument("--count", type=int, default=33)
    parser.add_argument("--flush-samples", type=int, default=0)
    args = parser.parse_args()
    if not 2 <= args.data_width <= 16 or args.spc < 1 or args.count < 1 or args.flush_samples < 0:
        parser.error("require 2 <= DATA_WIDTH <= 16, SPC >= 1, count >= 1 and flush_samples >= 0")
    golden_dir = Path(__file__).resolve().parents[2] / "vectors"
    output = args.output.resolve()
    if output == golden_dir or golden_dir in output.parents:
        parser.error("shell fixtures must not be written into sim/vectors")

    limit = 1 << (args.data_width - 1)
    pairs = [(1, -1), (-limit, limit - 1), (limit - 1, -limit), (0, -1), (-1, 0)]
    pairs += [
        ((17 * n) % (2 * limit) - limit, (29 * n + 3) % (2 * limit) - limit)
        for n in range(5, args.count)
    ]
    records = "".join(f"{q & 0xffff:04X}{i & 0xffff:04X}\n" for i, q in pairs[:args.count])
    logical_samples = args.count + args.flush_samples
    padding = (-logical_samples) % args.spc
    accepted = logical_samples + padding
    expected = records + "00000000\n" * args.flush_samples
    fields = {
        "DATA_WIDTH": args.data_width, "SPC": args.spc,
        "input_samples": args.count, "output_samples": logical_samples,
        "valid_start": 0, "valid_len": logical_samples,
        "flush_samples": args.flush_samples, "transport_padding_samples": padding,
        "accepted_input_samples": accepted, "raw_output_samples": accepted,
        "latency_samples": 0, "latency_cycles": 1,
        "FFT_LEN": 16, "HOP": 8, "DISCARD_PREFIX": 8,
        "EMIT_START": 8, "EMIT_LEN": 8,
        "block_cadence": 8, "fft_pipeline_cycles": 0,
    }
    manifest = "// Generated shell smoke metadata; not a canonical RRC manifest.\n"
    manifest += "`define RRC_SHELL_FIXTURE\n"
    manifest += "".join(f"localparam integer {name} = {value};\n" for name, value in fields.items())
    output.mkdir(parents=True, exist_ok=True)
    for name, contents in (("input.hex", records), ("expected.hex", expected), ("vector_manifest.svh", manifest)):
        (output / name).write_text(contents, encoding="ascii")
        digest = hashlib.sha256(contents.encode("ascii")).hexdigest()
        (output / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="ascii")


if __name__ == "__main__":
    main()
