# rtl/freq_opt — frequency-domain filter, optimized rows F-U4 and F-U8

`freq_opt_filter.sv` is the optimized frequency lane of the reduced matrix
(`docs/contracts/ppa-matrix-18.md`): **one source, two rows**. The parameter
`U` is the number of arithmetic issue lanes, 4 for F-U4 and 8 for F-U8
(`U=1` is `freq_serial`). It replaces the T03 transport shell (T42, #53). The
datapath is the shared `rtl/common/rrc_freq_engine.sv`, the same source as the
serial baseline; this wrapper adds the synchronized reset, the stream interface,
the parameter checks and the matrix row. A row is never an edited copy.

```bash
bash rtl/freq_opt/run.sh                   # both rows on their rtl_matching vectors
bash rtl/freq_opt/run.sh --lanes 8         # one row
bash rtl/freq_opt/run.sh --lanes 4 --vcd .build/f-u4.vcd
bash rtl/freq_opt/run.sh --exec-stages 3 --sparse-ports 1   # the FAST variants F-U4-E3S and F-U8-E3S (#55)
python -m pytest sim/python/tests/test_rtl_freq_matching.py sim/python/tests/test_rtl_freq_opt.py -v
```

Two more parameters, both default to the base rows and neither changes a code:
`EXEC_STAGES` (1) is the number of execute cycles of a lane and
`SPARSE_PORTS` (0) builds the work-buffer ports only for the entries a lane
can address. The proposed FAST variants of #55 set 3 and 1 (see "FAST variants"
below).

## What a lane is

A lane is one butterfly unit with its own complex multiplier. The 16-point FFT
has 4 radix-2 stages of 8 butterflies, the IFFT has 4 more, and the spectral
product has 16 independent bin products. With `U` lanes a pass fetches `U`
butterflies per cycle, so it takes `8/U` fetch cycles (`16/U` for the product)
plus the one drain cycle that lets the next pass read fully written values.
`U=8` runs a whole stage at once, which is the natural full parallelism of
radix-2 FFT16. The bin product and the IFFT use the same lanes, so they are in
the same top-level accounting (`ppa-matrix-18.md`, definition of `U`).

| Row | `U` | Fetch cycles per butterfly pass | Product pass | RUN | Cycles per block | First output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F-serial | 1 | 8 (+1 drain) | 16 (+1) | 89 | 107 | 99 |
| F-U4 | 4 | 2 (+1) | 4 (+1) | 29 | 47 | 39 |
| F-U8 | 8 | 1 (+1) | 2 (+1) | 19 | 37 | 29 |

A block is `8 ACCEPT + 1 LOAD + RUN + 8 EMIT + 1 DRAIN` and RUN is `80/U + 9`
cycles; the first output follows the accept edge of the first sample by
`RUN + 10`. A whole frame (257 blocks) takes 27499, 12079 and 9509 cycles.
Accepting 8 samples and emitting 8 outputs is serial in every row, so at `U=8`
16 of every 37 cycles are the stream interface: the speed-up over the serial
engine is 2.9x for `U=8` and 2.3x for `U=4`, not 8x and 4x.

## Why it is bit-exact with the serial engine

The butterflies of one pass touch disjoint pairs of the work buffer, so running
`U` of them in the same cycle cannot change a result: the order of the passes,
the arithmetic of a butterfly (one RNE shift per twiddle product, the exact
spectral product, the single `/16` fused into the output cast) and every width
are the serial ones. `U` only changes how many butterflies are fetched per
cycle. The lanes write disjoint entries, the control signals keep their names
(`state`, `cnt`, `pass`, `step`, `emit_idx`) and `U=1` behaves exactly as before
the change: F-serial still matches in 27499 cycles with latency 99.

Bit-exactness is checked three ways: 100 % matching of the four T22 frames per
row (`test_rtl_freq_matching.py`), a differential run of `U = 1, 4, 8` on the
same random, full-scale and alternating-extreme blocks with their own bubbles
and stalls (`test_rtl_freq_opt.py`; the T22 frames are QPSK and reach no RNE tie
or output saturation, the differential run reaches saturation and checks every
raw output), and the reset in the middle of RUN, EMIT and DRAIN
(`test_rtl_freq_serial.py`). The differential check is shown to catch a lane that
reads the wrong twiddle or writes back the wrong operand.

## FAST variants (#55, proposed)

### Pipelined lane (`EXEC_STAGES`)

The base rows execute a butterfly in the cycle after its fetch: operand select,
the 45x16 complex product, its 62-bit sum, one RNE, the add/subtract, the mode
mux and the write-back, about 17.6 ns of logic in the F-serial FAST run, all
launched by one `mode_q` flop. `EXEC_STAGES` (L) cuts that cycle with
registers, without touching any operation:

