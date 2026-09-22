# Frequency-Domain Block Contract Research

Research ticket: [#14](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/14)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-21

Updated: 2026-09-22

Branch: `research/frequency-block-contract`

Scope: research only; no simulator or RTL implementation is included.

## Recommendation

Keep the professor's proposed architecture, but make the non-canonical part
explicit:

- Filter length `M = 8`.
- FFT/IFFT length `N = 16`.
- Use complex `FFT -> pointwise complex multiply -> explicit IFFT`.
- Use a 50% frame overlap, so the hop is `H = 16 - 8 = 8` samples.
- Use the fixed-phase OLS frame
  `frame_b[r] = x[8b - 8 + r]`, `0 <= r < 16`.
- Initialize the eight pre-frame positions with zero. There is no steady-state
  zero padding in OLS.
- Discard `z_b[0:8]` from each IFFT and emit `z_b[8:16]` as output samples
  `y[8b:8b+8]`.

The first seven discarded values are mathematically required because they are
time-alias corrupted. The eighth is an already valid sample at the preceding
output position; it is discarded to make the forced 8-sample hop produce
exactly eight new samples with no duplicate. This is a project scheduling
choice, not a property of canonical OLS.

The mathematically minimal OLS contract for `M=8`, `N=16` is instead:

```text
valid outputs per frame = N - M + 1 = 9
required input overlap  = M - 1     = 7
hop                     = 9 samples
```

Therefore, “50% overlap” is not the canonical OLS overlap for this filter and
FFT size. The proposed baseline is valid only after the extra one-sample
discard/output policy above is written into the contract.

## Facts and Choices

| Item | Mathematically required or source-backed fact | Project choice to record |
| --- | --- | --- |
| FIR length | `M=8`; a causal FIR has `M-1=7` samples of memory. | None; fixed by the assignment. |
| Canonical OLS hop | `R=N-M+1=9`; the input overlap is `M-1=7`. | Whether to use this efficient canonical contract or force `H=8`. |
| Forced 50% OLS hop | 50% overlap of 16-sample frames means `N-H=8`, hence `H=8`. | Keep `H=8` for the professor's baseline, with one extra saved sample and one extra discarded valid output. |
| OLS discard | The first `M-1=7` IFFT outputs are invalid for a causal FIR. | Discard eight positions in the forced-50% schedule: seven aliases plus one duplicate/pre-boundary output. |
| OLA block | Input blocks are adjacent, not input-overlapped. Each block is zero padded so `N >= H+M-1`; IFFT tails are added. | Use `H=8` for a like-for-like 8-sample cadence, or `H=9` for the maximal block that exactly fills `N=16`. |
| Initial padding | Causal OLS needs at least seven leading zeros. | The fixed-phase `H=8` contract uses eight leading zeros to align each frame as eight history plus eight new samples. |
| Finite-frame ending | Samples outside a finite input are zero for a causal finite convolution. | Process enough final zero-padded blocks to select either the full output or the agreed valid output window. |
| Block latency | A block method waits for a frame/hop of input before producing a block; FFT/IFFT circuit pipeline cycles are additional. | Report `H=8` sample slots for the forced-50% schedule, separately from RTL cycle latency. |
| FFT convention | The DFT has a defined bin order and normalization; with NumPy's default, the forward transform is unscaled and the inverse has `1/N`. | Match the RTL FFT scaling exactly, with no extra `1/16` in the Python baseline if using the NumPy convention. |
| Complex representation | QPSK baseband data are complex, so the general complex DFT has 16 complex bins. | External vector records use `{Q[15:0], I[15:0]}` per ADR-0004; define `I=real`, `Q=imaginary` and retain this order internally. |
| Output alignment | For a causal convolution, output index `n` is `sum(h[k] * x[n-k])`; the block method must select the corresponding IFFT indices. | Compare frequency and time models at the same absolute sample indices; do not apply an unexplained one-sample or FFT-size shift. |

## OLS Derivation

Let `x[n]=0` outside a finite input and define the time-domain reference as

```text
y[n] = sum(k=0..7) h[k] * x[n-k]
```

Let `h16` be `h[0:8]` followed by eight zeros. For each block, compute

```text
z_b = IFFT16(FFT16(frame_b) * FFT16(h16))
```

where the multiplication is complex and elementwise.

### Canonical OLS

For the source-backed OLS construction, the frame starts at
`s_b = 9b - 7`:

```text
frame_b[r] = x[9b - 7 + r], 0 <= r < 16
```

The first seven IFFT positions are discarded. Positions `r=7..15` are the
nine alias-free outputs and align as

```text
z_b[7+i] = y[9b+i], 0 <= i < 9
```

The first block uses `x[-7:-1]=0`, followed by `x[0:9]`. Consecutive frames
share seven samples and introduce nine new input samples. This is the most
efficient unpartitioned OLS contract for `N=16`, `M=8`.

### Forced 50% OLS

For the requested 50% frame overlap, use `H=8` and start frame `b` at
`s_b = 8b - 8`:

```text
frame_b[r] = x[8b - 8 + r], 0 <= r < 16
```

Thus the frame contains eight saved/history samples and eight current samples:

```text
frame_b = [x[8b-8], ..., x[8b-1], x[8b], ..., x[8b+7]]
```

The alias-free region begins at `r=7`, but `r=7` maps to `y[8b-1]`. For
`b>0` that output was emitted by the preceding block, and for `b=0` it is the
pre-input sample `y[-1]`. Therefore the exact output selection is:

```text
discard z_b[0:8]       # z[0:7] alias/pre-boundary or duplicate
emit    z_b[8:16]
```

The selected samples satisfy

```text
z_b[8+i] = y[8b+i], 0 <= i < 8
```

This contract has exactly 8-sample frame overlap, exactly 8 new output
samples per block, no output duplication, and no lookahead beyond the current
8-sample input block. Its first frame is eight zeros followed by `x[0:8]`.

An equally valid but less convenient phase uses seven history samples and
keeps the first eight of the nine valid outputs. That phase needs one extra
lookahead input in each frame and drops the final valid output. The
eight-history phase above is recommended because it has a simple streaming
interface: eight old samples plus eight new samples per block.

## OLA Comparison

Overlap-add partitions the input into adjacent, non-overlapping blocks. For a
block of `H` input samples, form

```text
u_b = [x[bH], ..., x[bH+H-1], 0, ..., 0]  # N-H zeros
v_b = IFFT16(FFT16(u_b) * FFT16(h16))
```

The nonzero linear-convolution result has `H+M-1` samples. Place `v_b` at
output offset `bH` and add the tail that overlaps the next block.

Two useful `N=16`, `M=8` OLA choices are:

| OLA choice | Input samples/block | Zero padding in input frame | Nonzero convolution length | Hop | Tail added to next block |
| --- | ---: | ---: | ---: | ---: | ---: |
| Maximal `N`-filling block | 9 | 7 | 16 | 9 | 7 |
| Same 8-sample cadence as proposed OLS | 8 | 8 | 15 | 8 | 7 |

The second row is valid and convenient for comparison, but its input blocks
are not 50% overlapped. Its seven-sample overlap is in the output tails. OLA
requires zero padding and an output accumulation buffer; OLS avoids those
operations but reuses overlapping input samples and discards the corrupted
prefix. For this very short 8-tap filter, neither method has an asymptotic
advantage; the project should measure the actual RTL/PPA cost rather than
assume that frequency-domain filtering is cheaper.

## Padding, Ending, and Latency

### Padding

- **Recommended forced-50% OLS start:** `x[-8:-1] = 0`; the first frame is
  `[0,0,0,0,0,0,0,0,x[0],...,x[7]]`.
- **Canonical OLS start:** `x[-7:-1] = 0`; the first frame contains seven zeros
  and nine data samples `x[0:9]`.
- **Steady-state OLS:** do not append zeros to each frame; use the saved
  history and incoming samples.
- **Finite OLS end:** append zero input samples as needed so that the emitted
  blocks cover the desired causal tail through `S+M-2` for an input of length
  `S`. Then trim the result to that exact output length.
- **OLA:** append `N-H` zeros to every input block before its FFT. The final
  partial input block is zero-filled to `H`, and its IFFT tail is still added.

### Block latency

There are three different quantities that should not be conflated:

1. **Block cadence:** the recommended forced-50% OLS accepts eight new samples
   per block and emits eight aligned samples after that block is processed.
2. **Sample timestamps:** with zero-based indexing, the first block output
   `y[0:8]` becomes available after `x[7]` is received, so the first output has
   a seven-sample timestamp difference but consumes eight sample slots. A
   later block `b` emits `y[8b:8b+8]` after `x[8b+7]` is received.
3. **RTL implementation latency:** FFT, multiplication, IFFT, buffering, and
   handshake pipeline cycles are implementation-specific and must be measured
   in RTL. They do not change the mathematical sample-index alignment.

For canonical OLS, the corresponding block cadence is nine samples and the
first frame produces nine outputs after its nine incoming data samples. The
common documentation description of OLS/OLA latency as `N-M+1` refers to this
canonical valid-output/partition length, not to an arbitrary forced hop.

## Complex FFT and Packing Contract

The input is complex QPSK baseband, so use a full complex FFT and IFFT:

```text
X[k] = FFT16(x_block)[k]
H[k] = FFT16(h16)[k]
Y[k] = X[k] * H[k]       # complex multiply for every k=0..15
z    = IFFT16(Y)
```

Do not use real-input `rfft` packing for the QPSK stream. Even though the RRC
tap sequence is real-valued, the QPSK input is complex and the filtered output
is complex. Keep all 16 complex bins in the baseline. The bins use standard
DFT order: DC at bin 0, positive frequencies in increasing bin order, and
negative frequencies at the upper bins.

For NumPy-compatible float reference code, the default convention is an
unscaled forward FFT and an inverse FFT scaled by `1/N`. Therefore,
`ifft(fft(a))` recovers `a` within numerical accuracy and the product above
must not receive a second `1/16` scale factor. If the RTL FFT core uses a
different per-stage scaling convention, record that convention and compensate
exactly once.

The repository's external vector contract is one 32-bit complex record
`{Q[15:0], I[15:0]}`. Use `I=real` and `Q=imaginary` consistently when packing
and unpacking. The field order is a project interface choice, not a theorem of
OLS/OLA; coefficient/data width, rounding, saturation, and internal FFT
scaling remain part of the later fixed-point contract.

## Alignment and Valid Window

The time-domain and frequency-domain models must use the same causal reference:

```text
y_time[n] = sum(k=0..7) h[k] * x[n-k]
```

For the recommended forced-50% OLS, compare `z_b[8:16]` directly against
`y_time[8b:8b+8]`. There is no model-level shift. For the complete finite input
of length `S`, the full causal output has length `S+7` and indices `0..S+6`.

The project must separately choose its emitted vector window:

- **Full causal window:** compare and emit `y[0:S+7]`, including the filter
  tail.
- **Input-length window:** compare and emit `y[0:S]` if the external vector
  format must have one output per input sample.

Either is valid, but both domains must use the same absolute indices. Do not
use a library `same` mode without documenting its centering convention, and do
not compare implementation-only zero padding. This is consistent with the
repository's valid-output-window and float-equality contracts in ADR-0005.

## Numerical Equivalence Check

Use a short deterministic complex vector before using the RRC/QPSK stimulus:

1. Pick `S=32` complex input samples and exactly eight complex taps. Compute
   the reference with direct full convolution, for example
   `y_ref = np.convolve(x, h, mode="full")`.
2. Run the recommended OLS loop with `N=16`, `H=8`, frame start
   `8b-8`, `h16 = [h, zeros(8)]`, `z = ifft(fft(frame) * fft(h16))`, and
   select `z[8:16]`.
3. Run OLA with `H=8`, eight input zeros to make each 16-point frame, add each
   IFFT frame at offset `8b`, and trim to `len(y_ref)`.
4. Assert both outputs equal `y_ref` using the repository tolerance
   `rtol=1e-10`, `atol=1e-12`. Also assert that every output index is produced
   exactly once by the OLS selector.
5. Run the canonical OLS variant (`H=9`, seven-sample overlap, discard
   `z[0:7]`) as a separate check. This catches accidental treatment of 50%
   overlap as the mathematical OLS rule.
6. Add a unit impulse at `x[0]` and verify the first eight emitted samples are
   exactly the tap sequence in order. This catches the common one-sample
   alignment error.
7. Add a packing round-trip test for signed I/Q values, including negative
   values and the extrema of the selected fixed-point width.

An independent one-off float check using `S=32`, deterministic complex `x` and
`h`, and full output length `39` produced these maximum absolute errors:

```text
forced-50% OLS, H=8:  9.930136612989092e-16
OLA, H=8:              1.7841460175902718e-15
canonical OLS, H=9:    1.3334236103572998e-15
```

These are numerical-equivalence evidence for the indexing contract, not a
replacement for the project's eventual pytest test and RRC/QPSK vectors.

## Source-Backed Findings

- Julius O. Smith III's Stanford CCRMA OLS notes state that causal OLS has
  `L-1` invalid leading IFFT samples, needs at least `L-1` leading zeros, and
  uses hop `R=N-L+1`; they also explain that the input blocks overlap by
  `L-1`. [Overlap-Save Method](https://ccrma.stanford.edu/~jos/OLA/Overlap_Save_Method.html)
- The same Stanford material describes OLA as partitioning the input into
  adjacent frames, zero padding, FFT/filter/IFFT processing, and summing the
  overlapping output frames. [FFT Convolution Across Frames](https://ccrma.stanford.edu/~jos/OLA/FFT_Convolution_Across_Frames.html)
- MathWorks' first-party algorithm documentation independently states that
  OLA uses non-overlapping input blocks and adds the final `M-1` samples into
  the next block, while OLS uses overlapping input blocks and discards the
  first `M-1` circular-convolution samples. [Overlap-Add/Save](https://www.mathworks.com/help/dsp/ug/overlap-add-save.html)
- MathWorks' Frequency-Domain FIR Filter reference specifies OLS input
  overlap as `NumLen-1` and OLA input block length as `FFTLen-NumLen+1`.
  [Frequency-Domain FIR Filter](https://www.mathworks.com/help/dsp/ref/frequencydomainfirfilter.html)
- NumPy documents the DFT definition, standard bin order, complex input, and
  default forward/inverse normalization. [DFT reference](https://numpy.org/doc/stable/reference/routines.fft.html),
  [`fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html),
  and [`ifft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.ifft.html)
- SciPy's first-party references define `fftconvolve` as FFT-based full
  linear convolution and identify `oaconvolve` as overlap-add convolution;
  they also document full output length `N+M-1`. [`fftconvolve`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.fftconvolve.html)
  and [`oaconvolve`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.oaconvolve.html)
- Repository contract: [CONTEXT.md](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/CONTEXT.md),
  [ADR-0004 packed external vectors](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0004-packed-external-vectors.md),
  [ADR-0005 common SQNR contract](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0005-common-sqnr-contract.md),
  and [the F1 plan](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/plan-gantt.md#f1--floating-point-simulator-golden).

All web sources above were checked on 2026-09-21. The source-backed facts are
separated from project-specific choices in the table above; the latter should
be confirmed by the team before implementation.

## Concepts and FAQ

This section explains the vocabulary used by the contract, in the order the
questions usually come up while reading it.

### Q1. What is the difference between the FFT and the IFFT, and why should they be twice as wide as the filter?

The FFT analyzes a time block into frequency bins; the IFFT synthesizes a time
block back from frequency bins. They are the same transform with conjugated
phase factors and reciprocal normalization. With NumPy defaults, the forward
transform is unscaled and the inverse applies `1/N`, so `ifft(fft(a))` returns
`a` within numerical accuracy.

"Twice as wide as the filter" here means `N=16` against `M=8`. It is not a
universal law: a length-`N` circular convolution represents the linear
convolution of a hop of `H` samples with `M` taps without wrap only when
`N >= H + M - 1`. For the 8-sample hop and 8-tap filter used here,
`H + M - 1 = 15`, so 16 is the smallest power-of-two FFT that fits. The width
beyond the filter is what leaves room for the filter memory and the valid
output samples.

### Q2. What is circular convolution, how does it relate to this project, and what is the role of zero padding?

Multiplying `FFT(x)` by `FFT(h)` and applying an IFFT computes a circular
convolution: output index `n` wraps around modulo `N`, so the tail of the
linear convolution reappears at the beginning of the block. The time-domain
reference for this project is the linear, causal FIR
`y[n] = sum(h[k] * x[n-k])`, so the wrapped part must be prevented or
discarded.

Zero padding is the standard way to make circular convolution behave like
linear convolution: pad the input block (OLA) or the filter (`h16` here) so
the full linear result fits into `N` samples. In OLS, the input frames are not
zero-padded in steady state; the frame is already full of real history, and
the `M-1` wrapped samples are discarded because they are known to be
corrupted. Zero padding then appears only at the start (initial history) and
at the finite end (flushing the tail).

### Q3. What is the `complex FFT -> pointwise complex multiply -> explicit IFFT` flow?

It is the frequency-domain filtering pipeline: take a 16-sample block, compute
its 16 complex frequency bins, multiply them bin by bin with the 16 bins of
the zero-padded filter (`H[k] = FFT16(h16)`), and transform the product back
to time with an inverse FFT. "Explicit IFFT" means the design performs an
actual inverse transform rather than using a real-input shortcut or
precomputing a time-domain result. The QPSK stream is complex, so all 16 bins
are kept; the fact that the RRC taps are real does not make the data real.

### Q4. What does 50% frame overlap mean, what is the hop, and how does the overlap set the hop?

The frame length is `N=16`. The overlap is how many samples a frame shares
with the previous one. With 50% overlap, 8 of the 16 samples are reused, so
each new frame contributes `H = N - overlap = 16 - 8 = 8` new input samples;
that count is the hop. The hop therefore follows directly from the chosen
overlap. Canonical OLS instead uses the mathematically required overlap
`M-1 = 7`, which gives the hop `N - (M-1) = 9`.

### Q5. What is a fixed-phase OLS frame?

It is the alignment convention that anchors every frame at the same offset
relative to the input stream. For the forced-50% schedule, frame `b` is

```text
frame_b[r] = x[8b - 8 + r], 0 <= r < 16
```

so it always contains eight history samples followed by eight new samples.
"Fixed-phase" emphasizes that the frame grid does not slide or recenter: the
same eight-plus-eight structure repeats every block, which makes the streaming
interface simple. The alternative seven-history/nine-new phase is
mathematically valid but needs one extra lookahead sample and drops the last
valid output.

### Q6. What are the pre-frame positions, why are they initialized to zero, and why is there "no steady-state zero padding" in OLS?

The pre-frame positions are the inputs before the first real sample,
`x[-8:-1]`. A causal FIR sees zero outside the support of its input, so those
positions are zero; that is what lets the first frame produce the correct
causal output. In steady state, OLS reuses the previous frame's samples as
history instead of padding: each new frame is filled with real saved samples
plus real new samples. Zero padding exists only at the two boundaries: the
initial history and the final blocks needed to flush the filter tail. OLA is
different: it pads every input block with `N-H` zeros before the FFT.

### Q7. Why are IFFT values discarded, and what does "time-alias corrupted" mean?

A length-16 circular convolution wraps the linear-convolution tail back to the
start of the block. For an `M=8` filter, the first `M-1 = 7` samples of the
IFFT result are exactly that wrapped contribution added to the true values,
so they are corrupted by time-domain aliasing and cannot be used. In the
forced-50% schedule the eighth sample (index 7) is not corrupted: it is the
valid output `y[8b-1]` that the previous block already emitted, or the
pre-input sample `y[-1]` for `b=0`, and it is discarded only to avoid
duplication. Discarding `z[0:8]` leaves the eight alias-free samples
`z[8:16] = y[8b:8b+8]`.

### Q8. Why does the contract say that 50% overlap is not canonical, and what would the canonical application be?

Canonical OLS for `M=8`, `N=16` uses hop 9 and 7-sample overlap: seven leading
IFFT samples are discarded and nine valid outputs are kept. 50% overlap means
hop 8, so one valid output per frame has to be dropped to keep the cadence,
and the discard/output policy must be written down for the schedule to be well
defined. The professor's baseline is still valid as an engineering choice; the
point of the sentence is that it is a project scheduling decision, not the
textbook OLS rule, and the contract must state it explicitly.

### Q9. Why is the efficient canonical contract `R = N - M + 1 = 9` with input overlap `M-1 = 7`?

Because the first `M-1` samples of every length-`N` circular convolution are
corrupted, at most `N - (M-1) = N - M + 1` samples per frame are usable. To
consume exactly the usable samples with no gaps, the next frame must start
`N - M + 1` samples later; that is the hop `R = 9`. Its first `M-1 = 7`
samples are the last seven samples of the previous frame, which is where the
input overlap comes from. This partition maximizes the number of valid outputs
per FFT, so it is the efficient canonical OLS contract.

### Q10. What are OLS and OLA?

Overlap-save (OLS) splits the input into frames that overlap by `M-1` samples,
transforms each frame, multiplies by the filter's frequency response,
inverse-transforms, discards the first `M-1` corrupted samples, and
concatenates the survivors. Overlap-add (OLA) splits the input into adjacent,
non-overlapping blocks, zero-pads each block to length `N`, filters it in the
frequency domain, and adds the overlapping output tails into an accumulator.
Both compute the same linear convolution; OLS avoids output addition but
reuses input overlap, while OLA avoids input overlap but needs output
accumulation and zero padding.

## Human Decisions

The team must record the choices below. Only D1 blocks locking this contract;
D2 and D3 are resolved naturally by later tickets.

### D1. Which frequency baseline to lock

- **Status:** accepted 2026-09-22 — professor's forced-50% baseline with the explicit schedule.
- **What is being chosen:** the OLS schedule used by the frequency-domain golden: the professor's forced-50% schedule (`N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`) or the canonical OLS contract (`H=9`, overlap 7, discard `z[0:7]`, emit 9 samples).
- **Alternatives:** (a) professor's forced 50% with the explicit schedule — recommended; (b) canonical OLS `H=9`; (c) OLA with an 8-sample cadence.
- **Why it matters here:** the schedule fixes the frame grid, the discard/output mapping, the block cadence, and the alignment against the time-domain golden. It is also the contract the RTL implementation must follow.
- **Recommendation:** adopt the professor's baseline and write the forced-50% schedule explicitly, keeping canonical OLS `H=9` documented as the mathematical alternative. Any proposal to change the baseline goes to the professor first (professor gate).
- **Why:** it respects the assignment owner's architecture, gives a simple 8-sample streaming cadence, and the numerical checks in this document already validate the alignment to about `1e-15`.

### D2. Emitted vector window

- **Status:** deferred to ticket #15.
- **What is being chosen:** whether the emitted vectors use the full causal window `y[0:S+7]` (including the filter tail) or the input-length window `y[0:S]`.
- **Alternatives:** full causal; input-length; any other documented trim.
- **Why it matters here:** both domains must compare on the same absolute indices and the vector manifest must declare the window; a silent trim would produce vector-matching failures.
- **Recommendation:** let ticket #15 (stimulus, seed, and valid output window) decide, and record the result in both domain contracts.
- **Why:** it is the same decision for time and frequency, so it belongs with the stimulus contract rather than here.

### D3. FFT/IFFT scaling convention

- **Status:** deferred to the FXP/RTL phases.
- **What is being chosen:** the numeric scaling of the forward and inverse transforms, both in the Python golden and in the RTL FFT core.
- **Alternatives:** NumPy default (forward unscaled, inverse `1/N`) — recommended for the float golden; a per-stage scaled RTL core; any documented equivalent.
- **Why it matters here:** a duplicated or missing `1/N` changes the output scale and breaks vector matching; it must be recorded once and compensated exactly once.
- **Recommendation:** use the NumPy default in the float golden and freeze the RTL core convention when the FFT core is selected in the FXP/RTL phases.
- **Why:** it keeps the golden simple and makes the compensation point explicit.
