# sim/python — golden simulator (float) + fxp model

Use Python 3.12.x. Run these commands from the repository or worktree root to install the pinned dependencies and run the tests:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r sim/python/requirements.txt
python -m pytest sim/python -v
```

- `stimulus.py` (T11s, issue #67): shared deterministic canonical QPSK samples for the time and frequency goldens.
- `golden_time.py` (T11): full causal float time-domain RRC reference and folded-sample/spectrum evidence from the shared stimulus. The folded view shows discrete samples around symbol centers, not a continuous eye diagram.
- `golden_freq.py` (T12, placeholder): pending frequency-domain golden via FFT, response multiplication, and IFFT using the accepted overlap-save schedule.
- `rrc_coefs.py` (T10): generates and validates the 8 RRC coefficients with α=0.5.
- `fxp.py` + `sqnr.py` (T20, placeholders): pending fixed-point model and SQNR ≥ 40 dB measurement.
- `gen_vectors.py` (T13, placeholder): reserved for generating files in `sim/vectors/` with `.sha256` sidecars. Do not edit vectors by hand.
- `tests/`: coefficient, shared-stimulus, and time-golden suites, plus an import smoke test. T12/T20 behavior tests remain pending.

## Time-Golden Evidence

Generate the plots and their evidence manifest with:

```bash
python sim/python/golden_time.py --output-dir sim/python/artifacts/t11-time-golden
```

The output directory contains `folded_samples_natural_grid.png`, `spectrum.png`, and `evidence_manifest.json`. The canonical input has 2048 complex samples; the full causal time-golden output has 2055 samples, including the filter tail.

Time/frequency equality over the complete canonical output remains an integration gate for #40/#41. Once the frequency golden is implemented, compare both outputs with `rtol=1e-10` and `atol=1e-12` per ADR-0005; the current tests do not yet verify that comparison.

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

The RTL regression needs `iverilog` and `vvp` in PATH. Without them those tests
are skipped by the Python job and executed in the required RTL CI job instead.
The pre-#70 local suite with Icarus available passed 65 tests on 2026-10-02;
that historical count does not include the time-golden tests now on `main`.
These tests establish streaming transport correctness, not SQNR or RRC matching.
The adapted post-#70 suite was rechecked locally on 2026-10-05: 92 passed,
including 9 fixture cases and 44 Icarus cases, with no skips. All four wrappers
also passed `bash rtl/run.sh`. See `rtl/tb/README.md` for the scoped evidence;
these results do not establish RRC arithmetic, SQNR, or physical timing.