| L | Execute cycles after the fetch |
| ---: | --- |
| 1 | select, product, RNE, add/subtract, write back (the base rows) |
| 2 | select and product / RNE, add/subtract, write back |
| 3 | select / product / RNE, add/subtract, write back |

Each cut register carries the butterfly's operands, its mode and its two work
buffer entries, per lane, so no control flop drives the arithmetic of every
stage. The lanes issue together, so one chain of valid bits (the only reset
flops added) serves them all and its last bit enables the write-back. The
select stage registers the multiplier operand (`a-b`, `b` or `X[k]`) and the
one operand the last cycle adds to (`a+b` for the forward butterfly, `a` for the
inverse), not `a` and `a+b`. A pass now drains L cycles instead of one, so its last write
lands before the next pass reads:

| Row | `U` | L | Butterfly pass | Product pass | RUN | Cycles per block | First output | Frame |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| F-U4 | 4 | 1 | 2 (+1) | 4 (+1) | 29 | 47 | 39 | 12079 |
| F-U4-E3S | 4 | 3 | 2 (+3) | 4 (+3) | 47 | 65 | 57 | 16705 |
| F-U8 | 8 | 1 | 1 (+1) | 2 (+1) | 19 | 37 | 29 | 9509 |
| F-U8-E3S | 8 | 3 | 1 (+3) | 2 (+3) | 37 | 55 | 47 | 14135 |

RUN is `80/U + 9L` and every other number follows as for the base rows: each
extra execute cycle costs 9 cycles per block (one per pass). At 100 MHz the
block II of 65 and 55 cycles is 12.3 and 14.5 Msample/s (8 outputs per block).

### Sparse work-buffer ports (`SPARSE_PORTS`)

With full ports every lane can read and write any of the 16 entries: `2U`
read taps and `2U` write sources per entry. The addressing of a lane only ever
reaches a few of them; the engine enumerates them at elaboration from the same
address formulas (over the four spans, every fetch step and the product bins)
and builds the multiplexers over those only. Read taps in use: 44 of 128 at
`U=4` and 48 of 256 at `U=8`; write sources per entry 1-4 of 8 and 1-5 of 16.
An address outside the enumeration never occurs; simulation stops with a fatal
error if the schedule ever issues one. The cycle numbers do not change.

### Matching

The variants are rows of the same source selected with `--exec-stages L
--sparse-ports 1`; their `rtl_matching` manifests carry `rtl_parameters {"U":
4|8, "EXEC_STAGES": 3, "SPARSE_PORTS": 1}` and the testbench reads them back
(`DUT parameters U=... EXEC_STAGES=... SPARSE_PORTS=...`, printed only when the
runner defines them, so the base rows report as before). Evidence:
`sim/python/artifacts/t42-freq-opt-matching/F-U{4,8}-E3S/`: 4/4 frames, 8220
exact codes per variant, fill latency 57 and 47, block II 65 and 55 over the
first 256 intervals, source tail 121 and 101, VCD over all 257 blocks.

Bit-exactness is checked as for the unfolding: the four T22 frames per variant,
the differential run of thirteen engines (`U` in {1, 4, 8} x `L` in {1, 2, 3}
with full ports, and `U` = 4, 8 with sparse ports at `L` = 1 and 3;
`test_rtl_freq_opt.py`) with three more mutants (a pass that drains one cycle
too few, a product register that takes the fetch stage's entry, a sparse port
that misses one entry), and the reset in RUN with butterflies in the execute
stages (`test_rtl_freq_serial.py`).

### Physical exploration (not PPA evidence)

OpenLane 2.3.10 Classic, sky130A/hd, FAST SDC, `tt_025C_1v80`, run in a
development worktree, so nothing below is committed PPA evidence (T43 owns
that) and every number is a measurement of one run:

| Run | What | Result |
| --- | --- | --- |
| U=1 proxy, L=3 (full ports) | `freq_opt_filter` without the row check, full Classic flow | post-route setup WS **+1.05 ns at max_tt** (nom_tt +1.28, ff +4.59), hold +0.10; DRC 0 (magic, KLayout, route), LVS 0, 151 antenna nets; 328432 um2. Base F-serial FAST: -7.75 ns |
| F-U4, L=3, full ports | real-row config (55 %) | synthesis 4:34 (the base F-U4 had not finished ABC after 25 min); post-CTS resizer +0.87 ns; global routing fails, congestion (GRT-0118) |
| F-U4-E3S | real-row config (55 %) | synthesis 3:19, 925804 um2 (-8 %); post-CTS resizer +1.12 ns; global routing fails, congestion |
| F-U4-E3S, `FP_CORE_UTIL=50`, `GRT_ALLOW_CONGESTION=1` | sizing at the low end of the 50-60 % band | global routing ends with 32 overflowed edges (54.9 % usage); post-GRT setup +1.02 ns (nom_tt); detailed routing converges slowly (95797 -> 61213 -> 57892 violations in the first three iterations, about 35 min each) |
| F-U8-E3S | synthesis only | 6:43, peak 1.42 GB, 156715 cells, 1626133 um2 (the base F-U8 used 6.3 GB in ABC and had not finished after 1 h) |

