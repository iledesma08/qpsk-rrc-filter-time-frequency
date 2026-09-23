# Link AWGN Annex Contract (optional F5 analysis)

Decision ticket: [#35](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/35)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-23

Branch: `docs/35-link-awgn-annex`

Scope: Python-only analysis annex. No RTL, vector, testbench, stimulus, or
DoD changes. This contract is dormant until and unless the annex is
implemented; the project closes without it.

**Status:** PROPOSED — pending team acceptance. Nothing below is accepted
until the team records acceptance following the integration-branch flow.

## Proposed Decisions

The following are proposed (not yet accepted):

- **D1 — Analysis-only boundary:** the annex is a `sim/python/` script (for
  example `link_awgn.py`) plus plots. It MUST NOT modify `sim/vectors/`,
  any RTL source, any testbench, or the stimulus/FXP/streaming contracts
  (#13–#19), and it MUST NOT become a DoD of any phase.
- **D2 — Chain:** bits → Gray mapper (the #15 mapping, `Es = 2`) → TX
  shaping with the same 8-tap RRC from #13 → complex AWGN at a declared
  `Es/N0` → RX filtering with the local float golden as the matched filter
  → symbol sampling → minimum-distance slicer → BER count. The TX/RX
  matched assumption (same RRC both ends) is documented; any deliberate
  mismatch is declared, never silent.
- **D3 — Noise model:** circular complex AWGN with total variance `N0`,
  i.e. `N0/2` per I/Q component, where `N0 = Es / (Es/N0)_lin` with the
  contractual `Es = 2` (`qpsk-stimulus-15.md` Signal Model). The PRNG stream
  uses a fixed documented seed distinct from the stimulus seed (proposed
  `numpy.random.default_rng(2035)`) so link runs can never be confused with
  contractual vectors.
- **D4 — Symbol timing:** pulse centers sit at `2k + 3.5` samples (#15 D7),
  so the slicing instant requires interpolation. Interpolation here is part
  of the analysis model and MUST be labelled as such; it is never presented
  as implementation output.
- **D5 — Statistical significance:** each `Es/N0` point MUST accumulate at
  least 100 bit errors (or document a justified equivalent), with enough
  transmitted bits to support the claimed BER. The 1024-symbol canonical
  frame is explicitly insufficient for BER and MUST NOT be reused for it;
  link runs use their own long frames, separate from the canonical SQNR
  frame.
- **D6 — Theory reference:** Gray-coded QPSK
  `BER_theory = Q(sqrt(2*Eb/N0)) = Q(sqrt(Es/N0))`, consistent with `Es = 2`
  (`Es = 2*Eb` for QPSK). EVM, when plotted, follows the #18 definition
  (RMS vector error versus the float golden output).
- **D7 — Deliverables:** BER-versus-theory curve plus constellation plots
  for `docs/slides/` material. Suggested (non-normative) sweep:
  `Es/N0 = {0, 2, 4, 6, 8, 10}` dB.

## Decision Rationale

### D1 — Analysis-only boundary

- **Alternatives:** let the annex drive RTL vectors; make BER a phase DoD.
- **Why they are rejected:** AWGN in vectors would break deterministic
  bit-exact matching (the core F2/F3 verification); a BER DoD requires a
  full timed chain with significance the current plan does not budget.
- **Why this is proposed:** it preserves every frozen contract while still
  allowing the "right filter, not just bit-exact" argument in F5.

### D2/D3 — Chain and noise model

- **Alternatives:** TX with an ideal sinc or a different roll-off; noise
  variance referenced to `Es = 1`.
- **Why they are rejected:** a different TX pulse silently breaks the
  matched condition the BER theory assumes; `Es = 1` would contradict the
  contractual `Es = 2` and force a second scale convention.
- **Why this is proposed:** same-RRC both ends is the honest matched setup
  for this filter, and `N0 = Es/(Es/N0)` with `Es = 2` keeps one energy
  convention across stimulus, analysis, and theory.

### D4 — Timing interpolation

- **Alternatives:** slice at the nearest integer sample; forbid
  interpolation entirely.
- **Why they are rejected:** the nearest sample is up to half a sample off
  the true center and would corrupt the BER with a timing error; forbidding
  interpolation makes slicing impossible on this grid.
- **Why this is proposed:** the interpolation is analysis machinery, not
  evidence of implementation output, and labelling keeps that distinction
  auditable (same spirit as #15 D7).

### D5 — Significance rule

- **Alternatives:** reuse the canonical 1024-symbol frame; accept any error
  count.
- **Why they are rejected:** ~2048 bits cannot support BER claims below
  ~1e-2 with any confidence; an unjustified point is worse than no point.
- **Why this is proposed:** the 100-error floor is the standard
  order-of-magnitude rule that makes each plotted point defensible, and
  separating link frames protects the canonical frame's SQNR role.

### D6/D7 — Reference and deliverables

- **Why this is proposed:** the closed-form QPSK bound is only valid under
  the exact Gray mapping, matched RRC pair, and correct timing defined
  above; stating it here binds the plots to their assumptions. The Es/N0
  set is illustrative; the significance rule, not the set, is normative.

## Acceptance Gate for the Annex

The annex is accepted for F5 use only when:

- the chain, noise model, seed, timing interpolation, and matched
  assumption are documented as above;
- every plotted `Es/N0` point meets the D5 significance rule;
- no file under `sim/vectors/`, `rtl/`, or `rtl/tb/` is modified or added
  by the annex work;
- no phase DoD is reinterpreted through BER.

If the annex is never built, this contract stays dormant and no phase is
blocked.

## References

- AWGN annex issue: [#35](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/35).
- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md` (mapping,
  `Es = 2`, D7 centers).
- RRC coefficient contract: `docs/contracts/rrc-coefficient-contract-13.md`
  (8-tap RRC, D3 constellation).
- PPA matrix: `docs/contracts/ppa-matrix-18.md` (Presentation evidence,
  conditional BER).
- Vector manifest schema: `docs/contracts/vector-manifest-schema.md`
  (untouched by this contract).
- ADR-0005 common SQNR contract, and `CONTEXT.md`.
