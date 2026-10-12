"""Staged golden-vector generator (T13 F1 float references, T22 F2 expected codes).

Only this generator may write to ``sim/vectors/``. Normative schema:
``docs/contracts/vector-manifest-schema.md``. T13 implements the
``float_reference`` stage and T22 (#46) the ``fxp_expected`` stage;
``rtl_matching`` (T31 #48 / T33 #50) is a reserved interface that refuses to
guess its data.
"""

import argparse
import hashlib
import json
import platform
from pathlib import Path

import fxpmath
import numpy as np

import fxp
from golden_freq import filter_frequency_domain
from golden_time import _filter_time_domain
from rrc_coefs import _ARTIFACT_PATH, load_rrc8_coefficients
from sqnr import SQNR_CROSS_MIN_DB, SQNR_MIN_DB, split_half_is_stable
from stimulus import CORNER_CASES, generate_canonical_samples, generate_corner_samples


_SIM_DIR = Path(__file__).resolve().parent
_REPO_DIR = _SIM_DIR.parents[1]
_DEFAULT_OUTPUT_DIR = _SIM_DIR.parent / "vectors"
_T21_EVIDENCE_PATH = _SIM_DIR / "artifacts" / "t21-width-sweep" / "evidence_manifest.json"
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
_FXP_SOURCE_FILES = ("gen_vectors.py", "fxp.py", "sqnr.py", "rrc_coefs.py", "stimulus.py")
_FXP_HASH_SERIALIZATION = {
    **_HASH_SERIALIZATION,
    "codes_dtype": "<i8",
    "codes_layout": "shape (samples, 2), columns [I, Q]",
}

