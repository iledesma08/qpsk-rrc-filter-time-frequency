"""Stage the committed rtl_matching vectors of one variant for rrc_stream_tb (T31 #48, T33 #50, T40 #51).

``sim/vectors/rtl_matching/<variant_id>/<vector_set>/<vector_case>/`` holds only
metadata: the JSON manifest and the ``vector_manifest.svh`` the testbench
includes. The numeric payloads stay in ``sim/vectors/fxp_expected/`` and the
manifest binds them by hash. Staging checks every sidecar, every bound hash and
that the ``.svh`` localparams equal the manifest, then copies ``input.hex``,
``expected.hex`` and the ``.svh`` into a build directory (never
``sim/vectors/``), where ``rtl/run_variant.sh`` checks the sidecars again before
compiling. A parameterized RTL source gets its matrix row from the manifest's
``rtl_parameters`` (T40: ``SYSTOLIC_PES``/``PIPELINE_DEPTH`` of time_opt),
passed to the runner as arguments. With ``--evidence-dir`` it runs every frame,
captures the RTL outputs of the continuous run next to each staged frame and
writes the matching evidence. For the frequency variant the evidence also holds the block timing and
the VCD coverage of the continuous run (T33). Standard library only, so the RTL CI job needs no
NumPy.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[3]
VECTORS = ROOT / "sim" / "vectors"
FRAMES = (
    ("canonical", "none"),
    ("sys_corners", "corner_repeat"),
    ("sys_corners", "max_alternation"),
    ("sys_corners", "single_symbol_perturbation"),
)
SVH_FILE = "vector_manifest.svh"
# Outputs the testbench captured in the continuous run (+capture_file), per staged frame.
CAPTURE_FILE = "captured.hex"
# Payload entries of the manifest and the hash each one must match.
_BOUND_PAYLOADS = (
    ("input_file", "input_hex_sha256"),
    ("expected_file", "expected_hex_sha256"),
    ("fxp_expected_manifest", "fxp_expected_manifest_sha256"),
)
_LOCALPARAM = re.compile(r"^localparam integer (\w+) = (-?\d+);$", re.M)
_FIELD = re.compile(r"(\w+)=(\S+)")
# Runner argument of each rtl_parameters entry (rtl/run_variant.sh).
_RUNNER_FLAGS = {"SYSTOLIC_PES": "--systolic-pes", "PIPELINE_DEPTH": "--pipeline-depth", "U": "--lanes"}
TIME_TAPS = 8
# The ports and the engine control state of a frequency variant over the unstalled run (T33, #50).
# It is the proof that the run covers every block, not the activity file of T43.
VCD_FILE = "run.vcd"
# Control states of rrc_freq_engine that the VCD records once per block, by value.
_ENGINE_STATES = {1: "load", 2: "run", 3: "emit", 4: "drain"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path: Path) -> bytes:
    """Return the bytes of ``path`` after checking its ``sha256sum``-format sidecar."""
    data = path.read_bytes()
    digest, name = path.with_name(path.name + ".sha256").read_text(encoding="utf-8").split()
    if name != path.name or digest != _sha256(data):
        raise ValueError(f"{path}: hash does not match its sidecar")
    return data


def svh_fields(text: str) -> dict[str, int]:
    """Return the integer localparams of a generated ``vector_manifest.svh``."""
    return {name: int(value) for name, value in _LOCALPARAM.findall(text)}


def load_matching(variant_id: str, vector_set: str, vector_case: str, vectors: Path = VECTORS) -> dict:
    """Return one checked rtl_matching frame: its manifest, ``.svh`` and bound payload bytes."""
    vectors = Path(vectors)
    frame_dir = vectors / "rtl_matching" / variant_id / vector_set / vector_case
    manifests = sorted(frame_dir.glob("manifest_*.json"))
    if len(manifests) != 1:
        raise ValueError(f"{frame_dir}: expected exactly one rtl_matching manifest")
    manifest_bytes = checked_bytes(manifests[0])
    manifest = json.loads(manifest_bytes)
    identity = tuple(manifest.get(key) for key in ("artifact_stage", "variant_id", "vector_set", "vector_case"))
    if identity != ("rtl_matching", variant_id, vector_set, vector_case):
        raise ValueError(f"{manifests[0]}: not the rtl_matching manifest of {variant_id} {vector_set}/{vector_case}")
    hashes = manifest["hashes"]
    svh = checked_bytes(frame_dir / SVH_FILE)
    if _sha256(svh) != hashes["vector_manifest_svh_sha256"]:
        raise ValueError(f"vector_manifest_svh_sha256: {frame_dir / SVH_FILE} differs from the metadata this manifest binds")
    fields = svh_fields(svh.decode("ascii"))
    disagreeing = sorted(name for name, value in fields.items() if manifest.get(name) != value)
    if not fields or disagreeing:
        raise ValueError(f"{SVH_FILE}: localparams disagree with the manifest {disagreeing}")
    fxp_dir = (vectors / "fxp_expected").resolve()
    payloads = {}
    for entry, hash_key in _BOUND_PAYLOADS:
        path = (frame_dir / manifest["payload"][entry]).resolve()
        if not path.is_relative_to(fxp_dir):
            raise ValueError(f"{entry}: payloads come from fxp_expected/, got {path}")
        data = checked_bytes(path)
        if _sha256(data) != hashes[hash_key]:
            raise ValueError(f"{hash_key}: {path} differs from the payload this manifest binds")
        payloads[entry] = data
    return {
        "manifest": manifest,
        "manifest_sha256": _sha256(manifest_bytes),
        "svh": svh,
        "input": payloads["input_file"],
        "expected": payloads["expected_file"],
    }


def stage(output: Path, variant_id: str, vector_set: str, vector_case: str, vectors: Path = VECTORS) -> Path:
    """Copy one checked frame into ``output`` as ``input.hex``/``expected.hex``/``.svh`` with sidecars."""
    output = Path(output).resolve()
    for protected in {VECTORS.resolve(), Path(vectors).resolve()}:
        if output.is_relative_to(protected):
            raise ValueError("output: staged vectors never go into sim/vectors/")
    frame = load_matching(variant_id, vector_set, vector_case, vectors)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in (("input.hex", frame["input"]), ("expected.hex", frame["expected"]), (SVH_FILE, frame["svh"])):
        (output / name).write_bytes(data)
        (output / f"{name}.sha256").write_text(f"{_sha256(data)}  {name}\n", encoding="utf-8")
    return output


def runner_arguments(parameters: dict[str, int]) -> list[str]:
    """Return the runner arguments that select the matrix row named by ``rtl_parameters``."""
    unknown = sorted(set(parameters) - set(_RUNNER_FLAGS))
    if unknown:
        raise ValueError(f"rtl_parameters: no runner argument for {unknown}")
    return [item for name, value in sorted(parameters.items()) for item in (_RUNNER_FLAGS[name], str(value))]


def expected_ii(manifest: dict) -> int | None:
    """Return the initiation interval a time variant must measure, ``8/S`` (T-serial is ``S=1``)."""
    if manifest["model_domain"] != "time":
        return None
    return TIME_TAPS // manifest.get("rtl_parameters", {}).get("SYSTOLIC_PES", 1)


def expected_block_timing(manifest: dict) -> dict | None:
    """Return the block-level timing a frequency variant must measure, from its own manifest.

    ``None`` unless the variant is one of the frequency engines (F-serial and the F-U rows, one source):
    the schedule below is theirs, and a different architecture must declare its own instead of inheriting
    it. With ``U`` lanes (``rtl_parameters``, 1 for F-serial) a pass takes ``8/U + 1`` cycles, ``16/U + 1``
    for the product, so ``fft_pipeline_cycles`` must be ``80/U + 9`` (89, 29, 19). One block takes ``HOP``
    cycles to accept, one to load, ``fft_pipeline_cycles`` to run, ``EMIT_LEN`` to emit and one to drain,
    so a continuous run starts a block every ``HOP + 1 + fft_pipeline_cycles + EMIT_LEN + 1`` cycles. The
    first 257 - 1 = 256 intervals are the steady-state ones (ppa-matrix-18, Workload). Fill is the first
    accepted sample to the first valid output; tail is the last accepted sample (the last flush beat) to
    the last output beat, which is the fill without the other ``HOP - 1`` accept cycles and plus the other
    ``EMIT_LEN - 1`` (it ends on the block padding, so it equals the fill only because
    ``HOP == EMIT_LEN``). The source tail is what the tail-flush block costs: the last source sample to
    the last valid output, ``block_ii`` later than the block of that sample plus the fill and the
    difference of the two positions inside their blocks (``valid_start == 0``, ``latency_samples == 0``).
    """
    if manifest["rtl_variant"] not in ("freq_serial", "freq_opt"):
        return None
    lanes = manifest.get("rtl_parameters", {}).get("U", 1)
    if manifest["fft_pipeline_cycles"] != 80 // lanes + 9:
        raise ValueError(f"fft_pipeline_cycles: {lanes} lanes run FFT + product + IFFT in {80 // lanes + 9} cycles")
    hop, emit = manifest["HOP"], manifest["EMIT_LEN"]
    blocks = manifest["accepted_input_samples"] // hop
    block_ii = hop + 1 + manifest["fft_pipeline_cycles"] + emit + 1
    source = manifest["accepted_input_samples"] - manifest["flush_samples"] - manifest["transport_padding_samples"]
    last_valid, last_source = manifest["valid_start"] + manifest["valid_len"] - 1, source - 1
    return {
        "blocks": blocks,
        "block_ii_count": blocks - 1,
        "block_ii": block_ii,
        "fill_latency_cycles": manifest["latency_cycles"],
        "tail_latency_cycles": manifest["latency_cycles"] - (hop - 1) + (emit - 1),
        "source_tail_latency_cycles": ((last_valid // hop - last_source // hop) * block_ii
                                       + manifest["latency_cycles"] + last_valid % hop - last_source % hop),
    }


def summarize_vcd(path: Path, expected_blocks: int) -> dict:
    """Return how much of the run a testbench VCD covers, counted from the engine state it records.

    Every block enters LOAD, RUN, EMIT and DRAIN once, so a dump that covers all
    blocks has ``expected_blocks`` entries of each. The hash is over the value
    changes only: the header carries the date of the run.
    """
    text = Path(path).read_bytes().decode("ascii")
    header, marker, body = text.partition("$enddefinitions $end")
    state = re.search(r"\$var \w+ \d+ (\S+) state \[2:0\] \$end", header)
    if not marker or state is None:
        raise ValueError(f"{path}: not a VCD with the engine state")
    body = body.partition("$dumpoff")[0]
    entries = {name: 0 for name in _ENGINE_STATES.values()}
    previous, last_time = 0, 0
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            last_time = int(line[1:])
        elif line.startswith("b"):
            bits, _, identifier = line[1:].partition(" ")
            if identifier == state.group(1) and set(bits) <= {"0", "1"}:
                value = int(bits, 2)
                if value != previous and value in _ENGINE_STATES:
                    entries[_ENGINE_STATES[value]] += 1
                previous = value
    return {
        "bytes": len(text.encode("ascii")),
        "value_changes_sha256": _sha256(body.encode("ascii")),
        "last_time": last_time,
        "timescale": " ".join(re.search(r"\$timescale\s+(.*?)\s+\$end", header, re.S).group(1).split()),
        "engine_state_entries": entries,
        "blocks_expected": expected_blocks,
        "covers_all_blocks": all(count == expected_blocks for count in entries.values()),
    }


def run_matching(rtl_variant: str, staged: Path, capture: Path | None = None,
                 parameters: dict[str, int] | None = None, vcd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the variant's runner on a staged frame (shared testbench, Icarus).

    With ``capture`` the testbench also writes every output of its continuous
    run there, one packed ``{Q,I}`` record per line, in the ``.hex`` format.
    ``parameters`` (the manifest's ``rtl_parameters``) selects the matrix row.
    """
    arguments = ["--vectors", str(staged)] + (["--capture", str(capture)] if capture is not None else [])
    arguments += ["--vcd", str(vcd)] if vcd is not None else []
    arguments += runner_arguments(parameters or {})
    return subprocess.run(
        ["bash", str(ROOT / "rtl" / rtl_variant / "run.sh"), *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=600, check=False,
    )


def parse_report(stdout: str) -> dict:
    """Return the testbench report: both ``Frame`` lines, the mid-traffic reset, the DUT row and the PASS line."""
    def value(text: str):
        return int(text) if re.fullmatch(r"-?\d+", text) else text

    report = {}
    for line in stdout.splitlines():
        if line.startswith("Frame robustness="):
            fields = {key: value(text) for key, text in _FIELD.findall(line)}
            report["robustness" if fields["robustness"] else "continuous"] = fields
        elif line.startswith("Midtraffic reset "):
            report["midtraffic_reset"] = {key: value(text) for key, text in _FIELD.findall(line)}
        elif line.startswith("Block timing "):
            report["block_timing"] = {key: value(text) for key, text in _FIELD.findall(line)}
        elif line.startswith("DUT parameters "):
            report["dut_parameters"] = {key: value(text) for key, text in _FIELD.findall(line)}
        elif line.startswith("PASS: "):
            report["pass"] = line
    return report


def _simulator_version() -> str:
    result = subprocess.run(["iverilog", "-V"], capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).splitlines()[0].strip()


def _rtl_snapshot(rtl_variant: str) -> dict[str, str]:
    """Hash the shared RTL, the variant wrapper, the testbench and the runner as they were at run time."""
    paths = [*sorted((ROOT / "rtl" / "common").glob("*.sv")), ROOT / "rtl" / rtl_variant / f"{rtl_variant}_filter.sv",
             ROOT / "rtl" / "tb" / "rrc_stream_tb.sv", ROOT / "rtl" / "run_variant.sh"]
    return {str(path.relative_to(ROOT)): _sha256(path.read_bytes()) for path in paths}


def write_evidence(variant_id: str, evidence_dir: Path, build_dir: Path, vectors: Path = VECTORS) -> Path:
    """Run every frame of ``variant_id`` and write ``evidence_manifest.json`` plus one log per frame.

    A failing frame raises after its log is written. The evidence binds the
    ``.svh`` and payload hashes the runs consumed, the declared metadata and the
    measured latency, II, transport counts and robustness coverage. Each
    continuous run also captures the RTL outputs into ``<build_dir>/<frame>/``;
    their hash must equal the bound expected codes, independently of the
    testbench comparator. For a parameterized source the testbench must report
    the row of ``rtl_parameters`` and a time variant must measure ``II = 8/S``:
    T-S4P1 and T-S8P1 emit the same codes with the same latency, so the II is
    what binds a run to its row.
    """
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    rtl_variant = domain = provenance = ii = None
    for vector_set, vector_case in FRAMES:
        key = f"{vector_set}/{vector_case}"
        frame = load_matching(variant_id, vector_set, vector_case, vectors)
        manifest = frame["manifest"]
        rtl_variant, domain = manifest["rtl_variant"], manifest["model_domain"]
        parameters = manifest.get("rtl_parameters", {})
        provenance, ii = manifest["provenance"], expected_ii(manifest)
        timing = expected_block_timing(manifest)
        staged = stage(Path(build_dir) / f"{vector_set}-{vector_case}", variant_id, vector_set, vector_case, vectors)
        capture = staged / CAPTURE_FILE
        capture.unlink(missing_ok=True)
        vcd = staged / VCD_FILE if timing is not None else None
        if vcd is not None:
            vcd.unlink(missing_ok=True)
        result = run_matching(rtl_variant, staged, capture, parameters, vcd)
        # Icarus names the VCD it opens with an absolute path of this machine: keep it out of the log, whose
        # hash the evidence records, so the evidence does not depend on where it was generated.
        log = "".join(line + "\n" for line in (result.stdout + result.stderr).splitlines()
                      if not line.startswith("VCD info:"))
        log_name = f"{vector_set}-{vector_case}.log"
        (evidence_dir / log_name).write_text(log, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"{key}: vector matching failed, see {evidence_dir / log_name}")
        report = parse_report(result.stdout)
        continuous = report["continuous"]
        if continuous["measured_latency_cycles"] != manifest["latency_cycles"]:
            raise RuntimeError(f"{key}: measured latency differs from the manifest")
        if parameters and report.get("dut_parameters") != parameters:
            raise RuntimeError(f"{key}: the testbench elaborated {report.get('dut_parameters')}, not {parameters}")
        if ii is not None and continuous["measured_ii"] != ii:
            raise RuntimeError(f"{key}: measured II {continuous['measured_ii']} is not {ii}")
        block_timing = vcd_coverage = None
        if timing is not None:
            block_timing = report.get("block_timing")
            expected_fields = {"blocks": timing["blocks"], "block_ii_count": timing["block_ii_count"],
                               "block_ii_min": timing["block_ii"], "block_ii_max": timing["block_ii"],
                               "fill_latency_cycles": timing["fill_latency_cycles"],
                               "tail_latency_cycles": timing["tail_latency_cycles"],
                               "source_tail_latency_cycles": timing["source_tail_latency_cycles"]}
            measured = {name: (block_timing or {}).get(name) for name in expected_fields}
            if measured != expected_fields:
                raise RuntimeError(f"{key}: block timing {measured} differs from the expected {expected_fields}")
            vcd_coverage = summarize_vcd(vcd, timing["blocks"])
            if not vcd_coverage["covers_all_blocks"]:
                raise RuntimeError(f"{key}: the VCD does not cover all {timing['blocks']} blocks: {vcd_coverage}")
        captured_sha256 = _sha256(capture.read_bytes())
        # The capture holds every raw output beat. Only the records inside the valid window are expected
        # codes; any others are the declared block padding (the last frequency output, index 2055), which
        # is recorded but never compared.
        records = capture.read_text(encoding="ascii").split()
        if len(records) != manifest["raw_output_samples"]:
            raise RuntimeError(f"{key}: {len(records)} captured outputs, {manifest['raw_output_samples']} declared")
        first = manifest["valid_start"] - manifest["latency_samples"]
        window = records[first : first + manifest["valid_len"]]
        window_sha256 = _sha256(("\n".join(window) + "\n").encode("ascii"))
        if window_sha256 != manifest["hashes"]["expected_hex_sha256"]:
            raise RuntimeError(f"{key}: captured RTL outputs differ from the bound expected codes")
        padding = records[:first] + records[first + manifest["valid_len"]:]
        frames[key] = {
            "result": "PASS",
            "pass_line": report["pass"],
            "bound_sha256": {
                "vector_manifest_svh": _sha256(frame["svh"]),
                "input_hex": manifest["hashes"]["input_hex_sha256"],
                "expected_hex": manifest["hashes"]["expected_hex_sha256"],
            },
            "declared": {
                name: manifest[name]
                for name in ("DATA_WIDTH", "SPC", "latency_samples", "latency_cycles", "flush_samples",
                             "transport_padding_samples", "accepted_input_samples", "raw_output_samples",
                             "valid_start", "valid_len")
            },
            "continuous": continuous,
            "robustness": report["robustness"],
            "midtraffic_reset": report["midtraffic_reset"],
            **({"dut_parameters": report["dut_parameters"]} if parameters else {}),
            **({"block_timing": block_timing, "vcd": vcd_coverage} if timing is not None else {}),
            "captured_output_sha256": captured_sha256,
            "captured_valid_window_sha256": window_sha256,
            "block_padding_records": padding,
            "log_file": log_name,
            "log_sha256": _sha256(log.encode("utf-8")),
        }
    runs = [frame["continuous"] for frame in frames.values()]
    evidence = {
        "evidence_for": f"rtl_matching vector matching of {variant_id}",
        "variant_id": variant_id,
        "rtl_variant": rtl_variant,
        "model_domain": domain,
        **({"rtl_parameters": parameters} if parameters else {}),
        **({"expected_ii": ii} if ii is not None else {}),
        **({"expected_block_timing": timing} if timing is not None else {}),
        # Revision of the generator that wrote the rtl_matching metadata these runs consumed.
        "vector_generator": provenance,
        "testbench": "rtl/tb/rrc_stream_tb.sv",
        "simulator": _simulator_version(),
        "method": {
            "continuous": "valid_i and ready_i held high; asserts latency_cycles from the first accepted input to "
            "the first valid output, measures II from accepted-input edges",
            "robustness": "seeded source bubbles and sink stalls plus a post-input tail stall; the testbench fails "
            "unless bubbles, sink stalls and DUT ready_o backpressure all occur",
            "midtraffic_reset": "asynchronous reset after an accepted prefix, then the robust run restarts at record 0",
            "comparison": "exact stored codes at absolute index received*SPC + lane + latency_samples; "
            "a mismatch reports index, expected and captured code",
            "drain": "valid_i stops after the declared accepted count; outputs drain under ready_i=1 with a "
            "bounded timeout and a check for undeclared extra emissions",
            "capture": "the continuous run writes every captured output (+capture_file) in the .hex format; "
            "the SHA-256 of its valid-window records must equal expected_hex_sha256, independently of the "
            "testbench comparator. Records outside the window are declared block padding: recorded, not compared",
            **(
                {
                    "block_timing": "continuous run: the interval between the first accepted samples of consecutive "
                    "blocks is the block II (256 intervals for 257 blocks, the first 256 blocks); fill is the first "
                    "accepted input to the first valid output, tail the last accepted input to the last output beat (the block "
                    "padding) and source tail the last source sample to the last valid output",
                    "vcd": "+vcd_file dumps the ports and the engine control state over the continuous run; the "
                    "engine enters LOAD, RUN, EMIT and DRAIN once per block, so every block is covered only if each "
                    "count equals the block count. The dump stays in the build directory; the evidence keeps its "
                    "size and the hash of its value changes",
                }
                if timing is not None
                else {}
            ),
        },
        "summary": {
            "frames": len(frames),
            "passed": sum(frame["result"] == "PASS" for frame in frames.values()),
            "compared_codes": sum(run["compared"] for run in runs),
            "captured_equal_to_expected": sum(
                frame["captured_valid_window_sha256"] == frame["bound_sha256"]["expected_hex"]
                for frame in frames.values()
            ),
            "mismatches": 0,
            "measured_latency_cycles": sorted({run["measured_latency_cycles"] for run in runs}),
            "measured_ii": sorted({run["measured_ii"] for run in runs}),
            **(
                {
                    "measured_block_ii": sorted({frame["block_timing"]["block_ii_min"] for frame in frames.values()}),
                    "fill_latency_cycles": sorted({frame["block_timing"]["fill_latency_cycles"] for frame in frames.values()}),
                    "tail_latency_cycles": sorted({frame["block_timing"]["tail_latency_cycles"] for frame in frames.values()}),
                    "source_tail_latency_cycles": sorted(
                        {frame["block_timing"]["source_tail_latency_cycles"] for frame in frames.values()}),
                    "vcd_covers_all_blocks": all(frame["vcd"]["covers_all_blocks"] for frame in frames.values()),
                }
                if timing is not None
                else {}
            ),
        },
        "frames": frames,
        "rtl_snapshot_sha256": _rtl_snapshot(rtl_variant),
    }
    path = evidence_dir / "evidence_manifest.json"
    path.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage (and optionally run) the rtl_matching vectors of a variant")
    parser.add_argument("--variant", required=True, help="variant_id, e.g. T-serial or T-S8P1")
    parser.add_argument("--output", type=Path, help="staging directory (default .build/rtl/matching/<variant>)")
    parser.add_argument("--evidence-dir", type=Path, help="also run every frame and write the matching evidence here")
    arguments = parser.parse_args()
    output = arguments.output or ROOT / ".build" / "rtl" / "matching" / arguments.variant
    try:
        if arguments.evidence_dir is not None:
            print(write_evidence(arguments.variant, arguments.evidence_dir, output))
        else:
            for vector_set, vector_case in FRAMES:
                print(stage(output / f"{vector_set}-{vector_case}", arguments.variant, vector_set, vector_case))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
