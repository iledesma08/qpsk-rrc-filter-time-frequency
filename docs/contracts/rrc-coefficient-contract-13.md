# RRC Coefficient Contract Research

Research ticket: [#13](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/13)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-21

Updated: 2026-09-22 (expanded human decisions, added the Concepts and FAQ section, and recorded the accepted decisions)

Branch: `research/rrc-coefficient-contract`

Scope: research only. This note does not add simulator, RTL, vectors, or other project implementation code.

## Executive Recommendation

Use the following contract unless the human team explicitly chooses a different normalization or latency convention:

- Set the symbol period to `T=1` and sample at `sps=2`.
- For `N=8`, use the centered even-length grid `t[n] = (n - (N-1)/2) * T/sps`, for `n=0..7`.
- Evaluate the standard RRC impulse response, including explicit finite-value branches at `t=0` and `t=+/-T/(4*alpha)`.
- Normalize the eight sampled values to discrete unit energy: `sum(h[n]^2) = 1`.
- Store coefficients in increasing time order, from `t=-1.75*T` to `t=+1.75*T`.
- Treat each QPSK real component as the repository's declared value `+/-1.0`. For a 16-bit signed input, use scale `2^14` (`Q2.14`) so both `+1` and `-1` are exact. Use the common `Q2.(W-2)` scale for coefficients as well (refined by #16; at 16 bits this is `Q2.14`).
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

Refinement (#16): the FXP policy contract selects the common `Q2.(W-2)` format
for data and coefficients, so at `W=16` the coefficient integers become
`[179, -1818, 1818, 11295, 11295, 1818, -1818, 179]`. The `Q1.15` values above
remain as the labelled sensitivity experiment in phase E of the FXP sweep.

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
coefficient_scale_16bit: Q2.14
coefficient_scale_sensitivity: Q1.15 (optional phase E)
coefficients_float64: [the eight values listed above]
```

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

## Concepts and FAQ

This section explains the vocabulary and the questions that come up while reading this contract. It sits between Sources and Human Decisions so the terms are clear before the team accepts or changes a decision.

### Q1. What exactly is an RRC, and why research its coefficients?

A root-raised-cosine filter is the square root (in magnitude) of a raised-cosine spectrum. In a matched pair, the transmitter and receiver each apply an RRC; their cascade is a raised-cosine response whose impulse response crosses zero at every symbol instant except its own, giving zero inter-symbol interference. This project implements that pulse as an 8-tap FIR, so its coefficients are the golden data that every later artifact (vectors, FXP model, RTL) must reproduce. Research was needed because standard APIs disagree about length, ordering, delay, and normalization.

### Q2. What is the difference between a symbol period and a sample?

The symbol period `T` is the time between QPSK symbols (`T = 1/Rs`). A sample is one value after oversampling; with 2x oversampling there are two samples per symbol, spaced `T/2`. `CONTEXT.md` uses exactly this distinction: symbols exist before filtering, samples exist after oversampling.

### Q3. What is a centered even-length grid, what alternatives exist, and why choose it?

The grid is `t[n] = (n-(N-1)/2)/sps` for `n=0..7`. With `N=8`, `sps=2`, it gives `+/-0.25T, +/-0.75T, +/-1.25T, +/-1.75T`: symmetric about zero, with no sample at `t=0` and the center falling between the fourth and fifth taps. Alternatives:

- A one-sided (causal) grid `t[n] = n/sps`, which includes `g(0)` and produces an asymmetric truncation of the pulse.
- A standard integer-span API grid, whose length `span*sps+1` is odd (9 taps for `span=4`, `sps=2`) and cannot satisfy the fixed 8-tap requirement.

Centering is chosen because it keeps the truncation symmetric about the symbol center, matches the symmetry of the ideal pulse, and exposes the half-sample delay explicitly.

### Q4. Why is it important to evaluate the RRC limits (singular points)?

The ordinary formula has `0/0` forms at `t=0` and `t=+/-T/(4*alpha)`. Those are removable singularities, so the correct values come from limits (L'Hopital). Even though the eight-tap grid never lands on them, the implementation must branch explicitly: the continuous curve plotted over `[-2,2]` does pass through `t=0` and `t=+/-0.5`, and any future longer filter may sample those points. A naive implementation would produce `NaN`.

### Q5. Why normalize the sampled values to discrete unit energy?

Normalization fixes the amplitude scale of the golden coefficients. Unit energy, `sum(h^2)=1`, is the convention documented by MathWorks and implemented by Sionna (L2/unit power), makes a matched transmit/receive interpretation straightforward, and gives a clean, length-independent contract for SQNR and quantization. The alternative, unity DC gain (`sum(h)=1`), is valid but produces a different vector and must never be mixed with an energy-normalized one.

### Q6. Why store coefficients in increasing time order, and why from `-1.75T` to `+1.75T`?

Increasing index maps directly to increasing physical time, which is also the causal delay order used by `y[m] = sum(h[k]*x[m-k])`. The endpoints come from the grid: `+/-(N-1)/2` samples `= +/-3.5` samples `= +/-1.75T`. The vector is symmetric, so reversing it yields the same numbers, but the convention must still be fixed because it determines the documented delay, FFT bin alignment, vector manifests, and future non-symmetric experiments.

### Q7. What does "treat each QPSK real component as the repository's declared value `+/-1.0`" mean? Why `2^14`, and what are Q2.14 and Q1.15?

It means do not silently normalize the constellation. The repository declares `I,Q in {+1,-1}`, so each component is exactly `+/-1.0`. A signed 16-bit two's-complement word with scale `2^14` (`Q2.14`: two integer bits including the sign, fourteen fractional bits) represents `-1` and `+1` exactly as `-16384` and `+16384`; its range is `[-2, +1.99994]`. Signed `Q1.15` (scale `2^15`) has range `[-1, +0.99997]`, so `+1.0` is not exactly representable and would need saturation. Coefficients use `Q1.15` because normalized coefficients satisfy `abs(h) < 1`, and fifteen fractional bits give finer resolution (`2^-15`) than `Q2.14` (`2^-14`).

`Qm.n` notation: `m` integer bits (sign included) plus `n` fractional bits, `m+n` bits total; the stored integer represents the real value multiplied by `2^n`.

### Q8. Where does the FIR delay come from?

For any symmetric (linear-phase) FIR of length `N`, the transfer function factors as `z^-((N-1)/2)` times a real zero-phase polynomial, so the filter group delay is `(N-1)/2` samples. With `N=8` that is `3.5` samples, or `1.75T` at 2 samples per symbol. The half-integer value comes precisely from the even tap count.

### Q9. What is the RRC alpha, and why is it 0.5?

`alpha` is the roll-off factor of the RRC (`0 < alpha <= 1`). It controls excess bandwidth: the occupied one-sided bandwidth is `(1+alpha)/(2T)` versus the Nyquist minimum `1/(2T)`. `alpha=0.5` gives 50% excess bandwidth, a moderate transition band, and faster tail decay than smaller values; the assignment fixes this value.

### Q10. What does 2x oversampling imply, and what are its advantages and disadvantages?

It means two samples per symbol, with sample spacing `T/2`. Advantages: minimal data rate increase, simple hardware, and enough resolution for a half-symbol-aligned pulse in this project. Disadvantages: eye resolution is coarser than 4x/8x, the half-sample delay becomes explicit in the output grid, and spectral images are closer to the band. The assignment fixes this rate, and the design must handle the half-sample grid rather than assume integer symbol centers.

### Q11. Why 8 coefficients?

Fixed by the assignment. Eight taps span `3.5T` (about `1.75` symbols on each side), a deliberately short FIR: cheap hardware and a good PPA exercise, at the cost of a visibly imperfect stopband.

### Q12. What exactly is the NVIDIA Sionna `RootRaisedCosineFilter`, where does it come from, and why is it relevant?

Sionna is NVIDIA's open-source, GPU-accelerated link-level simulation library for communications. Its `RootRaisedCosineFilter` documents the piecewise RRC formula, both singular-point limits, the span/samples length behavior, and an optional L2/unit-power normalization. It is this document's primary implementation-grade source for the formula and its edge cases.

### Q13. What exactly is the Purdue EE538 square-root raised-cosine reference, and how does it relate to Sionna?

EE538 is a Purdue University course whose notes describe the ideal square-root raised-cosine pulse and stress that its support is infinite. It provides independent academic confirmation of the same ideal pulse Sionna implements. The conclusion "a practical FIR is a time-truncated approximation" means that any finite tap count (8, in this project) can only approximate the ideal infinite response; it is a statement about truncation, not a defect in the formula.

### Q14. What exactly is MathWorks `rcosdesign`, and what does the quoted sentence mean?

`rcosdesign` is MATLAB's standard RRC design function. This contract cites it as:

> MathWorks `rcosdesign` documents an RRC FIR specified by integer symbol span and samples per symbol. Its length is `span*sps+1`, its order is `span*sps`, and its coefficients have unit energy.

That means: the returned tap count is `span*sps+1`, the filter order is `span*sps`, and the coefficients are scaled to unit energy. Because `span*sps+1` is odd for integer spans, the standard API cannot directly produce the even 8-tap filter required here, which is why this contract defines an explicit custom grid.

### Q15. What exactly is GNU Radio's `firdes::root_raised_cosine`, and why is it relevant?

It is the RRC tap generator in GNU Radio, an open-source SDR framework. Its source forces an odd tap count and normalizes the taps by their sum, i.e. unity DC gain. It is relevant as a counterexample showing that "RRC normalization" and tap-count conventions are not universal, so this project must write its choices down explicitly.

### Q16. What exactly is SciPy, and why is it relevant?

SciPy is the Python scientific-computing library. This project uses it only for independent checks and future tooling: `freqz` for the frequency response, `upfirdn` for the upsample-filter-downsample operation, `fftconvolve` for FFT-based linear convolution, and `fft`/`ifft` for transform conventions. It does not define the RRC formula for us.

### Q17. What does the "endpoints are 3.5 symbol periods apart" warning mean?

It means the outermost taps sit at `-1.75T` and `+1.75T`, so the aperture is `3.5T`, not `4T`. A conventional `rcosdesign` with `span=4` and `sps=2` would produce nine taps spanning `+/-2T`. Ours is a custom even-length truncation; do not describe it as a "four-symbol-span, eight-tap" standard filter, because that combination does not exist in the standard integer-span convention.

### Q18. What is exposed in the Raw Values section?

It records the eight values produced directly by the formula before normalization, plus their raw energy and sum. This separates formula correctness from the normalization decision, lets anyone recompute the scale factor `sqrt(sum(raw^2))`, and gives a debugging checkpoint if the normalized vector is ever questioned.

### Q19. Where does the recommended finite-FIR normalization come from?

From this contract: `scale = sqrt(sum(raw[n]^2))` and `h[n] = raw[n]/scale`, so that `sum(h^2)=1`. It is the discrete-L2 normalization chosen to match MathWorks unit energy and Sionna's L2/unit-power normalization.

### Q20. What is the L2 choice? Why does it match the MathWorks unit-energy convention and Sionna's unit-power normalization? How does it differ from unity DC?

L2 normalization means dividing the coefficient vector by its Euclidean (L2) norm. MathWorks documents unit-energy coefficients (`sum(h^2)=1`) and Sionna's `normalize=True` path divides by the L2 norm, so the three agree. Unity DC instead divides by `sum(h)` so the DC gain is exactly 1; it produces a different coefficient vector and a different gain interpretation, and the two must not be mixed within one contract.

### Q21. Why does it say that "the order still matters for the documented delay, FFT bin alignment, vector manifests, and future non-symmetric experiments"?

Because the index convention defines the causal delay mapping, how coefficients are placed for FFT bin alignment, what the vector manifest states, and how future non-symmetric experiments (truncated or deliberately asymmetric filters) are interpreted. Symmetry makes the values palindromic but does not remove the need for a fixed convention.

### Q22. What are linear-phase delay and half-sample delay, and why does an even tap count cause the latter?

A symmetric FIR has a phase response that is linear in frequency, equivalent to a pure delay: the group delay is constant at `(N-1)/2` samples. If `N` is odd that delay is an integer; if `N` is even it is a half-integer. With `N=8` the delay is `3.5` samples `= 1.75T`, so output samples do not land exactly on symbol centers.

### Q23. What is the difference between an unnormalized and a unit-magnitude QPSK constellation? Why is Q2.14 recommended for the unnormalized one instead of Q1.15?

Unnormalized QPSK (`+/-1 +/- j`) has per-component values exactly `+/-1` and total symbol power 2. Unit-magnitude QPSK (`(+/-1 +/- j)/sqrt(2)`) has per-component values `+/-0.707` and total power 1. `Q1.15` cannot represent exactly `+1` (its maximum is `+0.99997`), so using it for the declared `+/-1` components would force saturation or a different interpretation; `Q2.14` represents `+/-1` exactly while still covering the needed range. The repository declares the unnormalized constellation, hence `Q2.14`.

### Q24. Why do coefficients use Q1.15 when the constellation section says not to use it?

The restriction applies to data samples, which include the exact value `1`. Coefficients are normalized to `max(abs(h))=0.689 < 1`, so `Q1.15` covers them with room to spare and gives one extra fractional bit of precision compared with `Q2.14`. Different signals have different dynamic ranges, so their binary-point placement differs.

### Q25. What does "if the output keeps the input's Q2.14 scale, accumulate at the product scale and rescale by Sc only after the full eight-term sum" mean?

Each product `h_int*x_int` carries scale `Sc*Sx = 2^15 * 2^14 = 2^29`. All eight products are summed in that scale, with an accumulator wide enough not to overflow, and only the final sum is divided by `Sc=2^15` to return to the input's `Q2.14` scale. Rescaling once at the end avoids accumulating per-term rounding errors. The rounding mode, actual accumulator width, and saturation policy are decided in the FXP sweep.

### Q26. Why can rounding, saturation, accumulator width, and overflow behavior not be decided now?

Because they depend on measured SQNR behavior and on architecture/PPA trade-offs, not only on the RRC contract. Ticket #16 owns that policy and the T20/T21 sweep chooses the widths; freezing them here without data would be guesswork. They must be frozen before the FXP sweep, not before T10.

### Q27. It says "the eight taps are very short for an ideal RRC approximation". Is it wrong, and should it be changed?

No. It is an expectation-setting statement, not an error: an 8-tap FIR is a coarse truncation of an infinite response, so the stopband and passband will deviate from ideal. The assignment fixes eight coefficients, so the correction is in presentation (plot the finite response and the ideal target separately) rather than changing the formula.

## Human Decisions

The team accepted the decisions below on 2026-09-22, before T10 freezes the simulator contract. Each entry keeps what was chosen, the alternatives that were on the table, why it matters for this project, the research recommendation, and the accepted status.

### D1. Coefficient normalization

- **Status:** accepted 2026-09-22 — discrete unit energy (`sum(h^2)=1`).
- **What is being chosen:** how the eight raw RRC samples are scaled before they become the golden coefficients.
- **Alternatives:** (a) discrete unit energy `h = raw / norm(raw)` — recommended; (b) unity DC gain `h = raw / sum(raw)`, the convention used by GNU Radio; (c) store raw unnormalized samples and normalize elsewhere.
- **Why it matters here:** it fixes the amplitude scale of the golden model, the SQNR reference, the coefficient integer scaling, the matched-filter interpretation, and every generated vector. Changing it later invalidates vectors, tests, and RTL results.
- **Recommendation:** unit energy.
- **Why:** it matches the MathWorks unit-energy convention and Sionna's L2/unit-power normalization, is standard for matched transmit/receive pulse shaping, and gives a scale-independent contract.

### D2. Half-sample delay and grid

- **Status:** accepted 2026-09-22 — keep the centered grid and `D=3.5` samples (`1.75T`), documented in the artifact and manifest.
- **What is being chosen:** whether to keep the centered even-length grid and its `3.5`-sample (`1.75T`) group delay.
- **Alternatives:** (a) keep `D=3.5` — recommended; (b) round the delay to `3` or `4` samples for integer-sample convenience; (c) switch to a 9-tap integer-delay filter, which violates the fixed 8-tap assignment.
- **Why it matters here:** the delay drives the alignment between time and frequency output, the vector manifest fields, the impulse/eye plots, and the FFT block valid window. A mismatch is a silent vector-matching failure.
- **Recommendation:** keep `D=3.5` and document it in the artifact and vector manifest.
- **Why:** it is a mathematical consequence of an even tap count; rounding it changes the filter contract rather than simplifying it.

### D3. Constellation convention

- **Status:** accepted 2026-09-22 — keep the declared unnormalized QPSK `+/-1 +/- j` with `Q2.14` input.
- **What is being chosen:** keep the repository-declared unnormalized QPSK `I,Q in {+1,-1}`, or switch to unit-magnitude `(+/-1 +/- j)/sqrt(2)`.
- **Alternatives:** (a) unnormalized `+/-1` with input scale `Q2.14` — recommended; (b) unit-magnitude with `Q1.15` as the data format; (c) any other declared scale.
- **Why it matters here:** it sets average power, input integer scaling, saturation margins, the SQNR reference, and all generated vectors.
- **Recommendation:** keep the declared `+/-1 +/- j`; record any change as a new ADR-level decision.
- **Why:** the assignment and repository already fix it, and changing it silently would break ADR-0004's data contract.

### D4. FXP numerics freeze

- **Status:** accepted 2026-09-22 — round-to-nearest-even, saturation at explicit narrowing boundaries, wide non-wrapping accumulator, and a single rescale after the full sum; the actual widths are frozen in the T20/T21 sweep.
- **Refinement (#16):** the coefficient format is refined to the common `Q2.(W-2)`; at `W=16` the coefficient integers are `[179, -1818, 1818, 11295, 11295, 1818, -1818, 179]`. See `docs/contracts/fxp-policy-16.md`.
- **What is being chosen:** rounding mode, saturation versus wrap, coefficient/input/output `Q` formats, accumulator width, and output rescaling policy.
- **Alternatives:** round-to-nearest-even versus truncation; saturate versus wrap on narrowing; wide non-wrapping accumulator versus minimal-width accumulator; single rescale after the full sum versus per-term rescale.
- **Why it matters here:** these choices determine whether `SQNR >= 40 dB` is met, whether overflow is possible, and how much area and timing the arithmetic costs. They are the core of ticket #16 and of the T20/T21 sweep.
- **Recommendation:** round-to-nearest-even, saturation at explicit narrowing boundaries, wide non-wrapping accumulator, and a single rescale after the full sum; freeze the actual widths after the sweep.
- **Why:** it preserves precision at low cost and keeps the sweep interpretable. This ticket already fixes data `Q2.14` and coefficient `Q1.15` but deliberately does not fix accumulator or output formats.

### D5. Canonical artifact storage

- **Status:** accepted 2026-09-22 — store both float64 (golden) and quantized integers (derived).
- **What is being chosen:** what the generated RRC artifact stores: full float64 decimals, quantized integers, or both.
- **Alternatives:** float only; integer only; both — recommended.
- **Why it matters here:** the artifact is the golden source for vectors and RTL coefficient tables. Divergence between the float and integer representations would produce false vector mismatches.
- **Recommendation:** store both, with float as golden and integers as derived data.
- **Why:** Python tests can verify exact reproduction while RTL consumes frozen integers.

### D6. Frequency block convention

- **Status:** accepted 2026-09-22 — deferred to ticket #14 under the professor gate below.
- **What is being chosen:** FFT block size, overlap convention, padding, and valid output alignment.
- **Alternatives:** overlap-save with 50% overlap and FFT16 (the professor's baseline) versus overlap-add; different first/last-block edge handling.
- **Why it matters here:** it controls the equality between the frequency-domain output and the time-domain golden, and the valid comparison window. This ticket does not resolve it because it belongs to ticket #14.
- **Recommendation:** defer to the #14 research result and then freeze it, keeping `D=3.5` visible in the manifest.
- **Professor gate:** the #14 research may compare overlap-save, overlap-add, or other alternatives, but any deviation from the professor's stated baseline (overlap-save with 50% overlap, 16-point FFT, explicit IFFT) must be proposed to the professor and approved before adoption, even if the alternative looks technically better.
- **Why:** it prevents mixing partially decided conventions across the two domains, and it keeps the assignment owner in the loop for changes to the reference design.

### D7. Eye and spectrum presentation

- **Status:** accepted 2026-09-22 — natural half-sample grid for verification evidence; symbol-center interpolation only in labelled slides; nine-tap reference optional.
- **What is being chosen:** how to present the natural half-sample output grid.
- **Alternatives:** (a) plot the natural half-sample grid — recommended for verification; (b) interpolate to symbol centers for presentation only; (c) add a nine-tap reference filter for contrast.
- **Why it matters here:** symbol-center interpolation can hide the real half-sample alignment and mislead the FFT alignment work. Plots are evidence, not decoration.
- **Recommendation:** keep the natural grid for all verification evidence; use symbol-center interpolation only in slides, clearly labelled; the nine-tap reference is optional.
- **Why:** it preserves reproducible evidence while still allowing readable presentations.

## Decision Rationale

### D1 — Normalization: discrete unit energy

- **Alternatives:** unity DC gain (the GNU Radio convention) or raw unnormalized samples.
- **Why they were rejected:** unity DC optimizes DC gain rather than matched-filter energy and produces a different vector that is incompatible with the MathWorks and Sionna conventions recorded here; raw samples leave an arbitrary scale that would make SQNR and FXP scaling incomparable.
- **Why this was chosen:** it matches the MathWorks unit-energy convention and Sionna's L2/unit-power normalization, is the standard matched transmit/receive convention, and gives a scale-independent contract.

### D2 — Half-sample delay and grid: centered even grid with `D=3.5`

- **Alternatives:** round the delay to `3` or `4` samples; switch to a nine-tap odd-length filter.
- **Why they were rejected:** rounding introduces a systematic alignment error against the ideal pulse and changes the documented delay; a nine-tap filter violates the fixed eight-coefficient assignment.
- **Why this was chosen:** the even tap count mathematically forces the half-sample group delay, and keeping the centered grid preserves symmetry and exact alignment with the ideal RRC.

### D3 — Constellation: unnormalized `+/-1 +/- j` with `Q2.14`

- **Alternatives:** unit-magnitude `(+/-1 +/- j)/sqrt(2)` with `Q1.15`; any other declared scale.
- **Why they were rejected:** the unit-magnitude constellation changes the declared average power and would require re-deriving every vector and the SQNR reference; other scales silently reinterpret the declared data.
- **Why this was chosen:** the assignment and repository declare `+/-1 +/- j`, and `Q2.14` represents both `+1` and `-1` exactly.

### D4 — FXP numerics: RNE, saturation, wide accumulator, single rescale

- **Alternatives:** truncation instead of RNE; wrap instead of saturation; a minimal-width accumulator; per-term rescaling.
- **Why they were rejected:** truncation adds a DC bias; wrap can hide overflow and corrupt vectors; a minimal accumulator risks internal overflow; per-term rescaling accumulates rounding noise.
- **Why this was chosen:** the chosen policy preserves precision at low cost, keeps overflow detectable, and makes the T20/T21 width sweep interpretable; the actual widths are frozen from measured data.

### D5 — Artifact storage: float golden plus derived integers

- **Alternatives:** float only, or integers only.
- **Why they were rejected:** float-only forces the RTL flow to quantize on the fly with a second, divergent implementation; integer-only loses the golden reference needed for regeneration and auditing.
- **Why this was chosen:** the float64 values stay the golden source and the integers are derived data consumed by RTL, both in one artifact so they cannot diverge.

### D6 — Frequency block convention: deferred to #14 under the professor gate

- **Alternatives:** choose canonical OLS hop 9 or OLA immediately.
- **Why they were rejected:** both alternatives deviate from the professor's stated baseline and require his approval; deciding them here would also mix a partially decided convention into the RRC contract.
- **Why this was chosen:** deferring keeps a single decision owner (#14), which later accepted the forced-50% baseline and documented hop 9 as the alternative under the professor gate.

### D7 — Eye and spectrum presentation: natural half-sample grid

- **Alternatives:** interpolate to symbol centers for all evidence; compare against a nine-tap reference filter.
- **Why they were rejected:** interpolated evidence compares derived values rather than implementation output and can hide a one-sample alignment error; the nine-tap reference is a different filter and can confuse the contract.
- **Why this was chosen:** the natural grid is exactly what the golden and RTL produce; interpolation remains a clearly labelled slide-only view, and the nine-tap comparison stays optional context.

## Independent Calculation Evidence

The numeric values in this note were independently calculated with CPython `3.12.3` using the displayed formula, `T=1`, `alpha=0.5`, `sps=2`, `N=8`, absolute-time evaluation for symmetry, and float64 arithmetic. No project source file was modified and no project implementation was run.
