"""Contract checks for the staged vector generator (T13 F1 float references)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import gen_vectors
from gen_vectors import (
    FXP_FIELDS,
    LEGACY_ALIASES,
    RTL_FIELDS,
    export_fxp_expected,
    export_rtl_matching,
    frame_samples,
    generate_float_reference,
    iter_frames,
    pack_qi_records,
    read_samples,
    validate_manifest,
)
from golden_freq import generate_frequency_golden
from golden_time import generate_time_golden


_COMMITTED_DIR = Path(__file__).resolve().parents[2] / "vectors"
_T11_CANONICAL_INPUT_SHA256 = "d805588396a3eefd3b2895601856f929a99bfeaa32dd1f05879b477dc774c132"
_EXPECTED_FRAMES = [
    ("canonical", "none"),
    ("sys_corners", "corner_repeat"),
    ("sys_corners", "max_alternation"),
    ("sys_corners", "single_symbol_perturbation"),
]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("vectors")
    manifests = generate_float_reference(output_dir)
    return output_dir, manifests


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_generator_declares_canonical_and_three_corner_frames():
    assert iter_frames() == _EXPECTED_FRAMES


def test_regeneration_is_byte_identical(generated, tmp_path):
    output_dir, _ = generated
    generate_float_reference(tmp_path)

    assert _tree_bytes(tmp_path) == _tree_bytes(output_dir)


def test_every_frame_has_two_domain_manifests_and_no_rtl_files(generated):
    output_dir, manifests = generated

    assert len(manifests) == 2 * len(_EXPECTED_FRAMES)
    for vector_set, vector_case in _EXPECTED_FRAMES:
        frame_dir = output_dir / "float_reference" / vector_set / vector_case
        assert sorted(path.name for path in frame_dir.iterdir() if not path.name.endswith(".sha256")) == [
            "input_samples.c16.bin",
            "manifest_freq.json",
            "manifest_time.json",
            "reference_freq.c16.bin",
            "reference_time.c16.bin",
        ]
    assert not list(output_dir.rglob("*.hex"))
    assert not list(output_dir.rglob("*.svh"))


def test_manifests_declare_f1_stage_and_frame_window(generated):
    _, manifests = generated

    for path in manifests:
        manifest = _load(path)
        validate_manifest(manifest)
        assert manifest["artifact_stage"] == "float_reference"
        assert manifest["model_domain"] == ("time" if path.name == "manifest_time.json" else "frequency")
        assert (manifest["vector_set"], manifest["vector_case"]) in _EXPECTED_FRAMES
        assert manifest["input_samples"] == 2048
        assert manifest["output_samples"] == 2055
        assert (manifest["valid_start"], manifest["valid_len"]) == (0, 2055)
        assert not set(manifest) & {*FXP_FIELDS, *RTL_FIELDS, *LEGACY_ALIASES, "component_sign_extension"}


def test_sidecars_and_manifest_hashes_bind_every_payload(generated):
    output_dir, manifests = generated

    for path in output_dir.rglob("*"):
        if path.is_file() and not path.name.endswith(".sha256"):
            digest, name = path.with_name(path.name + ".sha256").read_text(encoding="utf-8").split()
            assert name == path.name
            assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    for path in manifests:
        manifest = _load(path)
        payload = manifest["payload"]
        hashes = manifest["hashes"]
        assert hashes["input_samples_sha256"] == hashlib.sha256((path.parent / payload["input_file"]).read_bytes()).hexdigest()
        assert hashes["reference_sha256"] == hashlib.sha256((path.parent / payload["reference_file"]).read_bytes()).hexdigest()
        assert "vector_manifest_sha256" not in hashes


def test_canonical_input_hash_matches_time_golden_evidence(generated):
    output_dir, _ = generated
    manifest = _load(output_dir / "float_reference" / "canonical" / "none" / "manifest_time.json")

    assert manifest["hashes"]["input_samples_sha256"] == _T11_CANONICAL_INPUT_SHA256


def test_payloads_round_trip_and_match_both_goldens(generated):
    output_dir, _ = generated
    frame_dir = output_dir / "float_reference" / "canonical" / "none"

    np.testing.assert_array_equal(read_samples(frame_dir / "input_samples.c16.bin"), frame_samples("canonical", "none"))
    np.testing.assert_array_equal(read_samples(frame_dir / "reference_time.c16.bin"), generate_time_golden())
    np.testing.assert_array_equal(read_samples(frame_dir / "reference_freq.c16.bin"), generate_frequency_golden())


@pytest.mark.parametrize(("vector_set", "vector_case"), _EXPECTED_FRAMES)
def test_time_and_frequency_references_agree_on_every_frame(generated, vector_set, vector_case):
    output_dir, _ = generated
    frame_dir = output_dir / "float_reference" / vector_set / vector_case
    time_reference = read_samples(frame_dir / "reference_time.c16.bin")
    frequency_reference = read_samples(frame_dir / "reference_freq.c16.bin")

    assert time_reference.shape == frequency_reference.shape == (2055,)
    np.testing.assert_allclose(frequency_reference, time_reference, rtol=1e-10, atol=1e-12)


def test_committed_vectors_are_current(generated):
    """Committed F1 vectors must come from the current sources and agree with a fresh run."""
    output_dir, _ = generated
    committed_dir = _COMMITTED_DIR / "float_reference"
    fresh_files = {path.relative_to(output_dir) for path in (output_dir / "float_reference").rglob("*")}
    committed_files = {path.relative_to(_COMMITTED_DIR) for path in committed_dir.rglob("*")}
    assert committed_files == fresh_files

    for path in (output_dir / "float_reference").rglob("manifest_*.json"):
        relative = path.relative_to(output_dir)
        fresh = _load(path)
        committed = _load(_COMMITTED_DIR / relative)
        assert committed["provenance"]["source_sha256"] == fresh["provenance"]["source_sha256"]
        assert committed["hashes"]["input_samples_sha256"] == fresh["hashes"]["input_samples_sha256"]
        assert committed["hashes"]["rrc8_manifest_sha256"] == fresh["hashes"]["rrc8_manifest_sha256"]
        reference_file = relative.parent / fresh["payload"]["reference_file"]
        np.testing.assert_allclose(
            read_samples(_COMMITTED_DIR / reference_file),
            read_samples(output_dir / reference_file),
            rtol=1e-10,
            atol=1e-12,
        )


def _f1_manifest(generated) -> dict:
    output_dir, _ = generated
    return _load(output_dir / "float_reference" / "canonical" / "none" / "manifest_time.json")


@pytest.mark.parametrize(
    ("field", "value"),
    [("latency_samples", 0), ("latency_cycles", 8), ("W_common", 16), ("component_sign_extension", "sign_extend_to_16"), ("latency_time", 0)],
)
def test_f1_validator_rejects_invented_fxp_rtl_and_legacy_fields(generated, field, value):
    manifest = _f1_manifest(generated) | {field: value}

    with pytest.raises(ValueError, match="not allowed"):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [("input_samples", 2049), ("output_samples", 2048), ("valid_len", 2048), ("valid_start", 1), ("edge_pattern_symbols", 32)],
)
def test_validator_enforces_frame_window_invariants(generated, field, value):
    manifest = _f1_manifest(generated) | {field: value}

    with pytest.raises(ValueError, match=field):
        validate_manifest(manifest)


def test_validator_requires_stage_fields(generated):
    manifest = _f1_manifest(generated)
    del manifest["hashes"]

    with pytest.raises(ValueError, match="missing"):
        validate_manifest(manifest)
    with pytest.raises(ValueError, match="artifact_stage"):
        validate_manifest(_f1_manifest(generated) | {"artifact_stage": "final"})
    with pytest.raises(ValueError, match="missing"):
        validate_manifest(_f1_manifest(generated) | {"artifact_stage": "fxp_expected"})


def test_later_stage_exports_are_reserved_for_their_owners(tmp_path):
    with pytest.raises(NotImplementedError, match="T22"):
        export_fxp_expected(tmp_path)
    with pytest.raises(NotImplementedError, match="T31"):
        export_rtl_matching(tmp_path, variant_id="T-serial")
    assert not list(tmp_path.iterdir())


def test_symbol_map_metadata_is_consistent():
    assert gen_vectors._symbol_map_text() == "0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j"
    assert gen_vectors._symbol_map_is_gray()
    assert gen_vectors._symbol_energy_from_map() == 2


def test_pack_qi_records_places_q_high_and_i_low():
    records = pack_qi_records(np.array([16384, -16384, 0, -1]), np.array([-16384, 16384, 32767, -32768]))

    assert records == ["c0004000", "4000c000", "7fff0000", "8000ffff"]


def test_pack_qi_records_sign_extends_narrow_widths():
    assert pack_qi_records(np.array([-1, 3]), np.array([-4, 1]), width=3) == ["fffcffff", "00010003"]


@pytest.mark.parametrize(
    ("i_codes", "q_codes", "width", "error"),
    [
        (np.array([0.5]), np.array([0]), 16, TypeError),
        (np.array([32768]), np.array([0]), 16, ValueError),
        (np.array([0]), np.array([-5]), 3, ValueError),
        (np.array([0]), np.array([0]), 17, ValueError),
        (np.array([0, 1]), np.array([0]), 16, ValueError),
    ],
)
def test_pack_qi_records_rejects_floats_out_of_range_and_wide_records(i_codes, q_codes, width, error):
    with pytest.raises(error):
        pack_qi_records(i_codes, q_codes, width=width)
