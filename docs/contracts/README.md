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
| [frequency-block-contract-14.md](frequency-block-contract-14.md) | #14 (closed) | Accepted D1; D2 via #15; D3 deferred | Forced-50% OLS (`N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`), OLA comparison, professor gate, and the concept FAQ. |
| [qpsk-stimulus-15.md](qpsk-stimulus-15.md) | #15 (closed) | Accepted D1-D8 | 1024 symbols, `default_rng(2026)`, edge patterns, zero-insertion upsampling, and the full causal output window. |
| [fxp-common-width-16.md](fxp-common-width-16.md) | #16 (closed) | Research report — historical, superseded fields in Resolution Status; normative is fxp-policy-16.md | Long-form FXP study that backs `fxp-policy-16.md`. |
| [fxp-policy-16.md](fxp-policy-16.md) | #16 (closed) | Accepted D1-D9 | Common `Q2.(W-2)`, phased `W=8..18` sweep, RNE/saturation policy, and the manifest schema. |
| [rtl-streaming-17.md](rtl-streaming-17.md) | #17 (closed) | Accepted D1-D9 | `valid`/`ready` handshake, reset synchronizer, packed `{Q,I}`, latency declaration, and frequency block parameters. |
| [vector-manifest-schema.md](vector-manifest-schema.md) | #15/#16/#17 (via #12) | Normative | Single vector-manifest schema (stimulus + FXP + streaming + hashes); per-doc lists are non-normative examples. |
| [ppa-experiment-matrix-18.md](ppa-experiment-matrix-18.md) | #18 (closed) | Research report — historical, superseded fields in Resolution Status; normative is ppa-matrix-18.md | Long-form PPA matrix study that backs `ppa-matrix-18.md`. |
| [ppa-matrix-18.md](ppa-matrix-18.md) | #18 (closed) | Accepted D1-D9, D1 amended 2026-09-25 to a 6-row base (12-row on extension) | 6-row base matrix (serials + S4/S8 + U4/U8), factor definitions, canonical workload, controlled conditions, VCD/SAIF power policy, and Pareto ranking. |
| [openlane-env-19.md](openlane-env-19.md) | #19 (closed) | Task record | Verified Nix/OpenLane/PDK, smoke test, report paths, and the small-design PDN fix. |
| [link-awgn-annex-35.md](link-awgn-annex-35.md) | #35 (open) | Accepted D1-D8; dormant until built | Optional Python-only AWGN link annex (F5): chain, noise model, timing, significance rule; no RTL/vector/TB/DoD changes. |

Original research branches remain as history; the copies in this folder are
the maintained ones.

## Adding a new contract

1. Resolve the research ticket first; keep the document on its research branch
   if that is the workflow in use.
2. Add the maintained copy here as `<topic>-<ticket>.md`.
3. Add a row to the table with ticket, status, and a one-line summary.
4. Link the document from its ticket so reviewers can find it.