What it shows: the cuts move the critical path from the 17.6 ns control +
multiply + round + add cycle to the 45x16 product alone (about 7.5 ns), and
they make synthesis of the unfolded rows cheap. What stops the real rows is
routing: every lane exchanges about 360 bits per butterfly with the one shared
work buffer, so the placer gathers the lanes around it and the centre of the
die congests (estimated routing demand 2.4x the mean there). Sparse ports
shrink the multiplexers but not that traffic. Closing F-U4/F-U8 at FAST in the
table's conditions needs a different work-buffer organisation (banks per lane,
or a pipelined FFT without a shared buffer); a larger die is a sizing-rule
decision of the team.

## Status

- Vector matching (T42, #53): 4/4 frames PASS per row, 2055 exact codes each
  (8220 per row), 257 blocks, 2056 raw outputs, block II 47 and 37 cycles over
  the first 256 intervals, fill latency 39 and 29, source tail latency 85 and 65
  (last source sample `x[2047]` to the last valid output `y[2054]`), and a scoped
  VCD covering all 257 blocks. The evidence is
  `sim/python/artifacts/t42-freq-opt-matching/<row>/`. The definitions of these
  timings are those of F-serial (`rtl/freq_serial/README.md`, "Vector matching
  (T33)"); the RUN length is checked against `80/U + 9`.
- The rows are selected with `--lanes U` in `rtl/run_variant.sh`; the
  `rtl_matching` manifest carries `rtl_parameters {"U": 4|8}`, which the
  testbench reads back from the instance (`DUT parameters U=...`).
- The elaboration rejects any other lane count, other framing tuples and
  `DATA_WIDTH`/`SPC` other than 16/1 (`test_rtl_config.py`).
- The OpenLane configuration (`openlane/freq_opt/config.json`) names its sources
  and uses relative sizing like the time rows. The target runs, the timing
  closure at FAST 100 MHz (the main target of both rows) and the PPA numbers
  are T43 (#54); nothing here is a PPA result.

## The transport shell

Until T42 this wrapper was the elastic transport-only shell. The testbench
mechanics tests (`test_rtl_stream.py`, `test_rtl_config.py`) still need a DUT
whose output is its input, so the shell lives on as the test-only wrapper
`sim/python/tests/transport/transport_filter.sv` (runner variant `transport`).
It is not a filter, is never synthesized and is not a PPA row.

## Learning

- Unfolding is replication of the arithmetic, not a new algorithm: the schedule
  and every rounding stay the serial ones, so exactness comes from the
  disjointness of the butterflies of a pass, and the check that matters is a
  differential one on codes that reach rounding ties and saturation.
- The stream interface is serial. Eight cycles to accept a block and eight to
  emit it do not shrink with `U`, which caps the gain (2.9x at `U=8`); a design
  that overlaps the next block's accept with the current compute would lower
  the block II further at the cost of a second frame buffer, and is left as an
  extension.
- The work buffer is a register file with `U` pairs of read ports and `U` pairs
  of write ports. The wiring grows with `U` even though each lane is the same
  hardware, so the area of a row is not just `U` multipliers.
- A row's cycle numbers follow from `U` (`80/U + 9`), so the matching evidence
  checks the declared RUN length against that formula instead of trusting it.

## Scope limits

These are functional results.

- **Physical runs.** Synthesis, FAST 100 MHz timing, activity, power and signoff
  of F-U4 and F-U8 are T43 (#54). The execute stage does a 45x16 complex product,
  a 62-bit sum, the RNE and the add/subtract in one cycle, so closing 10 ns in
  sky130 is not assured (T-S4P1, with much smaller arithmetic, missed it by
  0.56 ns in T41), and synthesis time grows with `U`. If a row misses FAST it is
  recorded as a failed main goal. The registers that #55 adds for that are the
  `EXEC_STAGES` variants above, with their own matching; their physical
  exploration is not PPA evidence.
- **PPA claims.** The deltas against F-serial at a matched target and the
  "improves at least one axis" claim belong to T43/T44; nothing in this
  directory states a throughput/area/power result.
- **Block overlap.** The rows keep the serial schedule (accept, load, run, emit,
  drain), so only RUN scales with `U`. Overlapping the next block's accept with
  the current compute is outside this scope.
- **Other lane counts.** `U=2` and the folded contrast `F=2` are extension rows
  of `ppa-matrix-18.md`; the engine elaborates only `U` in {1, 4, 8}.
- **`docs/block-diagram.md`** describes this architecture in sections 3 and 4.8.
