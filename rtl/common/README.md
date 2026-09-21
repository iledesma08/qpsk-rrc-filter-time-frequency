# rtl/common — shared time/frequency

Frozen fxp coefficients (T22) + shared packages/constants.

Nothing domain-specific goes here: shared logic is shared, not duplicated.

The current `rrc_stream_placeholder.sv` is only a toolchain smoke shell. It
passes one registered sample through and must be replaced by the shared RTL
contracts decided before F3.
