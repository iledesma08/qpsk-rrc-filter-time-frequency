"""Contract checks for the staged vector generator (T13 F1 float references, T22 F2 expected codes)."""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import fxp
import gen_vectors
from gen_vectors import (
    FXP_FIELDS,
    LEGACY_ALIASES,
    RTL_FIELDS,
    RTL_MATCHING_FIELDS,
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
from rrc_coefs import load_rrc8_coefficients


_COMMITTED_DIR = Path(__file__).resolve().parents[2] / "vectors"
_T21_EVIDENCE = Path(gen_vectors.__file__).resolve().parent / "artifacts" / "t21-width-sweep" / "evidence_manifest.json"
_T11_CANONICAL_INPUT_SHA256 = "d805588396a3eefd3b2895601856f929a99bfeaa32dd1f05879b477dc774c132"
# Canonical production output codes accepted by T21 (fxp-policy-16 T21 acceptance record).
_T21_CANONICAL_CODES_SHA256 = {
    "time": "874198a244236c4c48cc9aa26103254576203904f2c202074217d210c6dd9750",
    "frequency": "202312fc748c3a77c27fa31f89f7f85d9d725c41a521afefcd0e994714e80752",
}
_PRODUCTION_COEFFICIENT_CODES = [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]
_FXP_FRAME_FILES = ["expected_freq.hex", "expected_time.hex", "input.hex", "manifest_freq.json", "manifest_time.json"]
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


def test_rtl_matching_export_is_reserved_for_its_owners(tmp_path):
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


def test_vector_plots_are_evidence_outside_the_vector_tree(generated, tmp_path):
    from plot_vectors import generate_vector_plots

    output_dir, _ = generated
    before = _tree_bytes(output_dir)
    manifest_path = generate_vector_plots(output_dir, tmp_path)
    manifest = _load(manifest_path)

    assert _tree_bytes(output_dir) == before
    assert manifest["plots"] == [
        "canonical_none.png",
        "sys_corners_corner_repeat.png",
        "sys_corners_max_alternation.png",
        "sys_corners_single_symbol_perturbation.png",
        "time_frequency_agreement.png",
    ]
    for name, digest in manifest["plot_sha256"].items():
        assert digest == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    for name, digest in manifest["vector_payload_sha256"].items():
        assert digest == hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
    assert len(manifest["vector_payload_sha256"]) == 3 * len(_EXPECTED_FRAMES)
    assert max(manifest["max_abs_time_frequency_error"].values()) < manifest["atol"]


def test_plots_dir_flag_is_float_reference_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("sys.argv", ["gen_vectors.py", "--stage", "fxp_expected", "--plots-dir", str(tmp_path)])

    with pytest.raises(SystemExit):
        gen_vectors.main()
    assert "--plots-dir" in capsys.readouterr().err


# T22 F2 fxp_expected export


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unpack_records(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Decode packed ``{Q[15:0], I[15:0]}`` hex records into signed 16-bit I and Q codes."""
    words = np.array([int(line, 16) for line in path.read_text(encoding="ascii").split()], dtype=np.int64)

    def signed(field: np.ndarray) -> np.ndarray:
        return np.where(field >= 1 << 15, field - (1 << 16), field)

    return signed(words & 0xFFFF), signed(words >> 16)


def _all_keys(value) -> set:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("fxp_vectors")
    paths = export_fxp_expected(output_dir, vectors_dir=_COMMITTED_DIR)
    return output_dir, paths


def _fxp_manifest(exported) -> dict:
    return _load(exported[1][1])


def test_fxp_export_writes_the_coefficient_table_and_every_frame_in_both_domains(exported):
    output_dir, paths = exported
    stage_dir = output_dir / "fxp_expected"

    assert [path.name for path in paths] == [gen_vectors.COEFFICIENT_FILE] + [
        "manifest_time.json",
        "manifest_freq.json",
    ] * len(_EXPECTED_FRAMES)
    assert sorted(path.name for path in output_dir.iterdir()) == ["fxp_expected"]
    assert sorted(
        path.name for path in stage_dir.iterdir() if path.is_file() and not path.name.endswith(".sha256")
    ) == [gen_vectors.COEFFICIENT_FILE]
    for vector_set, vector_case in _EXPECTED_FRAMES:
        frame_dir = stage_dir / vector_set / vector_case
        names = sorted(path.name for path in frame_dir.iterdir() if not path.name.endswith(".sha256"))
        assert names == _FXP_FRAME_FILES
        assert len((frame_dir / "input.hex").read_text(encoding="ascii").split()) == 2048
        for tag in ("time", "freq"):
            assert len((frame_dir / f"expected_{tag}.hex").read_text(encoding="ascii").split()) == 2055
    assert not list(output_dir.rglob("*.svh"))


def test_fxp_manifests_declare_the_f2_stage_and_the_frozen_policy_only(exported):
    _, paths = exported

    for path in paths[1:]:
        manifest = _load(path)
        validate_manifest(manifest)
        assert manifest["artifact_stage"] == "fxp_expected"
        assert manifest["model_domain"] == ("time" if path.name == "manifest_time.json" else "frequency")
        assert {field: manifest[field] for field in FXP_FIELDS} == fxp.PRODUCTION_POLICY.manifest_fields()
        assert manifest["component_sign_extension"] == "sign_extend_to_16"
        assert (manifest["input_samples"], manifest["output_samples"]) == (2048, 2055)
        assert (manifest["valid_start"], manifest["valid_len"]) == (0, 2055)
        assert not _all_keys(manifest) & {
            *RTL_FIELDS,
            *RTL_MATCHING_FIELDS,
            *LEGACY_ALIASES,
            "sqnr_cross_db",
            "vector_manifest_sha256",
        }


def test_fxp_manifests_apply_the_acceptance_gates_by_frame_role(exported):
    _, paths = exported

    for path in paths[1:]:
        manifest = _load(path)
        evidence = manifest["fxp_evidence"]
        assert evidence["internal_overflow_count"] == 0
        if manifest["vector_set"] == "canonical":
            assert evidence["frame_role"] == "acceptance"
            assert evidence["sqnr_db"] >= 40.0
            assert evidence["output_saturation_count"] == 0
            assert evidence["gates"] == {
                "split_half_stable": True,
                "sqnr_at_least_40_db": True,
                "zero_internal_overflow": True,
                "zero_output_saturation": True,
            }
        else:
            assert evidence["frame_role"] == "diagnostic"
            assert evidence["gates"] == {"zero_internal_overflow": True}
        assert manifest["acceptance"]["production_acceptance_passed"] is True
        assert manifest["acceptance"]["output_codes_match_t21"] is True


def test_fxp_sidecars_and_hashes_bind_every_payload_and_upstream_artifact(exported):
    output_dir, paths = exported
    t21_sha256 = _sha256(_T21_EVIDENCE)

    for path in (output_dir / "fxp_expected").rglob("*"):
        if path.is_file() and not path.name.endswith(".sha256"):
            digest, name = path.with_name(path.name + ".sha256").read_text(encoding="utf-8").split()
            assert name == path.name
            assert digest == _sha256(path)
    assert _load(paths[0])["hashes"]["t21_evidence_sha256"] == t21_sha256
    for path in paths[1:]:
        manifest = _load(path)
        hashes = manifest["hashes"]
        payload = manifest["payload"]
        f1_manifest = _COMMITTED_DIR / "float_reference" / manifest["vector_set"] / manifest["vector_case"] / path.name
        assert hashes["f1_manifest_sha256"] == _sha256(f1_manifest)
        assert hashes["t21_evidence_sha256"] == t21_sha256
        assert hashes["rrc8_manifest_sha256"] == _sha256(gen_vectors._ARTIFACT_PATH)
        assert hashes["coefficient_table_sha256"] == _sha256(path.parent / payload["coefficient_file"])
        assert hashes["input_hex_sha256"] == _sha256(path.parent / payload["input_file"])
        assert hashes["expected_hex_sha256"] == _sha256(path.parent / payload["expected_file"])


@pytest.mark.parametrize(("vector_set", "vector_case"), _EXPECTED_FRAMES)
def test_expected_codes_are_the_accepted_integer_model_output(exported, vector_set, vector_case):
    output_dir, _ = exported
    frame_dir = output_dir / "fxp_expected" / vector_set / vector_case
    samples = read_samples(_COMMITTED_DIR / "float_reference" / vector_set / vector_case / "input_samples.c16.bin")
    accepted = _load(_T21_EVIDENCE)["frames"]["16"][f"{vector_set}/{vector_case}"]

    for domain, tag in (("time", "time"), ("frequency", "freq")):
        i_codes, q_codes = _unpack_records(frame_dir / f"expected_{tag}.hex")
        result = fxp.run_fxp_model(domain, samples)
        np.testing.assert_array_equal(i_codes, result.i_codes)
        np.testing.assert_array_equal(q_codes, result.q_codes)
        manifest_codes = _load(frame_dir / f"manifest_{tag}.json")["hashes"]["output_codes_sha256"]
        assert manifest_codes == result.codes_sha256() == accepted[domain]["output_codes_sha256"]


def test_canonical_expected_codes_are_the_codes_t21_accepted(exported):
    output_dir, _ = exported
    frame_dir = output_dir / "fxp_expected" / "canonical" / "none"

    for domain, tag in (("time", "time"), ("frequency", "freq")):
        i_codes, q_codes = _unpack_records(frame_dir / f"expected_{tag}.hex")
        decoded_sha256 = hashlib.sha256(np.stack((i_codes, q_codes), axis=1).astype("<i8").tobytes()).hexdigest()
        assert decoded_sha256 == _T21_CANONICAL_CODES_SHA256[domain]


@pytest.mark.parametrize(("vector_set", "vector_case"), _EXPECTED_FRAMES)
def test_input_codes_are_the_exact_q2_14_frame(exported, vector_set, vector_case):
    output_dir, _ = exported
    i_codes, q_codes = _unpack_records(output_dir / "fxp_expected" / vector_set / vector_case / "input.hex")
    samples = read_samples(_COMMITTED_DIR / "float_reference" / vector_set / vector_case / "input_samples.c16.bin")

    np.testing.assert_array_equal(i_codes, samples.real * (1 << 14))
    np.testing.assert_array_equal(q_codes, samples.imag * (1 << 14))
    assert set(np.unique(np.concatenate((i_codes, q_codes))).tolist()) <= {-16384, 0, 16384}


def test_canonical_expected_codes_are_not_a_cast_of_the_float_reference(exported):
    """On the canonical frame a cast of the float output differs from the integer model.

    The cast matches the model on most sys_corners frames, so they cannot tell
    the two apart; this check and the T21 code hashes carry the guard.
    """
    output_dir, _ = exported
    frame_dir = output_dir / "fxp_expected" / "canonical" / "none"

    for tag in ("time", "freq"):
        reference = read_samples(_COMMITTED_DIR / "float_reference" / "canonical" / "none" / f"reference_{tag}.c16.bin")
        i_codes, q_codes = _unpack_records(frame_dir / f"expected_{tag}.hex")
        cast_i = np.rint(reference.real * (1 << 14)).astype(np.int64)
        cast_q = np.rint(reference.imag * (1 << 14)).astype(np.int64)
        assert np.count_nonzero((cast_i != i_codes) | (cast_q != q_codes)) > 0


def test_coefficient_table_keeps_the_float_golden_beside_the_production_codes(exported):
    _, paths = exported
    table = _load(paths[0])
    f1_hashes = _load(_COMMITTED_DIR / "float_reference" / "canonical" / "none" / "manifest_time.json")["hashes"]

    assert table["coefficients_float64"] == load_rrc8_coefficients().tolist()
    assert table["coefficient_codes"] == _PRODUCTION_COEFFICIENT_CODES
    assert table["coefficient_codes"] == [int(code) for code in fxp.quantize_coefficients()]
    assert (table["format"], table["W_common"], table["F_coeff"], table["rounding_mode"]) == ("Q2.14", 16, 14, "RNE")
    assert (table["ordering"], table["delay_samples"], table["range_violation_count"]) == ("ascending_time", 3.5, 0)
    assert table["hashes"]["rrc8_manifest_sha256"] == f1_hashes["rrc8_manifest_sha256"]
    assert table["hashes"]["coefficients_sha256"] == f1_hashes["coefficients_sha256"]
    assert "versions" not in table["provenance"]


def test_coefficient_saturation_is_refused_and_nothing_is_written(monkeypatch, tmp_path):
    saturating = load_rrc8_coefficients() * 3.0
    monkeypatch.setattr(gen_vectors, "load_rrc8_coefficients", lambda: saturating)

    with pytest.raises(ValueError, match="range violation"):
        export_fxp_expected(tmp_path, vectors_dir=_COMMITTED_DIR)
    assert not list(tmp_path.iterdir())


def _reject_acceptance(evidence: dict) -> None:
    evidence["production_acceptance"]["passed"] = False


def _accept_other_width(evidence: dict) -> None:
    evidence["production_acceptance"]["W_common"] = 14


def _change_f1_hash(evidence: dict) -> None:
    evidence["f1_manifest_sha256"]["canonical/none"]["time"] = "0" * 64


def _change_accepted_codes(evidence: dict) -> None:
    evidence["frames"]["16"]["sys_corners/max_alternation"]["frequency"]["output_codes_sha256"] = "0" * 64


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (_reject_acceptance, "not numerically accepted"),
        (_accept_other_width, "not numerically accepted"),
        (_change_f1_hash, "F1 manifests differ"),
        (_change_accepted_codes, "output codes differ"),
    ],
)
def test_export_refuses_without_a_matching_t21_acceptance(tmp_path, mutate, error):
    evidence = _load(_T21_EVIDENCE)
    mutate(evidence)
    acceptance_path = tmp_path / "evidence_manifest.json"
    acceptance_path.write_text(json.dumps(evidence), encoding="utf-8")
    output_dir = tmp_path / "vectors"

    with pytest.raises(ValueError, match=error):
        export_fxp_expected(output_dir, vectors_dir=_COMMITTED_DIR, acceptance_path=acceptance_path)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    ("frame", "domain", "field", "value", "error"),
    [
        ("sys_corners/corner_repeat", "frequency", "internal_overflow_count", 1, "frequency.zero_internal_overflow"),
        ("canonical/none", "time", "sqnr_db", 39.0, "time.sqnr_at_least_40_db"),
        ("canonical/none", "frequency", "output_saturation_count", 2, "frequency.zero_output_saturation"),
        ("canonical/none", None, "sqnr_cross_db", 30.0, "sqnr_cross"),
    ],
)
def test_export_refuses_a_frame_that_fails_an_acceptance_gate(
    monkeypatch, tmp_path, frame, domain, field, value, error
):
    measure_frame = fxp.measure_frame
    target = frame_samples(*frame.split("/"))

    def failing_measure_frame(samples, references, policy=fxp.PRODUCTION_POLICY, trace=False):
        run = measure_frame(samples, references, policy, trace)
        if np.array_equal(samples, target):
            entry = run["measurement"] if domain is None else run["measurement"][domain]
            entry[field] = value
        return run

    monkeypatch.setattr(fxp, "measure_frame", failing_measure_frame)
    with pytest.raises(ValueError, match=error):
        export_fxp_expected(tmp_path, vectors_dir=_COMMITTED_DIR)
    assert not list(tmp_path.iterdir())


def test_export_refuses_an_unstable_canonical_split_half(monkeypatch, tmp_path):
    monkeypatch.setattr(gen_vectors, "split_half_is_stable", lambda reference, fxp_output: False)

    with pytest.raises(ValueError, match="split_half_stable"):
        export_fxp_expected(tmp_path, vectors_dir=_COMMITTED_DIR)
    assert not list(tmp_path.iterdir())


def test_export_refuses_tampered_f1_frames(tmp_path):
    shutil.copytree(_COMMITTED_DIR / "float_reference", tmp_path / "float_reference")
    payload = tmp_path / "float_reference" / "sys_corners" / "max_alternation" / "reference_freq.c16.bin"
    data = bytearray(payload.read_bytes())
    data[0] ^= 1
    payload.write_bytes(bytes(data))

    with pytest.raises(ValueError, match="hash does not match"):
        export_fxp_expected(tmp_path)
    assert not (tmp_path / "fxp_expected").exists()


def test_fxp_export_is_byte_identical(exported, tmp_path):
    output_dir, _ = exported
    export_fxp_expected(tmp_path, vectors_dir=_COMMITTED_DIR)

    assert _tree_bytes(tmp_path) == _tree_bytes(output_dir)


def test_committed_fxp_vectors_are_current(exported):
    """Committed F2 vectors must equal a fresh export; only the manifests' tool versions depend on the host."""
    output_dir, _ = exported
    fresh_dir = output_dir / "fxp_expected"
    committed_dir = _COMMITTED_DIR / "fxp_expected"
    fresh_files = {path.relative_to(fresh_dir) for path in fresh_dir.rglob("*") if path.is_file()}
    committed_files = {path.relative_to(committed_dir) for path in committed_dir.rglob("*") if path.is_file()}
    assert committed_files == fresh_files

    for relative in sorted(fresh_files):
        if relative.name.startswith("manifest_"):
            if relative.suffix == ".json":
                fresh = _load(fresh_dir / relative)
                committed = _load(committed_dir / relative)
                fresh["provenance"].pop("versions")
                committed["provenance"].pop("versions")
                assert committed == fresh, relative
            continue
        assert (committed_dir / relative).read_bytes() == (fresh_dir / relative).read_bytes(), relative


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("latency_samples", 0, "not allowed"),
        ("SPC", 1, "not allowed"),
        ("flush_samples", 7, "not allowed"),
        ("sqnr_cross_db", 89.29, "not allowed"),
        ("latency_time", 0, "not allowed"),
        ("W_common", 18, "production numeric invariant"),
        ("rounding_mode", "truncation_toward_zero", "rounding_mode"),
        ("fft_mode", "baseline_B_one_bit_per_stage", "fft_mode"),
        ("W_acc_time", 34, "W_acc_time"),
        ("component_sign_extension", "none", "component_sign_extension"),
    ],
)
def test_fxp_validator_rejects_rtl_cross_domain_and_non_production_fields(exported, field, value, error):
    with pytest.raises(ValueError, match=error):
        validate_manifest(_fxp_manifest(exported) | {field: value})


@pytest.mark.parametrize("field", [*FXP_FIELDS, "component_sign_extension", "hashes"])
def test_fxp_validator_requires_the_policy_and_packing_fields(exported, field):
    manifest = _fxp_manifest(exported)
    del manifest[field]

    with pytest.raises(ValueError, match="missing"):
        validate_manifest(manifest)


def test_cli_exports_fxp_expected_next_to_the_f1_frames(monkeypatch, tmp_path, capsys, exported):
    shutil.copytree(_COMMITTED_DIR / "float_reference", tmp_path / "float_reference")
    monkeypatch.setattr("sys.argv", ["gen_vectors.py", "--stage", "fxp_expected", "--output-dir", str(tmp_path)])

    gen_vectors.main()
    printed = [Path(line) for line in capsys.readouterr().out.split()]
    assert printed == [tmp_path / path.relative_to(exported[0]) for path in exported[1]]
    assert _tree_bytes(tmp_path / "fxp_expected") == _tree_bytes(exported[0] / "fxp_expected")
