# Research contracts

Canonical copies of the research contracts produced for the execution Wayfinder map
([#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)).

Each document keeps its originating ticket and decision status. Accepted decisions are
recorded as ADRs in `docs/adr/`; these documents hold the supporting research, the open
human decisions, and the reproducible checks that back them. Original research branches
remain as history; the copies in this folder are the maintained ones.

| Document | Ticket | Status | Summary |
| -------- | ------ | ------ | ------- |
| [toolchain-gap-2.md](toolchain-gap-2.md) | #2 (closed) | Accepted into ADR-0004/0005/0006 | Python 3.12 pins, Icarus/vvp, optional Verilator lint, and the OpenLane 2 + Sky130 PPA evidence checklist. |
| [rrc-coefficient-contract-13.md](rrc-coefficient-contract-13.md) | #13 (open) | Research complete, D1-D7 pending team acceptance | 8-tap RRC grid, raw values, unit-energy normalization, ordering, 3.5-sample delay, and Q2.14/Q1.15 scaling. |
| [frequency-block-contract-14.md](frequency-block-contract-14.md) | #14 (open) | Research complete, baseline pending team acceptance | Overlap-save versus overlap-add, FFT16 with 50% overlap, hop/discard/latency conventions, and alignment with time. |
| [fxp-common-width-16.md](fxp-common-width-16.md) | #16 (open) | Research complete, policy pending team acceptance | Signed Q2.(W-2) common width, sweep W=8..18, rounding/saturation policy, and accumulator/FFT width trade-offs. |
| [ppa-experiment-matrix-18.md](ppa-experiment-matrix-18.md) | #18 (open) | Research complete, matrix pending team acceptance | Serial baselines plus pipeline/unfolded/folded experiment matrix and OpenLane evidence for the 100 MHz/10 MHz targets. |

## Adding a new contract

1. Resolve the research ticket first; keep the document on its research branch if that is
   the workflow in use.
2. Add the maintained copy here as `<topic>-<ticket>.md`.
3. Add a row to the table with ticket, status, and a one-line summary.
4. Link the document from its ticket so reviewers can find it.
