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
