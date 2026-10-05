"""Staged golden-vector generator (T13 F1 float references).

Only this generator may write to ``sim/vectors/``. Normative schema:
``docs/contracts/vector-manifest-schema.md``. T13 implements the
``float_reference`` stage; ``fxp_expected`` (T22, #46) and ``rtl_matching``
(T31 #48 / T33 #50) are reserved interfaces that refuse to guess their data.
"""

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np

from golden_freq import filter_frequency_domain
from golden_time import _filter_time_domain
from rrc_coefs import _ARTIFACT_PATH, load_rrc8_coefficients
from stimulus import CORNER_CASES, generate_canonical_samples, generate_corner_samples


_SIM_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_DIR = _SIM_DIR.parent / "vectors"
_RTOL = 1e-10
_ATOL = 1e-12
_HASH_SERIALIZATION = {
    "algorithm": "SHA-256",
    "array_order": "C",
    "byte_order": "little-endian",
    "samples_dtype": "<c16",
    "coefficients_dtype": "<f8",
}
_SOURCE_FILES = ("gen_vectors.py", "stimulus.py", "rrc_coefs.py", "golden_time.py", "golden_freq.py")

STAGES = ("float_reference", "fxp_expected", "rtl_matching")
DOMAINS = ("time", "frequency")
_DOMAIN_FILE_TAG = {"time": "time", "frequency": "freq"}
INPUT_FILE = "input_samples.c16.bin"
REFERENCE_FILE = "reference_{tag}.c16.bin"
MANIFEST_FILE = "manifest_{tag}.json"

# Schema section 1 (qpsk-stimulus-15.md). Contract constants of qpsk-stim-15-v1;
# vector_set/vector_case say which frame content a manifest describes.
_SYMBOL_MAP = {0: 1 + 1j, 1: 1 - 1j, 2: -1 + 1j, 3: -1 - 1j}
_STIMULUS_CONSTANTS = {
    "stimulus_version": "qpsk-stim-15-v1",
    "symbol_count": 1024,
    "edge_pattern_symbols": 40,
    "random_seed": 2026,
    "prng": "numpy.random.default_rng (PCG64)",
    "symbol_map": "0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j",
    "symbol_map_coding": "gray",
    "symbol_energy": 2,
    "samples_per_symbol": 2,
    "upsampling": "zero_insertion",
    "input_samples": 2048,
    "output_samples": 2055,
    "valid_start": 0,
    "valid_len": 2055,
    "symbol_center_offset_samples": 3.5,
}
_VECTOR_SETS = {"canonical": ("none",), "sys_corners": CORNER_CASES}
STIMULUS_FIELDS = ("artifact_stage", "model_domain", *_STIMULUS_CONSTANTS, "vector_set", "vector_case")
FXP_FIELDS = (
    "W_common", "F_data", "F_coeff", "rounding_mode", "overflow_mode", "W_product", "W_acc_time",
    "fft_mode", "fft_stage_widths", "W_acc_freq", "ifft_scale",
)
RTL_FIELDS = (
    "DATA_WIDTH", "SPC", "FFT_LEN", "HOP", "DISCARD_PREFIX", "EMIT_START", "EMIT_LEN",
    "latency_samples", "latency_cycles", "block_cadence", "fft_pipeline_cycles",
)
RTL_MATCHING_FIELDS = (
    "variant_id", "flush_samples", "transport_padding_samples", "accepted_input_samples", "raw_output_samples",
)
PACKING_FIELDS = ("component_sign_extension", "hashes")
LEGACY_ALIASES = (
    "input_scale_16bit", "coefficient_scale_16bit", "output_scale_16bit", "evidence_interpolation",
    "latency_time", "latency_freq", "valid_count", "S",
)
_REQUIRED_FIELDS = {
    "float_reference": (*STIMULUS_FIELDS, "hashes"),
    "fxp_expected": (*STIMULUS_FIELDS, *FXP_FIELDS, *PACKING_FIELDS),
    "rtl_matching": (*STIMULUS_FIELDS, *FXP_FIELDS, *RTL_FIELDS, *RTL_MATCHING_FIELDS, *PACKING_FIELDS),
}
_FORBIDDEN_FIELDS = {
    "float_reference": (*FXP_FIELDS, *RTL_FIELDS, *RTL_MATCHING_FIELDS, "component_sign_extension", *LEGACY_ALIASES),
    "fxp_expected": (*RTL_FIELDS, *RTL_MATCHING_FIELDS, *LEGACY_ALIASES),
    "rtl_matching": LEGACY_ALIASES,
}
_RTL_CONSTANTS = {"FFT_LEN": 16, "HOP": 8, "DISCARD_PREFIX": 8, "EMIT_START": 8, "EMIT_LEN": 8, "block_cadence": 8}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sample_bytes(values: np.ndarray) -> bytes:
    """Serialize complex samples as C-order little-endian complex128."""
    return np.asarray(values, dtype=_HASH_SERIALIZATION["samples_dtype"]).tobytes(order="C")


