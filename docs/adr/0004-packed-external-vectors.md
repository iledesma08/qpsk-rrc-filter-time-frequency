# Packed external vectors for vector matching

**Status:** accepted, extended by contracts. Normative manifest: `docs/contracts/qpsk-stimulus-15.md` + `docs/contracts/fxp-policy-16.md` + `docs/contracts/rtl-streaming-17.md` + `docs/contracts/vector-manifest-schema.md`. This ADR defines only packing {Q[15:0],I[15:0]} + $readmemh + hash.

Python remains the golden-vector source of truth. `gen_vectors.py` generates
packed `.hex` input and expected-output files, one 32-bit record per complex
sample using `{Q[15:0], I[15:0]}`, plus a SHA-256 sidecar and a generated
`vector_manifest.svh` containing metadata such as the vector count and
packing. Testbenches consume the files with `$readmemh`; vectors are never
compiled into the DUT. Generated SystemVerilog includes are reserved for small
hardware constants such as frozen coefficient tables.

CSV may be emitted as an optional Python-analysis export, but it is not part
of RTL vector matching.

Lifecycle amendment accepted 2026-10-02: T13 first produces deterministic F1
stimulus/float references and generation infrastructure. T22 regenerates the
production integer expected codes from each accepted FXP model. T31/T33 add
per-variant streaming metadata and measured latency for RTL consumption.
Float references are not integer expected vectors; F1/F2 completion does not
require future RTL latencies. The normative schema declares the artifact
stage and its applicable fields, retaining external packed records and hashes.
