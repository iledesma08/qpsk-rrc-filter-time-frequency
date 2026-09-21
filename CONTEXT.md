# QPSK + RRC Filters

RRC filter project for QPSK in two domains: time and frequency.

## Language

**QPSK**:
Complex 2-bit symbols (±1 ± j) at symbol rate Rs.
_Avoid_: 4-QAM (this project says QPSK)

**Symbol**:
Complex QPSK value before filtering.
_Avoid_: sample (a sample is post-oversampling)

**2x oversampling**:
Each symbol produces 2 samples (one per half symbol period).
_Avoid_: generic upsampling, interpolation

**RRC (root-raised-cosine)**:
Root-raised-cosine pulse-shaping filter, 50% roll-off (α = 0.5).
_Avoid_: RC, plain raised-cosine

**50% roll-off**:
RRC factor α = 0.5. Fixed by the assignment, not a free parameter.
_Avoid_: variable alpha, beta

**Coefficient**:
One of the 8 taps of the discrete RRC filter.
_Avoid_: weight, tap as the primary noun (tap is fine informally)

**Time-domain filter**:
Direct sample × coefficient convolution in the time domain.
_Avoid_: temporal FIR, time-domain filter misspellings

**Frequency-domain filter**:
Filtering via FFT → response multiply → IFFT (overlap-add/save).
_Avoid_: frequential filter, FFT filter

**Floating-point golden**:
Python float64 simulator defining the correctness reference.
_Avoid_: ideal model, floating reference

**FXP (fixed point)**:
Quantization of coefficients and data to N bits with SQNR ≥ 40 dB.
_Avoid_: generic fixed point without SQNR, intN

**SQNR**:
Signal-to-quantization-noise ratio in dB between float and fxp outputs.
_Avoid_: SNR, SNQR

**Vector matching**:
Sample-by-sample RTL vs golden-vector comparison from `sim/vectors/`.
_Avoid_: matching test, golden test

**Serial version**:
RTL processing one sample per cycle (or one shared MAC).
_Avoid_: slow version, simple version

**Optimized version**:
RTL improving one PPA axis (unfolded, pipeline, systolic, folded, or mixed).
_Avoid_: fast version, final version

**PPA**:
Performance-time, Power, and Area axes. Grading rewards the best trade-off, not a single axis.
_Avoid_: performance alone, generic optimization

**Unfolded / parallel**:
Hardware replication to process N samples in parallel.
_Avoid_: bare parallel (ambiguous with pipeline)

**Pipeline**:
Critical-path cuts with registers to raise fmax.
_Avoid_: generic segmentation

**Systolic**:
PE array with rhythmic data/coefficient flow.
_Avoid_: untranslated jargon in slides

**Folded**:
Time reuse of one operator to save area at the cost of throughput.
_Avoid_: plegada, shared

**Slides**:
Final presentation contrasting time vs frequency + PPA + lessons learned.
_Avoid_: filminas, ppt, defense

**Gantt**:
Schedule with tasks, dependencies, and the 4-member split.
_Avoid_: roadmap, informal timeline
