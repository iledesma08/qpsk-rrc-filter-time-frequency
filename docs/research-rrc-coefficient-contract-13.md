# RRC Coefficient Contract Research

Research ticket: [#13](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/13)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-21

Branch: `research/rrc-coefficient-contract`

Scope: research only. This note does not add simulator, RTL, vectors, or other project implementation code.

## Executive Recommendation

Use the following contract unless the human team explicitly chooses a different normalization or latency convention:

- Set the symbol period to `T=1` and sample at `sps=2`.
- For `N=8`, use the centered even-length grid `t[n] = (n - (N-1)/2) * T/sps`, for `n=0..7`.
- Evaluate the standard RRC impulse response, including explicit finite-value branches at `t=0` and `t=+/-T/(4*alpha)`.
- Normalize the eight sampled values to discrete unit energy: `sum(h[n]^2) = 1`.
- Store coefficients in increasing time order, from `t=-1.75*T` to `t=+1.75*T`.
- Treat each QPSK real component as the repository's declared value `+/-1.0`. For a 16-bit signed input, use scale `2^14` (`Q2.14`) so both `+1` and `-1` are exact. Use a 16-bit `Q1.15` coefficient scale for the recommended normalized coefficients.
- Document the FIR delay as `(N-1)/2 = 3.5` samples, not as either 3 or 4 samples.

This recommendation preserves the fixed repository constraints while making the even-length half-sample delay explicit. It is not the same as asking a standard integer-span RRC API for eight taps.

## Repository Facts

These are facts already recorded in the repository, not new decisions made by this research:

- `README.md` fixes QPSK as `+/-1 +/- j`, RRC `alpha=0.5`, 2x oversampling, and 8 coefficients.
- `CONTEXT.md` defines a coefficient as one of the eight discrete RRC coefficients and defines the Python float64 simulator as the golden reference through ADR-0001.
- `sim/python/README.md` reserves `rrc_coefs.py` for the future T10 generator and explicitly says it generates eight RRC coefficients.
- ADR-0004 fixes external complex records as `{Q[15:0], I[15:0]}` but does not yet define the numeric fixed-point scale represented by those 16-bit fields.
- ADR-0005 fixes the complex SQNR equation and the float time/frequency equality tolerances, but does not define the RRC coefficient normalization or input scale.

## Source Facts

### RRC Formula and Singular Points

The NVIDIA Sionna `RootRaisedCosineFilter` documentation gives the standard piecewise RRC impulse response. With `u=abs(t)/T`, `0 < alpha <= 1`, and `T` the symbol period, the ordinary branch is:

```text
g(t) = (1/T) * [sin(pi*u*(1-alpha))
                + 4*alpha*u*cos(pi*u*(1+alpha))]
              / [pi*u*(1-(4*alpha*u)^2)]
```

The two removable singularities have these limits:

```text
g(0) = (1/T) * [1 + alpha*(4/pi - 1)]

g(+/-T/(4*alpha)) = alpha/(T*sqrt(2)) * [
    (1 + 2/pi)*sin(pi/(4*alpha))
    + (1 - 2/pi)*cos(pi/(4*alpha))
]
```

Sionna's source evaluates the absolute time before applying the formula, which is a useful way to enforce exact even symmetry in floating-point output. The same source explicitly branches for both singular points.

For this ticket, with `T=1` and `alpha=0.5`, the two special values are:

```text
g(0)   = 1.136619772367581
g(+/-0.5) = 0.578632469632550
```

The Purdue EE538 square-root raised-cosine reference describes the same ideal pulse and notes that the ideal response has infinite support, so a practical FIR is a time-truncated approximation.

### Standard API Length and Normalization Conventions

MathWorks `rcosdesign` documents an RRC FIR specified by integer symbol span and samples per symbol. Its length is `span*sps + 1`, its order is `span*sps`, and its coefficients have unit energy. With integer `span` and `sps=2`, that convention produces an odd number of coefficients. It cannot directly produce an eight-coefficient filter.

Sionna follows the same design distinction: its built-in RRC length is derived from an integer symbol span and samples per symbol, and an even product is increased to the next odd length. Its `normalize=True` path normalizes the discrete coefficient vector by its L2 norm.

GNU Radio's `firdes::root_raised_cosine` is a useful counterexample. Its source forces an odd tap count and normalizes by the sum of the taps, i.e. unity DC gain, rather than by discrete L2 energy. Therefore neither "RRC normalization" nor an external library's tap count should be assumed without recording it.

### SciPy Operations Relevant to Reproduction

SciPy does not need to define the RRC formula for this project. The formula should be implemented from the contract above, then SciPy can provide independent checks:

- `scipy.signal.freqz` computes the digital FIR frequency response. Its coefficient input is the numerator sequence in delay order, and it supports `whole=True` and an explicit sampling frequency.
- `scipy.signal.upfirdn` documents the zero-insertion upsample, FIR, and downsample operation. Its `h` argument is a one-dimensional FIR coefficient sequence.
- `scipy.signal.fftconvolve` provides an independent FFT-based linear-convolution check against direct convolution.
- `scipy.fft.fft` uses an unscaled forward transform by default and `scipy.fft.ifft` applies the inverse `1/N` scaling by default. Their documented frequency-bin ordering must be preserved when implementing an FFT-domain baseline.

## Exact Recommended Discrete Contract

### Grid

Let `N=8`, `sps=2`, and `T=1`. Define:

```text
t[n] = (n - (N-1)/2) / sps,  n=0,...,N-1
```

The grid is therefore:

```text
[-1.75, -1.25, -0.75, -0.25, +0.25, +0.75, +1.25, +1.75] * T
```

It is symmetric about zero and has its center between the fourth and fifth coefficients. There is no sample at `t=0`. The endpoints are 3.5 symbol periods apart. Do not describe this as a conventional four-symbol-span, eight-tap `rcosdesign` filter: the conventional integer-span relationship would use nine taps at 2 samples per symbol.

### Raw Values

Evaluating the formula with `alpha=0.5`, `T=1`, and the absolute-time symmetry rule gives:

```text
[ 0.015468180292133855,
 -0.15684266071530739,
  0.15684266071530747,
  0.97449535840443269,
  0.97449535840443269,
  0.15684266071530747,
 -0.15684266071530739,
  0.015468180292133855 ]
```

The raw sampled energy is `1.9981594171876955`, and the raw coefficient sum is `1.9799270773931332`.

### Normalization

The recommended finite-FIR normalization is:

```text
scale = sqrt(sum(raw[n]^2 for n=0..7))
h[n] = raw[n] / scale
```

For this vector, `scale=1.4135626682916098`. The resulting canonical float64 coefficients are:

```text
[ 0.010942691568693054,
 -0.11095557645481881,
  0.11095557645481886,
  0.68938956882766222,
  0.68938956882766222,
  0.11095557645481886,
 -0.11095557645481881,
  0.010942691568693054 ]
```

Checks from the independent calculation:

```text
sum(h[n]^2) = 0.99999999999999978  # float64 roundoff
sum(h[n])   = 1.4006645207927106   # not unity DC gain
sum(abs(h[n])) = 1.8444868266119858
max(abs(h[n])) = 0.68938956882766222
```

The L2 choice is recommended because it matches the unit-energy convention documented by MathWorks and the unit-power normalization implemented by Sionna. It also makes a matched transmit/receive interpretation straightforward. Unity-DC normalization is a valid alternative, but it produces a different vector and must not be mixed with the energy-normalized contract.

### Ordering and Delay

Use ascending physical time as the external order:

```text
h[0] = g(-1.75*T)
h[1] = g(-1.25*T)
...
h[7] = g(+1.75*T)
```

For a causal direct-form FIR, the same sequence is assigned to delays `0` through `7`:

```text
y[m] = sum(h[k] * x[m-k] for k=0..7)
```

Because the vector is symmetric, reversing it gives the same values, but the order still matters for the documented delay, FFT bin alignment, vector manifests, and future non-symmetric experiments. The linear-phase delay is:

```text
D = (N-1)/2 = 3.5 samples = 1.75*T
```

The half-sample delay is a real consequence of the required even tap count. A comparison that rounds this delay to 3 or 4 samples changes the contract.

### Fixed-Point Input Scale

The repository declares the unnormalized QPSK constellation `I,Q in {+1,-1}`. For a signed W-bit two's-complement input with per-component scale `Sx=2^Fx`, choose `Fx=W-2` if `+1.0` must be exactly representable. In conventional notation this is `Q2.(W-2)`, where the two integer bits include the sign bit. For the existing 16-bit vector fields:

```text
input format: Q2.14
Sx = 2^14
I_int, Q_int in {+16384, -16384}
```

Do not use signed `Q1.15` for the declared `+1` component: its largest positive value is `1 - 2^-15`, so `+1` would require saturation or a different interpretation. If the team instead wants unit-magnitude QPSK `( +/-1 +/- j )/sqrt(2)`, that is a different constellation contract and should be recorded as a human decision rather than silently introduced.

The recommended 16-bit coefficient representation is `Q1.15`, with coefficient scale `Sc=2^15`. It is safe because the normalized coefficient magnitude is below one. Round-to-nearest-even gives this example coefficient integer vector:

```text
[359, -3636, 3636, 22590, 22590, 3636, -3636, 359]
```

The coefficient and input integer products have scale `Sc*Sx`. If the output keeps the input's Q2.14 scale, accumulate at the product scale and rescale by `Sc` only after the full eight-term sum. Rounding, saturation, accumulator width, and overflow behavior remain implementation decisions and must be frozen before the FXP sweep.

## Reproducible Checks

The following checks should be part of the future T10/T11 tests. They are checks and acceptance criteria, not implementation code added by this ticket.

### Coefficient Checks

- Recompute the grid from `N=8`, `sps=2`, and `T=1`; assert the eight times equal the listed grid.
- Check exact or tolerance-controlled symmetry: `h == h[::-1]` within `1e-15`.
- Check `abs(sum(h*h)-1) <= 2e-15` for float64.
- Check `max(abs(h)) < 1` and `sum(abs(h))` against the recorded value.
- Exercise the `t=0` branch and the `t=+/-0.5` branch explicitly, even though neither singular point is on the eight-tap grid.
- Evaluate the ordinary branch in both algebraically equivalent forms and require agreement at approximately float64 precision away from singular points.
- Check the FIR phase/delay as `D=3.5` samples. The coefficient symmetry and linear phase should agree with the expected half-sample delay.

### Time and Frequency Checks

- Compare direct `numpy.convolve(x,h)` with `scipy.signal.fftconvolve(x,h,mode="full")` on a deterministic complex QPSK frame.
- Compare the time-domain golden output with the frequency-domain output only after both use the same causal coefficient order, zero padding, FFT/IFFT normalization, and `D=3.5` alignment.
- For an impulse input, compare the complete output against `h` and verify the two equal peak coefficients occur at causal indices 3 and 4.
- For an all-ones real input, check the interior steady-state value against `sum(h)=1.4006645207927106`; this is a diagnostic, not a unity-gain requirement.
- Verify that the FFT-domain block implementation cannot circularly alias the eight-tap response into the valid output window.

### Plot Checks

Generate and retain at least these plots with the parameter manifest beside them:

- A stem plot of the eight normalized coefficients against `t/T`, with a continuous RRC curve over `[-2,2]` for visual comparison. Apply the same finite-vector normalization factor to the continuous curve if comparing amplitudes.
- A zero-padded magnitude response, preferably with at least 4096 points, using `scipy.signal.freqz` or an explicitly documented `scipy.fft` convention. Plot frequency in cycles per symbol and mark the ideal RRC passband edge `|f|=(1-alpha)/(2T)=0.25/T` and stopband edge `|f|=(1+alpha)/(2T)=0.75/T`.
- A deterministic QPSK eye/spectrum plot using a recorded seed and enough guard symbols to separate startup and ending transients. Plot the time coordinate with the 3.5-sample delay visible; do not imply an integer-sample symbol-center alignment that the even-length filter does not provide.

The eight taps are very short for an ideal RRC approximation. The plots should therefore show the finite response and ideal target separately; a visibly imperfect stopband is expected and is not by itself evidence of a formula error.

## Canonical Artifact Specification

The future generated coefficient artifact should carry these fields, either as JSON or as an equivalent manifest:

```text
artifact_version: rrc8-v1
family: root-raised-cosine
alpha: 0.5
symbol_period: 1.0
samples_per_symbol: 2
num_coefficients: 8
grid_formula: t[n] = (n-(N-1)/2)/sps
normalization: discrete_l2_unit_energy
ordering: ascending_time
delay_samples: 3.5
input_constellation_components: [-1.0, +1.0]
input_scale_16bit: Q2.14
coefficient_scale_16bit: Q1.15
coefficients_float64: [the eight values listed above]
```

For a canonical text serialization using the exact decimal strings in this document, the independently computed SHA-256 is:

```text
dfde3e70071c5c921a7237bd02e91de53a68f94063b4f1b54f231912a10c37a1
```

The hash covers this canonical content, in this order, with a final newline:

```text
rrc8-v1
alpha=0.5
symbol_period=1
samples_per_symbol=2
num_coefficients=8
grid=t_n=(n-(N-1)/2)/sps
normalization=divide_by_sqrt(sum(raw**2))
ordering=ascending_time
times=-1.75,-1.25,-0.75,-0.25,0.25,0.75,1.25,1.75
coefficients=0.010942691568693054,-0.11095557645481881,0.11095557645481886,0.68938956882766222,0.68938956882766222,0.11095557645481886,-0.11095557645481881,0.010942691568693054
```

## Open Human Decisions

These items should be reviewed and accepted by the project team before T10 freezes the simulator contract:

- Accept discrete unit-energy normalization, or choose unity DC gain instead.
- Accept the required 3.5-sample delay, or change the design length/grid despite the fixed eight-coefficient assignment.
- Keep the declared `+/-1 +/- j` constellation, or explicitly change to unit-magnitude QPSK.
- Freeze rounding mode, saturation versus wrap, coefficient/input/output Q formats, accumulator width, and output rescaling for FXP.
- Freeze whether the canonical artifact stores full float64 decimals, quantized integers, or both. The recommendation is both, with the float values as golden and integers as derived data.
- Freeze FFT block size, overlap convention, padding, and valid output alignment. This ticket does not resolve the map's separate frequency-domain baseline question.
- Decide whether eye plots should show the natural half-sample output grid, interpolate to symbol centers for presentation only, or use a nine-tap comparison as a separate reference.

## Sources

All web sources below were consulted on 2026-09-21.

- [S1] NVIDIA Sionna `RootRaisedCosineFilter` API. Official documentation gives the RRC piecewise formula, both singular-point limits, span/samples length behavior, discrete convolution, and unit-power normalization option: https://nvlabs.github.io/sionna/phy/api/signal/sionna.phy.signal.RootRaisedCosineFilter.html
- [S2] NVIDIA Sionna filter source. Official source evaluates absolute sampling time, branches at `t=0` and `t=+/-T/(4*beta)`, constructs sampling times, and normalizes by the coefficient L2 norm: https://nvlabs.github.io/sionna/_modules/sionna/phy/signal/filter.html
- [S3] MathWorks `rcosdesign` documentation. Official API documents integer symbol span, samples per symbol, order `span*sps`, length `span*sps+1`, and unit-energy coefficients: https://www.mathworks.com/help/signal/ref/rcosdesign.html
- [S4] Clay S. Turner, *Raised Cosine and Root Raised Cosine Formulae*. The author reference derives the RRC formula and identifies the removable singularities requiring L'Hopital limits: http://www.claysturner.com/dsp/Raised%20Cosine%20and%20Root%20Raised%20Cosine%20Formulae.pdf
- [S5] Purdue EE538, *Square Root Raised Cosine*. Academic DSP reference gives the square-root raised-cosine spectrum/pulse and discusses finite truncation: https://engineering.purdue.edu/~ee538/SquareRootRaisedCosine.pdf
- [S6] GNU Radio `firdes::root_raised_cosine` source. Official implementation forces an odd tap count and normalizes its generated taps by their sum: https://github.com/gnuradio/gnuradio/blob/main/gr-filter/lib/firdes.cc
- [S7] SciPy `freqz` documentation/source. Official API defines FIR coefficient order, frequency units, whole-spectrum mode, and the recommended magnitude plotting call: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.freqz.html
- [S8] SciPy `upfirdn` documentation/source. Official API documents zero-insertion upsampling, FIR filtering, and coefficient argument behavior: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.upfirdn.html
- [S9] SciPy `fftconvolve` documentation/source. Official API documents FFT-based linear convolution and output modes: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.fftconvolve.html
- [S10] SciPy `fft` and `ifft` documentation/source. Official API documents transform normalization and frequency ordering: https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.fft.html and https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.ifft.html
- [R1] Repository `README.md`, `CONTEXT.md`, ADR-0001, ADR-0004, ADR-0005, and `sim/python/README.md`, inspected on the same date.

## Independent Calculation Evidence

The numeric values in this note were independently calculated with CPython `3.12.3` using the displayed formula, `T=1`, `alpha=0.5`, `sps=2`, `N=8`, absolute-time evaluation for symmetry, and float64 arithmetic. No project source file was modified and no project implementation was run.