def read_samples(path: Path) -> np.ndarray:
    """Read a ``.c16.bin`` float payload written by this generator."""
    return np.frombuffer(path.read_bytes(), dtype=_HASH_SERIALIZATION["samples_dtype"]).astype(np.complex128)


def _write_with_sidecar(path: Path, data: bytes) -> str:
    """Write ``data`` and its ``sha256sum``-format sidecar; return the digest."""
    path.write_bytes(data)
    digest = _sha256_bytes(data)
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def frame_samples(vector_set: str, vector_case: str) -> np.ndarray:
    """Return the 2048 input samples of one declared frame."""
    if vector_set not in _VECTOR_SETS or vector_case not in _VECTOR_SETS[vector_set]:
        raise ValueError(f"frame: unknown vector_set/vector_case {vector_set!r}/{vector_case!r}")
    if vector_set == "canonical":
        return generate_canonical_samples()
    return generate_corner_samples(vector_case)


def iter_frames() -> list[tuple[str, str]]:
    """Return every declared (vector_set, vector_case) pair in generation order."""
    return [(vector_set, case) for vector_set, cases in _VECTOR_SETS.items() for case in cases]


def filter_reference(samples: np.ndarray, coefficients: np.ndarray, domain: str) -> np.ndarray:
    """Return the full causal float64 reference of ``samples`` in one domain."""
    if domain == "time":
        return _filter_time_domain(samples, coefficients)
    if domain == "frequency":
        return filter_frequency_domain(samples, coefficients)
    raise ValueError(f"domain: expected one of {DOMAINS}, got {domain!r}")


def _symbol_energy_from_map() -> float:
    corners = np.array(list(_SYMBOL_MAP.values()))
    return float(np.mean(corners.real**2 + corners.imag**2))


def _symbol_map_is_gray() -> bool:
    """Check that constellation neighbours (differ in I or Q only) differ in one bit."""
    for a, sa in _SYMBOL_MAP.items():
        for b, sb in _SYMBOL_MAP.items():
            neighbours = (sa.real == sb.real) != (sa.imag == sb.imag)
            if neighbours and (a ^ b).bit_count() != 1:
                return False
    return True


def _symbol_map_text() -> str:
    def corner(value: complex) -> str:
        return f"{int(value.real):+d}{'+' if value.imag > 0 else '-'}j"

    return ", ".join(f"{index}={corner(value)}" for index, value in _SYMBOL_MAP.items())


def _assert_stimulus_consistency() -> None:
    if _symbol_map_text() != _STIMULUS_CONSTANTS["symbol_map"]:
        raise AssertionError("symbol_map text does not match the executable mapping")
    if not _symbol_map_is_gray():
        raise AssertionError("symbol_map_coding: gray is inconsistent with symbol_map")
    if _symbol_energy_from_map() != _STIMULUS_CONSTANTS["symbol_energy"]:
        raise AssertionError("symbol_energy does not match symbol_map")


def _assert_frame(samples: np.ndarray) -> None:
    symbols = samples[::2]
    if samples.shape != (_STIMULUS_CONSTANTS["input_samples"],):
        raise AssertionError("input_samples: frame is not 2048 samples")
    if np.any(samples[1::2] != 0):
        raise AssertionError("upsampling: odd samples must be zero")
    if not np.all(np.isin(symbols, list(_SYMBOL_MAP.values()))):
        raise AssertionError("symbols: every symbol must be a QPSK corner")


