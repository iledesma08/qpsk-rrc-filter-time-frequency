# Python float simulator as golden

The Python float64 simulator is the correctness reference for the whole project: it defines the RRC coefficients, generates golden vectors, and measures SQNR of the fxp model and vector matching of the RTL.

We choose Python (NumPy/SciPy/pytest) for iteration speed and plotting, even though the final RTL targets another language.