STAGES = ("float_reference", "fxp_expected", "rtl_matching")
DOMAINS = ("time", "frequency")
_DOMAIN_FILE_TAG = {"time": "time", "frequency": "freq"}
INPUT_FILE = "input_samples.c16.bin"
REFERENCE_FILE = "reference_{tag}.c16.bin"
MANIFEST_FILE = "manifest_{tag}.json"
# F2 layout mirrors F1: fxp_expected/<vector_set>/<vector_case>/ holds the
# shared input codes and one expected file and manifest per domain.
INPUT_HEX_FILE = "input.hex"
EXPECTED_HEX_FILE = "expected_{tag}.hex"
COEFFICIENT_FILE = "rrc8_q2.14_coefficients.json"
_HEX_ENCODING = "one 32-bit {Q[15:0], I[15:0]} record per line, 8 lowercase hex digits, read with $readmemh"
_ACCEPTANCE_FRAME = ("canonical", "none")

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
# The cross-domain SQNR compares two domains, so per-domain vector manifests
# never carry it (fxp-policy-16 cross-domain amendment).
CROSS_DOMAIN_FIELDS = ("sqnr_cross_db",)
_FORBIDDEN_FIELDS = {
    "float_reference": (*FXP_FIELDS, *RTL_FIELDS, *RTL_MATCHING_FIELDS, "component_sign_extension", *LEGACY_ALIASES),
    "fxp_expected": (*RTL_FIELDS, *RTL_MATCHING_FIELDS, *LEGACY_ALIASES, *CROSS_DOMAIN_FIELDS),
    "rtl_matching": (*LEGACY_ALIASES, *CROSS_DOMAIN_FIELDS),
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
        for field, expected in fxp.PRODUCTION_POLICY.manifest_fields().items():
            if manifest[field] != expected:
                raise ValueError(f"{field}: expected the frozen production value {expected!r}")
        if manifest["component_sign_extension"] != "sign_extend_to_16":
            raise ValueError("component_sign_extension: expected 'sign_extend_to_16'")
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


def _codes_sha256(i_codes: np.ndarray, q_codes: np.ndarray) -> str:
    """Hash I/Q codes as ``<i8`` with columns ``[I, Q]``, the T20/T21 serialization."""
    codes = np.stack((np.asarray(i_codes), np.asarray(q_codes)), axis=1)
    return _sha256_bytes(codes.astype(_FXP_HASH_SERIALIZATION["codes_dtype"]).tobytes(order="C"))


def _hex_bytes(records: list[str]) -> bytes:
    return ("\n".join(records) + "\n").encode("ascii")


def _repo_relative(path: Path) -> str:
    resolved = Path(path).resolve()
    return str(resolved.relative_to(_REPO_DIR)) if resolved.is_relative_to(_REPO_DIR) else resolved.name


def _load_t21_acceptance(path: Path) -> tuple[dict, str]:
    """Read the T21 sweep evidence; refuse unless it accepts production Q2.14."""
    data = Path(path).read_bytes()
    evidence = json.loads(data)
    acceptance = evidence.get("production_acceptance") or {}
    if acceptance.get("passed") is not True or acceptance.get("W_common") != fxp.PRODUCTION_WIDTH:
        raise ValueError(f"{path}: production Q2.14 is not numerically accepted by T21")
    return evidence, _sha256_bytes(data)


def _accepted_frame(evidence: dict, key: str) -> dict:
    """Return the T21 production measurement of one frame."""
    try:
        return evidence["frames"][str(fxp.PRODUCTION_WIDTH)][key]
    except KeyError as exc:
        raise ValueError(f"{key}: T21 evidence has no production measurement for this frame") from exc


def _frame_gates(frame: dict, run: dict, acceptance_frame: bool) -> dict[str, dict[str, bool]]:
    """Return the fxp-policy-16 acceptance gates that apply to one frame, per domain.

    Every frame is an internal-overflow gate. SQNR, the D6 split-half check and
    output saturation are gated on the canonical frame and diagnostics elsewhere.
    """
    gates = {}
    for domain in DOMAINS:
        entry = run["measurement"][domain]
        checks = {"zero_internal_overflow": entry["internal_overflow_count"] == 0}
        if acceptance_frame:
            decoded = run["results"][domain].decoded()
            checks["sqnr_at_least_40_db"] = entry["sqnr_db"] is None or entry["sqnr_db"] >= SQNR_MIN_DB
            checks["split_half_stable"] = split_half_is_stable(frame["reference"][domain], decoded)
            checks["zero_output_saturation"] = entry["output_saturation_count"] == 0
        gates[domain] = checks
    return gates


def _coefficient_table(policy: fxp.FxpPolicy, acceptance: dict, hashes: dict, sources: dict) -> dict:
    """Return the production coefficient table: the float golden beside its stored codes.

    ``fxp.quantize_coefficients`` raises on a range violation, so no coefficient
    is ever saturated silently into the table. The table carries no tool
    versions, so its hash does not depend on the host that generated it.
    """
    coefficients = load_rrc8_coefficients()
    codes = fxp.quantize_coefficients(policy, coefficients)
    if list(codes) != list(fxp.quantize_coefficients(policy)):
        raise AssertionError("coefficient codes differ from the codes of the FXP model")
    code_bytes = np.asarray(codes, dtype=_FXP_HASH_SERIALIZATION["codes_dtype"]).tobytes(order="C")
    return {
        "artifact": "rrc8-v1-q2.14",
        "artifact_stage": "fxp_expected",
        "status": "frozen production coefficients, exported after the T21 numerical acceptance",
        "coefficient_artifact": "rrc8-v1",
        "num_coefficients": fxp.FILTER_LENGTH,
        "ordering": "ascending_time",
        "delay_samples": 3.5,
        "format": f"Q2.{policy.fraction_bits}",
        "W_common": policy.width,
        "F_coeff": policy.fraction_bits,
        "rounding_mode": fxp.ROUNDING_MODE,
        "quantization": (
            f"code = RNE(h * 2^{policy.fraction_bits}); a code outside the signed {policy.width}-bit range "
            "is an error, never a saturation"
        ),
        "range_violation_count": 0,
        "coefficients_float64": coefficients.tolist(),
        "coefficient_codes": [int(code) for code in codes],
        "acceptance": acceptance,
        "hash_serialization": _FXP_HASH_SERIALIZATION,
        "hashes": {
            **hashes,
            "coefficients_sha256": _sha256_bytes(
                np.asarray(coefficients, dtype=_HASH_SERIALIZATION["coefficients_dtype"]).tobytes(order="C")
            ),
            "coefficient_codes_sha256": _sha256_bytes(code_bytes),
        },
        "provenance": {"generator": "sim/python/gen_vectors.py", "source_sha256": sources},
    }


def export_fxp_expected(
    output_dir: Path,
    vectors_dir: Path | None = None,
    acceptance_path: Path = _T21_EVIDENCE_PATH,
) -> list[Path]:
    """Write the F2 ``fxp_expected`` sets (T22, #46); return the coefficient table and manifest paths.

    The F1 frames are read from ``vectors_dir`` (default ``output_dir``) after
    their hash check, and the production integer models of ``fxp.py`` run on
    them. Expected codes are never a cast of the float references. The export
    refuses unless T21 accepts production Q2.14 on these same F1 frames, every
    frame reproduces the output codes T21 accepted, and every acceptance gate
    passes. Everything is built and validated before the first file is written.
    No RTL latency, transport count or ``vector_manifest.svh`` is emitted.
    """
    output_dir = Path(output_dir)
    vectors_dir = output_dir if vectors_dir is None else Path(vectors_dir)
    policy = fxp.PRODUCTION_POLICY
    _assert_stimulus_consistency()
    evidence, t21_sha256 = _load_t21_acceptance(acceptance_path)
    sources = {name: _sha256_bytes((_SIM_DIR / name).read_bytes()) for name in _FXP_SOURCE_FILES}
    upstream = {
        "rrc8_manifest_sha256": _sha256_bytes(_ARTIFACT_PATH.read_bytes()),
        "t21_evidence_sha256": t21_sha256,
    }
    acceptance = {
        "record": "fxp-policy-16.md T21 acceptance record (#45)",
        "evidence_file": _repo_relative(acceptance_path),
        "production_acceptance_passed": True,
    }
    provenance = {
        "generator": "sim/python/gen_vectors.py",
        "model": "sim/python/fxp.py production-A integer models (fxp-policy-16 T20 freeze)",
        "coefficient_artifact": "rrc8-v1",
        "source_sha256": sources,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "fxpmath": fxpmath.__version__},
    }

    stage_dir = output_dir / "fxp_expected"
    coefficient_path = stage_dir / COEFFICIENT_FILE
    table = _coefficient_table(policy, acceptance, upstream, sources)
    table_bytes = (json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    files = [(coefficient_path, table_bytes)]
    manifest_paths = []

    for vector_set, vector_case in iter_frames():
        key = f"{vector_set}/{vector_case}"
        frame = fxp.load_f1_frame(vectors_dir, vector_set, vector_case)
        if frame["manifest_sha256"] != evidence["f1_manifest_sha256"].get(key):
            raise ValueError(f"{key}: F1 manifests differ from the frames T21 accepted")
        _assert_frame(frame["samples"])
        run = fxp.measure_frame(frame["samples"], frame["reference"], policy)
        accepted = _accepted_frame(evidence, key)
        for domain in DOMAINS:
            if run["measurement"][domain]["output_codes_sha256"] != accepted[domain]["output_codes_sha256"]:
                raise ValueError(f"{key}: {domain} output codes differ from the codes T21 accepted")
        acceptance_frame = (vector_set, vector_case) == _ACCEPTANCE_FRAME
        gates = _frame_gates(frame, run, acceptance_frame)
        failed = [f"{domain}.{name}" for domain, checks in gates.items() for name, ok in checks.items() if not ok]
        cross = run["measurement"]["sqnr_cross_db"]
        if acceptance_frame and cross is not None and cross < SQNR_CROSS_MIN_DB:
            failed.append("sqnr_cross")
        if failed:
            raise ValueError(f"{key}: FXP acceptance gates failed {failed}")

        frame_dir = stage_dir / vector_set / vector_case
        input_i, input_q = (codes.astype(np.int64) for codes in fxp.quantize_samples(frame["samples"], policy))
        input_bytes = _hex_bytes(pack_qi_records(input_i, input_q))
        files.append((frame_dir / INPUT_HEX_FILE, input_bytes))

        for domain in DOMAINS:
            tag = _DOMAIN_FILE_TAG[domain]
            result = run["results"][domain]
            entry = run["measurement"][domain]
            expected_file = EXPECTED_HEX_FILE.format(tag=tag)
            expected_bytes = _hex_bytes(pack_qi_records(result.i_codes, result.q_codes))
            fxp_evidence = {
                "model": "fxp.py production-A integer model, run by this export",
                "sqnr_reference": "this domain's F1 float reference over the full causal window",
                "frame_role": "acceptance" if acceptance_frame else "diagnostic",
                "sqnr_db": entry["sqnr_db"],
                "split_half_sqnr_db": entry["split_half_sqnr_db"],
                "internal_overflow_count": entry["internal_overflow_count"],
                "output_saturation_count": entry["output_saturation_count"],
                "gates": gates[domain],
            }
            if not acceptance_frame:
                fxp_evidence["reported_without_threshold"] = ["sqnr_db", "split_half_sqnr_db", "output_saturation_count"]
            manifest = {
                "artifact_stage": "fxp_expected",
                "model_domain": domain,
                **_STIMULUS_CONSTANTS,
                "vector_set": vector_set,
                "vector_case": vector_case,
                **policy.manifest_fields(),
                "component_sign_extension": "sign_extend_to_16",
                "payload": {
                    "input_file": INPUT_HEX_FILE,
                    "expected_file": expected_file,
                    "coefficient_file": f"../../{COEFFICIENT_FILE}",
                    "encoding": _HEX_ENCODING,
                    "input_count": int(input_i.size),
                    "expected_count": int(result.i_codes.size),
                },
                "fxp_evidence": fxp_evidence,
                "acceptance": {
                    **acceptance,
                    "output_codes_match_t21": True,
                    "cross_domain": "gated on the canonical frame by the T21 production acceptance; "
                    "per-domain manifests do not carry sqnr_cross_db",
                },
                "hash_serialization": _FXP_HASH_SERIALIZATION,
                "hashes": {
                    **upstream,
                    "f1_manifest_sha256": frame["manifest_sha256"][domain],
                    "coefficient_table_sha256": _sha256_bytes(table_bytes),
                    "input_hex_sha256": _sha256_bytes(input_bytes),
                    "expected_hex_sha256": _sha256_bytes(expected_bytes),
                    "input_codes_sha256": _codes_sha256(input_i, input_q),
                    "output_codes_sha256": entry["output_codes_sha256"],
                },
                "provenance": provenance,
            }
            if manifest["payload"]["input_count"] != manifest["input_samples"]:
                raise AssertionError("input_samples: input codes are not 2048 samples")
            if manifest["payload"]["expected_count"] != manifest["output_samples"]:
                raise AssertionError("output_samples: expected codes are not 2055 samples")
            validate_manifest(manifest)
            manifest_path = frame_dir / MANIFEST_FILE.format(tag=tag)
            text = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n"
            files.append((frame_dir / expected_file, expected_bytes))
            files.append((manifest_path, text.encode("utf-8")))
            manifest_paths.append(manifest_path)

    for path, data in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_with_sidecar(path, data)
    return [coefficient_path, *manifest_paths]


def export_rtl_matching(output_dir: Path, variant_id: str) -> list[Path]:
    """Write F3 ``rtl_matching`` metadata for one variant (T31 #48 / T33 #50).

    Must bind the F2 payload hashes and add measured latency, flush and
    transport counts plus the metadata-only ``vector_manifest.svh``.
    """
    raise NotImplementedError("rtl_matching export is owned by T31 (#48) / T33 (#50) after RTL measurement")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate staged golden vectors (T13: float_reference, T22: fxp_expected)"
    )
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
        for path in export_fxp_expected(args.output_dir):
            print(path)
    else:
        export_rtl_matching(args.output_dir, variant_id="")


if __name__ == "__main__":
    main()
