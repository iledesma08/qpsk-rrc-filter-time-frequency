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
- `fxp.py` (T20): integer FXP models of both domains (production `Q2.14`, sweep-parameterized `Q2.(W-2)`): the 35-bit time MAC and the integer FFT16 overlap-save path (DIF FFT, `H[k]`, DIT IFFT, one cast), with overflow/saturation/rounding counters and per-stage traces.
- `sqnr.py` (T20): complex SQNR, cross-domain SQNR and the split-half check over the full causal window (ADR-0005).
- `plot_vectors.py` (T13): review-evidence plots of the F1 float references (imported lazily by `gen_vectors.py --plots-dir`). Plots are evidence under `artifacts/`, never vectors.
- `gen_vectors.py` (T13): staged vector generator. It writes the F1 `float_reference` stage to `sim/vectors/` with `.sha256` sidecars and stage-validated manifests. The `fxp_expected` (T22) and `rtl_matching` (T31/T33) exports and the integer-only `{Q,I}` packer are interfaces for those later stages. Do not edit vectors by hand.
- `tests/`: coefficient, shared-stimulus, time-golden, frequency-golden, and vector-generator suites, plus an import smoke test. `test_fxp.py` holds the T20 directed arithmetic checks and the production gate preview; `test_sqnr.py` covers the SQNR formulas.

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

## Integer FXP models (T20)

Regenerate the T20 evidence with:

```bash
python sim/python/fxp.py --output-dir sim/python/artifacts/t20-fxp
```

The generator reads the F1 inputs and float references from `sim/vectors/float_reference/` and checks their hashes first. It writes `evidence_manifest.json` (schema section 2 policy fields, the frozen integer constants, per-frame SQNR/split-half/cross-domain SQNR, overflow and saturation counters, per-point ranges and rounding/tie counts) and `traces.json` (per-stage integer traces for stage-by-stage RTL comparison). `--width W` runs a diagnostic `Q2.(W-2)` width with the same rules; the sweep itself and numerical acceptance are T21 (#45), and expected-code vectors are T22 (#46). Nothing here writes to `sim/vectors/`.

The arithmetic follows the production-A integer freeze amendment in `docs/contracts/fxp-policy-16.md`. All values are exact Python integers in NumPy `object` arrays, so nothing wraps silently. Additions and products are exact integer operations; the narrowing primitives (`quantize`, `round_shift`, `saturate`) use `fxpmath` with `rounding='around'` (RNE) and `overflow='saturate'`.

`fxpmath` 0.4.10 rounds through float64, so it is exact only while the operand has at most 53 significant bits; its extended-precision path is not exact either and warns that rounding may be bypassed. The inverse-FFT twiddle products reach about 2^47 at W=16 and about 2^53 at W=18. `round_shift` therefore subtracts an even multiple of the rounding step first (ties-to-even does not change under even integer offsets) and lets `fxpmath` round the reduced operand, which lies in `[0, 2^(shift+1))`. `saturate` accepts at most 63-bit inputs (the `fxpmath` int64 path) and at most 53-bit outputs. Tests compare `round_shift` against exact `Fraction` rounding up to 90 bits. `test_fxp.py` checks that the committed evidence matches a regeneration (except `provenance`), so changing the model requires regenerating it.

## T03 transport fixtures (#42)

`tests/rtl_shell_fixture.py` is a test utility, not the RRC vector generator.
It produces reproducible signed integer `{Q[15:0],I[15:0]}` records, identity
expected outputs, a metadata-only manifest, and SHA-256 sidecars. It refuses
to write into `sim/vectors/`. The RTL runners generate these under `.build/rtl/`.

```bash
python sim/python/tests/rtl_shell_fixture.py \
  --output .build/rtl/example-fixture --data-width 8 --spc 4 --count 33 \
  --flush-samples 2
python -m pytest sim/python/tests/test_rtl_shell_fixture.py -v
python -m pytest sim/python/tests/test_rtl_stream.py -v
python -m pytest sim/python/tests/test_rtl_config.py -v
```

`--flush-samples` is nonnegative and defaults to zero. `--count 33` keeps
`input.hex` at 33 original source records; `expected.hex` contains those records
plus the declared flush zeros, not beat-padding expectations. The manifest
declares `flush_samples`, `transport_padding_samples`, `accepted_input_samples`,
and `raw_output_samples`: accepted count rounds source plus flush up to a whole
SPC beat, and raw output count equals accepted count for identity transport.
The example has 35 expected records, 36 accepted/raw samples, and one transport
padding sample. Consume it with
`bash rtl/time_serial/run.sh --vectors .build/rtl/example-fixture`; flush is a
fixture-generator option, not a new runner option. See `rtl/tb/README.md` for
physical counting, valid-window comparison, and bounded drain checks.

Widths such as 8/12 test signed transport packing diagnostically; production
`W_common=16`, `F_data=F_coeff=14` (`Q2.14`) is already accepted by contract #16.
T03 contains no fractional arithmetic and does not establish numerical
acceptance. T20/T21 validation and T22's frozen production coefficient/expected
code export remain pending; the fixture is not a replacement for `gen_vectors.py`.

The RTL regression needs `iverilog` and `vvp` in PATH. Without them simulation
cases are skipped by the Python job and executed in the required RTL CI job
instead. The runner diagnostic needs no simulator. The generator remains a
test fixture utility even though the simulation runner invokes its CLI; it is
not production-vector generation. Its block constants mirror the accepted
`rrc_pkg.sv` baseline and are checked by the TB, not parsed from RTL at runtime.
The pre-#70 local suite with Icarus available passed 65 tests on 2026-10-02;
that historical count does not include the time-golden tests now on `main`.
These tests establish streaming transport correctness, not SQNR or RRC matching.
After the PR #73 review changes, the suite was rechecked locally on 2026-10-06:
208 passed, including 92 inherited cases, 9 fixture cases, 61 stream cases and
46 structural/configuration cases, with no skips. All four wrappers
also passed `bash rtl/run.sh`. See `rtl/tb/README.md` for the scoped evidence;
these results do not establish RRC arithmetic, SQNR, or physical timing.
