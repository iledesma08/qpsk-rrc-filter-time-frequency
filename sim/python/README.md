# sim/python — golden simulator (float) + fxp model

The local environment is Python 3.12.x. Install the pinned dependencies with:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r sim/python/requirements.txt
python -m pytest sim/python -v
```

- `golden_time.py` (to create, T11): QPSK → 2x upsampling → float time-domain RRC.
- `golden_freq.py` (to create, T12): same via FFT→×→IFFT.
- `rrc_coefs.py` (to create, T10): generates the 8 RRC coefs with α=0.5.
- `fxp.py` + `sqnr.py` (T20): quantization and SQNR ≥ 40 dB measurement.
- `gen_vectors.py` (T13): dumps into `../vectors/` with `.sha256`. Only authorized generator.
- `tests/`: one test per T11/T12/T20 DoD.

Requires NumPy/SciPy/pytest (create `requirements.txt` in T10).