def validate_manifest(manifest: dict) -> None:
    """Raise ``ValueError`` if ``manifest`` violates its declared stage contract."""
    stage = manifest.get("artifact_stage")
    if stage not in STAGES:
        raise ValueError(f"artifact_stage: expected one of {STAGES}, got {stage!r}")
    if manifest.get("model_domain") not in DOMAINS:
        raise ValueError(f"model_domain: expected one of {DOMAINS}")

    missing = [field for field in _REQUIRED_FIELDS[stage] if field not in manifest]
    if missing:
        raise ValueError(f"{stage}: missing required fields {missing}")
    forbidden = [field for field in _FORBIDDEN_FIELDS[stage] if field in manifest]
    if forbidden:
        raise ValueError(f"{stage}: fields not allowed at this stage {forbidden}")

    for field, expected in _STIMULUS_CONSTANTS.items():
        if manifest[field] != expected:
            raise ValueError(f"{field}: expected {expected!r}, got {manifest[field]!r}")
    if manifest["vector_case"] not in _VECTOR_SETS.get(manifest["vector_set"], ()):
        raise ValueError("vector_set/vector_case: unknown frame")

    if stage in ("fxp_expected", "rtl_matching"):
        if manifest["W_common"] != 16 or manifest["F_data"] != 14 or manifest["F_coeff"] != 14:
            raise ValueError("production numeric invariant: W_common=16, F_data=F_coeff=14 (Q2.14)")
    if stage == "rtl_matching":
        if manifest["DATA_WIDTH"] != manifest["W_common"]:
            raise ValueError("DATA_WIDTH: must equal W_common")
        for field, expected in _RTL_CONSTANTS.items():
            if manifest[field] != expected:
                raise ValueError(f"{field}: expected {expected}")


def _source_hashes() -> dict[str, str]:
    return {name: _sha256_bytes((_SIM_DIR / name).read_bytes()) for name in _SOURCE_FILES}


def generate_float_reference(output_dir: Path) -> list[Path]:
    """Write F1 float references for every frame; return the manifest paths."""
    _assert_stimulus_consistency()
    coefficients = load_rrc8_coefficients()
    upstream = {
        "rrc8_manifest_sha256": _sha256_bytes(_ARTIFACT_PATH.read_bytes()),
        "coefficients_sha256": _sha256_bytes(
            np.asarray(coefficients, dtype=_HASH_SERIALIZATION["coefficients_dtype"]).tobytes(order="C")
        ),
    }
    provenance = {
        "generator": "sim/python/gen_vectors.py",
        "coefficient_artifact": "rrc8-v1",
        "source_sha256": _source_hashes(),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }

    manifests = []
    for vector_set, vector_case in iter_frames():
        frame_dir = output_dir / "float_reference" / vector_set / vector_case
        frame_dir.mkdir(parents=True, exist_ok=True)
        samples = frame_samples(vector_set, vector_case)
        _assert_frame(samples)
        input_sha256 = _write_with_sidecar(frame_dir / INPUT_FILE, _sample_bytes(samples))

        references = {domain: filter_reference(samples, coefficients, domain) for domain in DOMAINS}
        if not np.allclose(references["time"], references["frequency"], rtol=_RTOL, atol=_ATOL):
            raise AssertionError(f"{vector_set}/{vector_case}: time/frequency references disagree")
        max_abs_error = float(np.max(np.abs(references["time"] - references["frequency"])))

        for domain, reference in references.items():
            tag = _DOMAIN_FILE_TAG[domain]
            reference_file = REFERENCE_FILE.format(tag=tag)
            manifest = {
                "artifact_stage": "float_reference",
                "model_domain": domain,
                **_STIMULUS_CONSTANTS,
                "vector_set": vector_set,
                "vector_case": vector_case,
                "payload": {
                    "input_file": INPUT_FILE,
                    "reference_file": reference_file,
                    "encoding": "raw C-order little-endian complex128 (<c16), no header",
                    "input_count": samples.size,
                    "reference_count": reference.size,
                },
                "float_agreement": {
                    "compared_with": "frequency" if domain == "time" else "time",
                    "rtol": _RTOL,
                    "atol": _ATOL,
                    "max_abs_error": max_abs_error,
                },
                "hash_serialization": _HASH_SERIALIZATION,
                "hashes": {
                    **upstream,
                    "input_samples_sha256": input_sha256,
                    "reference_sha256": _write_with_sidecar(frame_dir / reference_file, _sample_bytes(reference)),
                },
                "provenance": provenance,
            }
            if manifest["payload"]["reference_count"] != manifest["output_samples"]:
                raise AssertionError("output_samples: reference is not 2055 samples")
            validate_manifest(manifest)
            manifest_path = frame_dir / MANIFEST_FILE.format(tag=tag)
            text = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n"
            _write_with_sidecar(manifest_path, text.encode("utf-8"))
            manifests.append(manifest_path)
    return manifests


