"""Stage the committed rtl_matching vectors of one variant for rrc_stream_tb (T31 #48, T40 #51).

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
writes the matching evidence. Standard library only, so the RTL CI job needs no
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
_RUNNER_FLAGS = {"SYSTOLIC_PES": "--systolic-pes", "PIPELINE_DEPTH": "--pipeline-depth"}
TIME_TAPS = 8


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


def run_matching(rtl_variant: str, staged: Path, capture: Path | None = None,
                 parameters: dict[str, int] | None = None) -> subprocess.CompletedProcess:
    """Run the variant's runner on a staged frame (shared testbench, Icarus).

    With ``capture`` the testbench also writes every output of its continuous
    run there, one packed ``{Q,I}`` record per line, in the ``.hex`` format.
    ``parameters`` (the manifest's ``rtl_parameters``) selects the matrix row.
    """
    arguments = ["--vectors", str(staged)] + (["--capture", str(capture)] if capture is not None else [])
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
        staged = stage(Path(build_dir) / f"{vector_set}-{vector_case}", variant_id, vector_set, vector_case, vectors)
        capture = staged / CAPTURE_FILE
        capture.unlink(missing_ok=True)
        result = run_matching(rtl_variant, staged, capture, parameters)
        log = result.stdout + result.stderr
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
        captured_sha256 = _sha256(capture.read_bytes())
        if captured_sha256 != manifest["hashes"]["expected_hex_sha256"]:
            raise RuntimeError(f"{key}: captured RTL outputs differ from the bound expected codes")
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
            "captured_output_sha256": captured_sha256,
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
            "its SHA-256 must equal expected_hex_sha256, independently of the testbench comparator",
        },
        "summary": {
            "frames": len(frames),
            "passed": sum(frame["result"] == "PASS" for frame in frames.values()),
            "compared_codes": sum(run["compared"] for run in runs),
            "captured_equal_to_expected": sum(
                frame["captured_output_sha256"] == frame["bound_sha256"]["expected_hex"] for frame in frames.values()
            ),
            "mismatches": 0,
            "measured_latency_cycles": sorted({run["measured_latency_cycles"] for run in runs}),
            "measured_ii": sorted({run["measured_ii"] for run in runs}),
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
