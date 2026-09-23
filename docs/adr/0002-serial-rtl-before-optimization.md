# Serial RTL with vector matching before optimizing

**Status:** accepted, extended by contracts. Normative: `docs/contracts/rtl-streaming-17.md` + `docs/contracts/frequency-block-contract-14.md` + `docs/contracts/ppa-matrix-18.md`. This ADR defines only the serial-first baseline rule; streaming interface, OLS schedule, and optimization matrix live in the contracts.

Every PPA optimization starts from a working serial RTL with 100% vector matching against `sim/vectors/`.

We avoid optimizing a design with no reference: the serial version sets the correctness and PPA baseline against which unfolded/pipeline/systolic/folded are measured.
