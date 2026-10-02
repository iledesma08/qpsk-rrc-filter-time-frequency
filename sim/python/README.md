# sim/python — golden simulator (float) + fxp model

The local environment is Python 3.12.x. Install the pinned dependencies with:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r sim/python/requirements.txt
python -m pytest sim/python -v
```

- `rrc_coefs.py` (T10): implemented coefficient generation/loading and the frozen
  `rrc8-v1` artifact under `artifacts/`.
- `stimulus.py` (#67): implemented shared canonical QPSK samples with 2x zero
  insertion; both goldens consume this source.
- `golden_time.py` (T11) and `golden_freq.py` (T12): currently entry-point stubs
  on this branch; full time/frequency filtering arrives in their own issues.
- `fxp.py` + `sqnr.py` (T20): stubs for fixed-point and common SQNR measurement.
- `gen_vectors.py` (T13): currently a stub; the completed generator is the only
  writer authorized to produce RRC goldens in `sim/vectors/`.
- `tests/`: coefficient/stimulus checks.
