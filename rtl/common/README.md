# rtl/common — shared time/frequency

Frozen fxp coefficients (T22) + shared packages/constants.

Nothing domain-specific goes here: shared logic is shared, not duplicated.

The current `rrc_stream_placeholder.sv` is only a toolchain smoke shell. It
keeps the output idle and is superseded by the accepted streaming interface in
`docs/contracts/rtl-streaming-17.md` (`valid`/`ready`, packed `{Q,I}`, reset
synchronizer, and the `rrc_pkg.sv` constants), which replaces the shell in F3.
