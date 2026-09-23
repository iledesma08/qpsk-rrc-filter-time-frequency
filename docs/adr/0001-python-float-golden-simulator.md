# Python float simulator as golden

**Status:** accepted, extended by contracts. Normative: `docs/contracts/rrc-coefficient-contract-13.md` + `docs/contracts/qpsk-stimulus-15.md` + `docs/contracts/fxp-policy-16.md`. This ADR defines only that Python float64 is the correctness reference; frozen coefficients, stimulus frame, and FXP/SQNR details live in the contracts.

The Python float64 simulator is the correctness reference for the whole project: it defines the RRC coefficients, generates golden vectors, and measures SQNR of the fxp model and vector matching of the RTL.

We choose Python (NumPy/SciPy/pytest) for iteration speed and plotting, even though the final RTL targets another language.
