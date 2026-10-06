# Research contracts

Canonical copies of the decision contracts and their backing research reports
for the execution Wayfinder map
([#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)).
Accepted decisions are also recorded as ADRs in `docs/adr/`; these documents
hold the supporting research, the decision rationale, and the reproducible
checks.

| Document | Ticket | Status | Summary |
| --- | --- | --- | --- |
| [toolchain-gap-2.md](toolchain-gap-2.md) | #2 (closed) | Accepted into ADR-0004/0005/0006 | Python 3.12 pins, Icarus/vvp, optional Verilator lint, and the OpenLane 2 + Sky130 PPA evidence checklist. |
| [rrc-coefficient-contract-13.md](rrc-coefficient-contract-13.md) | #13 (closed) | Accepted D1-D7 | 8-tap RRC grid, raw values, unit-energy normalization, 3.5-sample delay, data `Q2.14`; the coefficient format was refined to the common `Q2.(W-2)` by #16. |
| [frequency-block-contract-14.md](frequency-block-contract-14.md) | #14 (closed), #74 | Accepted D1; D2 via #15; D3 deferred; assignment confirmation 2026-10-06 | Forced-50% OLS (`N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`), OLA comparison and the concept FAQ. The revised assignment fixes 50% overlap and closes the hop-9 professor gate. |
| [qpsk-stimulus-15.md](qpsk-stimulus-15.md) | #15 (closed) | Accepted D1-D8 | 1024 symbols, `default_rng(2026)`, edge patterns, zero-insertion upsampling, and the full causal output window. |
| [fxp-common-width-16.md](fxp-common-width-16.md) | #16 (closed) | Research report — historical, superseded fields in Resolution Status; normative is fxp-policy-16.md | Long-form FXP study that backs `fxp-policy-16.md`. |
| [fxp-policy-16.md](fxp-policy-16.md) | #16 (closed), #74 | Accepted D1-D9; format and base-scope amendments 2026-10-02; cross-domain SQNR amendment 2026-10-06 | Production Q2.14/RNE, conservative guards, frequency A, mandatory width sweep and integer freeze; cross-domain SQNR >= 33.98 dB (34 dB nominal) between time and frequency FXP outputs; truncation/wrap, narrow guards and frequency B are optional. |
| [rtl-streaming-17.md](rtl-streaming-17.md) | #17 (closed), #42 | Accepted D1-D9; finite-frame amendment 2026-10-02; T03 amendment under PR #73 review | `valid`/`ready`, shared synchronized reset, packed `{Q,I}`, latency, flush/drain counts, and transport-only T03 verification before F3. |
| [vector-manifest-schema.md](vector-manifest-schema.md) | #15/#16/#17 (via #12) | Normative; lifecycle amendment 2026-10-02 | Staged float reference, Q2.14 integer expectations, and per-variant RTL matching metadata with hashes and transport counts. |
| [ppa-experiment-matrix-18.md](ppa-experiment-matrix-18.md) | #18 (closed) | Research report — historical, superseded fields in Resolution Status; normative is ppa-matrix-18.md | Long-form PPA matrix study that backs `ppa-matrix-18.md`. |
| [ppa-matrix-18.md](ppa-matrix-18.md) | #18 (closed) | Six-architecture base; target/evidence amendment 2026-10-02 | Serial SLOW 10 MHz and optimized FAST 100 MHz main targets, paired comparative runs, valid activity, and same-domain serial improvement evidence. Additional architectures remain extension-only. |
| [openlane-env-19.md](openlane-env-19.md) | #19 (closed) | Task record | Verified Nix/OpenLane/PDK, smoke test, report paths, and the small-design PDN fix. |
| [link-awgn-annex-35.md](link-awgn-annex-35.md) | #35 (open) | Accepted D1-D8; outside base, dormant pending explicit activation | Python-only AWGN link annex: chain, noise model, timing and significance; no RTL/vector/TB/DoD changes and no delivery blocker. |

Original research branches remain as history; the copies in this folder are
the maintained ones.

## Adding a new contract

1. Resolve the research ticket first; keep the document on its research branch
   if that is the workflow in use.
2. Add the maintained copy here as `<topic>-<ticket>.md`.
3. Add a row to the table with ticket, status, and a one-line summary.
4. Link the document from its ticket so reviewers can find it.