def pack_qi_records(i_codes: np.ndarray, q_codes: np.ndarray, width: int = 16) -> list[str]:
    """Pack signed integer I/Q codes into 32-bit ``{Q[15:0], I[15:0]}`` hex records.

    Only integer codes are accepted: float references are never cast into
    packed expected-output files. ``width < 16`` components are sign-extended
    into the 16-bit fields; ``width > 16`` needs a new record format.
    """
    i_values = np.asarray(i_codes)
    q_values = np.asarray(q_codes)
    if not (np.issubdtype(i_values.dtype, np.integer) and np.issubdtype(q_values.dtype, np.integer)):
        raise TypeError("codes: expected integer arrays, float payloads are never packed")
    if i_values.shape != q_values.shape or i_values.ndim != 1:
        raise ValueError("codes: expected two one-dimensional arrays of equal length")
    if not 1 <= width <= 16:
        raise ValueError("width: records hold at most 16 bits per component")
    low, high = -(1 << (width - 1)), (1 << (width - 1)) - 1
    for name, values in (("I", i_values), ("Q", q_values)):
        if values.size and (values.min() < low or values.max() > high):
            raise ValueError(f"{name}: code outside the signed {width}-bit range")
    i_fields = i_values.astype(np.int64) & 0xFFFF
    q_fields = q_values.astype(np.int64) & 0xFFFF
    return [f"{(int(q) << 16) | int(i):08x}" for i, q in zip(i_fields, q_fields, strict=True)]


def export_fxp_expected(output_dir: Path) -> list[Path]:
    """Write F2 ``fxp_expected`` sets (owned by T22, #46).

    Must regenerate Q2.14 input and per-domain expected codes from the accepted
    FXP models (never from a cast of the float references), pack them with
    ``pack_qi_records``, and declare sections 1, 2 and 4 of the schema, binding
    the F1 manifest hashes. No RTL latency or transport counts.
    """
    raise NotImplementedError("fxp_expected export is owned by T22 (#46) after FXP acceptance")


def export_rtl_matching(output_dir: Path, variant_id: str) -> list[Path]:
    """Write F3 ``rtl_matching`` metadata for one variant (T31 #48 / T33 #50).

    Must bind the F2 payload hashes and add measured latency, flush and
    transport counts plus the metadata-only ``vector_manifest.svh``.
    """
    raise NotImplementedError("rtl_matching export is owned by T31 (#48) / T33 (#50) after RTL measurement")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate staged golden vectors (T13: float_reference)")
    parser.add_argument("--stage", choices=STAGES, default="float_reference")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--plots-dir",
        type=Path,
        help="also write review-evidence plots of the float_reference vectors (not part of the vectors)",
    )
    args = parser.parse_args()
    if args.plots_dir is not None and args.stage != "float_reference":
        parser.error("--plots-dir is only available for --stage float_reference")
    if args.stage == "float_reference":
        for path in generate_float_reference(args.output_dir):
            print(path)
        if args.plots_dir is not None:
            from plot_vectors import generate_vector_plots

            print(generate_vector_plots(args.output_dir, args.plots_dir))
    elif args.stage == "fxp_expected":
        export_fxp_expected(args.output_dir)
    else:
        export_rtl_matching(args.output_dir, variant_id="")


if __name__ == "__main__":
    main()
