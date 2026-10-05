# sim/python — golden simulator (float) + fxp model

Use Python 3.12.x. Run these commands from the repository or worktree root to install the pinned dependencies and run the tests:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r sim/python/requirements.txt
python -m pytest sim/python -v
```

- `stimulus.py` (T11s, issue #67; T13): shared deterministic canonical QPSK samples for the time and frequency goldens, plus the three `sys_corners` frames.
- `golden_time.py` (T11): full causal float time-domain RRC reference and folded-sample/spectrum evidence from the shared stimulus. The folded view shows discrete samples around symbol centers, not a continuous eye diagram.
- `golden_freq.py` (T12): full causal float frequency-domain RRC reference using complex FFT16, response multiplication, IFFT16, and forced-50% OLS (`H=8`). It consumes the shared stimulus and validated `rrc8-v1` coefficients.
- `rrc_coefs.py` (T10): generates and validates the 8 RRC coefficients with α=0.5.
- `fxp.py` + `sqnr.py` (T20, placeholders): pending fixed-point model and SQNR ≥ 40 dB measurement.
- `plot_vectors.py` (T13): review-evidence plots of the F1 float references (imported lazily by `gen_vectors.py --plots-dir`). Plots are evidence under `artifacts/`, never vectors.
- `gen_vectors.py` (T13): staged vector generator. It writes the F1 `float_reference` stage to `sim/vectors/` with `.sha256` sidecars and stage-validated manifests. The `fxp_expected` (T22) and `rtl_matching` (T31/T33) exports and the integer-only `{Q,I}` packer are interfaces for those later stages. Do not edit vectors by hand.
- `tests/`: coefficient, shared-stimulus, time-golden, frequency-golden, and vector-generator suites, plus an import smoke test. T20 behavior tests remain pending.

## Time-Golden Evidence

Generate the plots and their evidence manifest with:

```bash
python sim/python/golden_time.py --output-dir sim/python/artifacts/t11-time-golden
```

The output directory contains `folded_samples_natural_grid.png`, `spectrum.png`, and `evidence_manifest.json`. The canonical input has 2048 complex samples; the full causal time-golden output has 2055 samples, including the filter tail.

The frequency golden uses 16-sample frames with an 8-sample hop: each frame contains eight history samples and eight new samples, and emits `z[8:16]`. The complete canonical output has 2055 samples. `test_golden_equivalence.py` verifies its agreement with the time golden over the full output using `rtol=1e-10` and `atol=1e-12` per ADR-0005.

## Frequency-Golden Evidence

Generate the T12 plots and their evidence manifest with:

```bash
python sim/python/golden_freq.py \
	--output-dir sim/python/artifacts/t12-freq-golden \
	--comparison-output-dir sim/python/artifacts/golden_comparison
```

The T12 directory contains `ols_boundaries.png`, `impulse_response.png`, and `evidence_manifest.json`. The comparison directory contains `canonical_time_frequency_comparison.png`. The manifest records the canonical input and coefficient hashes, forced-50% OLS schedule, valid output window, time/frequency error, source and plot hashes, and tool versions. This is floating-point reference evidence only; it is not FXP or RTL evidence. The entries in `manifest["plots"]` are resolved relative to `output_dir.parent` (equivalent to `manifest_path.parent.parent` for the generated T12 manifest), so a comparison directory outside that parent is recorded with `../` segments instead of failing with a `ValueError`.

Both time- and frequency-golden manifests use the same array-hash serialization: SHA-256 over C-order bytes, with samples encoded as little-endian complex128 (`<c16`) and real RRC coefficients encoded as little-endian float64 (`<f8`). Each manifest records this policy in `hash_serialization`, making canonical input hashes directly comparable across domains and independent of host byte order.

The shared time/frequency integration check lives in `tests/test_golden_equivalence.py`; the frequency-specific tests continue to exercise the public filter and its OLS block selector.

## F1 Float References (T13)

Regenerate the staged F1 vectors with:

```bash
python sim/python/gen_vectors.py --stage float_reference --output-dir sim/vectors
```

The generator writes the canonical frame and the three `sys_corners` frames, each with 2048 input samples and 2055 full causal outputs. Each frame gets one manifest per domain. `tests/test_gen_vectors.py` covers byte-identical regeneration, time/frequency agreement on every frame (`rtol=1e-10`, `atol=1e-12`), sidecars and hashes, and stage validation, which rejects invented FXP, latency, or legacy fields. It also checks that the committed `sim/vectors/` still matches the current sources, so editing a golden, the stimulus, or the generator requires regenerating. Layout and payload encoding: `sim/vectors/README.md`.

### Vector evidence plots

Generate the review plots together with the vectors (or on their own, since the vectors are regenerated deterministically) with:

```bash
python sim/python/gen_vectors.py --output-dir sim/vectors \
	--plots-dir sim/python/artifacts/t13-reference-vectors
```

`--plots-dir` is optional and only valid for `--stage float_reference`; the default regeneration and the byte-identical check do not depend on matplotlib output. The directory contains one plot per frame (`canonical_none.png`, `sys_corners_corner_repeat.png`, `sys_corners_max_alternation.png`, `sys_corners_single_symbol_perturbation.png`), each with the input samples, the 2055-sample float reference, and a zoom on what the frame stresses. It also contains `time_frequency_agreement.png` (|time - frequency| per frame against `atol=1e-12`) and `evidence_manifest.json` (plot hashes, hashes of the vector payloads plotted, the maximum time/frequency error per frame, and tool versions). I and Q use the T11 colors, with Q drawn dashed on top because they coincide wherever a symbol is `+1+j` or `-1-j`. PNG bytes can vary across matplotlib versions, so the plot hashes are evidence of this run and are not compared in CI.
