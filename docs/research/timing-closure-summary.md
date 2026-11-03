# Timing closure of the PPA rows: what was tried, what came out, what was decided

Date: 2026-11-03. Issue: #91, follow-up of T44 (#55). Branch: `feat/91-fast-timing-closure`.

**Evidence:**

- The OpenLane runs of this exploration: `sim/python/artifacts/timing-closure/evidence_manifest.json`. It records the
  run ids A–E used below, the commands, the RTL each run used and the hash of every file.
- T-S4P1-C FAST, collected with `ppa_stage.py` like a T41 row: `sim/python/artifacts/t41-time-ppa/T-S4P1-C/fast/`.
- The vector matching of the variants: `sim/python/artifacts/t40-time-opt-matching/T-S4P1-C/` and
  `sim/python/artifacts/t42-freq-opt-matching/F-U{4,8}-E3S/`.

**Goal.** Close timing at the target each row is built for:

- The serial rows close at SLOW (10 MHz).
- The optimized rows of each domain close at FAST (100 MHz): T-S4P1, T-S8P1, F-U4 and F-U8.

**Signoff rule.** The rule is the T41/T43 one. A row meets timing when the worst setup slack over the tt signoff corners
(`nom/min/max_tt_025C_1v80`) after routing is ≥ 0. The ss corner (`*_ss_100C_1v60`) is reported only as a diagnostic.
Every routed FAST run here, base or variant, fails at ss.

**Flow.** OpenLane 2.3.10 Classic, Sky130 `sky130_fd_sc_hd`, with the sizing and SDC files of the table
(`openlane/sdc/sky130_{10,100}MHz.sdc`). The development machine is WSL with 4 CPUs and 7.8 GiB. Every heavy run was
serialized behind one lock.

**Labels used below:**

- **Measured:** read from a report of a run.
- **Inference:** reasoned from measured data but not measured itself.
- **Proxy:** a reduced configuration used to learn about a row. It is not that row and must not be quoted as its PPA.

## 1. Result per row

| Row | Target | Before | After | Status | Where |
|---|---|---|---|---|---|
| T-serial | SLOW | +87.614 ns | no change | met, nothing to do | `main` (T41) |
| F-serial | SLOW | +80.872 ns | no change | met, nothing to do | `main` (T43) |
| T-S4P1 → **T-S4P1-C** | FAST | −0.560 ns | **+1.556 ns** | **closed** | #91 (`CAST_REGISTER`) |
| T-S8P1 (→ T-S8P1-C, optional) | FAST | +0.023 ns | +1.858 ns | already met; extra margin | #91 (run only) |
| F-U4 → F-U4-E3S | FAST | unrun | Table conditions: **fails global routing** (+1.119 ns before routing)<br>⚠️ Relaxed conditions: routes, **−1.536 ns** | **not closed** | #91 (`EXEC_STAGES`, `SPARSE_PORTS`) |
| F-U8 → F-U8-E3S | FAST | unrun | synthesizes (6:43); not placed or routed | **not closed** (same buffer structure as F-U4) | #91 |

All slacks are the worst tt setup slack after routing (measured). The exception is the +1.119 ns of F-U4-E3S under the
table's conditions: it is the nom_tt slack after the post-CTS resizer, because that run never got through routing.

**In short:**

- Every serial row meets SLOW.
- In time, both FAST rows close: T-S4P1 through the registered-cast variant T-S4P1-C, and T-S8P1 as it already was.
- In frequency, pipelining fixes timing and synthesis.
  - One pipelined lane closes FAST after routing (proxy +1.053 ns).
  - The real F-U4/F-U8 rows fail at routing under the table's conditions. The congestion comes from the shared
    work-buffer architecture.
  - With relaxed physical settings, F-U4 routes but misses by 1.5 ns. The failing paths are the wires into and out of
    that same buffer.

## 2. Serial rows at SLOW: already closed

Both serial rows already met SLOW in the committed evidence, so no change was made (measured).

**T-serial SLOW** (`sim/python/artifacts/t41-time-ppa/T-serial/slow/`):

- Setup slack +87.614 ns at tt (fmax 80.7 MHz), +73.757 ns at ss.
- Hold +0.355 ns.
- DRC and LVS 0. Antenna: 3 nets, reported but not gated.

**F-serial SLOW** (`sim/python/artifacts/t43-freq-ppa/F-serial/slow/`):

- Setup slack +80.872 ns at tt (fmax 52.3 MHz), +62.701 ns at ss.
- Hold +0.359 ns.
- DRC and LVS 0. Antenna: 117 nets, reported but not gated ("pending the timing review (T44)").

**Out of scope here: F-serial FAST.** It fails with −7.752 ns at tt (−1.309 ns even at ff). It is not a target of this
work, because serial rows are judged at SLOW. Its run was still used to calibrate how much slack the frequency engine
loses during routing (§4.1).

## 3. Time domain at FAST

### 3.1 Why T-S4P1 missed (baseline, measured)

Evidence: the committed T41 run `sim/python/artifacts/t41-time-ppa/T-S4P1/fast/`.

- Worst slack at tt: −0.560 ns, so fmax 94.7 MHz. There were 60 setup violators, and all of them end at the output.
- The critical path starts at the slot counter `last_slot`, which fans out to the operand selects of every processing
  element (PE).
- In the same clock cycle, the path then runs through the tap-0 35-bit add, the RNE/saturation cast to Q2.14, and the
  output buffer into `sample_o`.

Two candidate fixes came out of the critical-path analysis:

1. **Variant 1.** Replicate the slot register so its fanout no longer loads the path. It was drafted as a follow-up
   after T41 but never published.
2. **Variant 2.** Register the tap-0 sum `y[n]` before the output cast. This splits the add from the cast and the
   output buffer.

Variant 2 was chosen: it removes the cause (add + cast + buffer in one cycle) rather than the symptom (slot fanout).

### 3.2 What was tried: T-S4P1-C, the registered cast (`CAST_REGISTER=1`)

**Change.** `time_opt_filter.sv` gets a new parameter `CAST_REGISTER` (default 0):

- With 0, the logic is identical to the base rows.
- With 1, two 35-bit registers (`y_acc_i`, `y_acc_q`) and a valid flag hold `y[n]` between the tap-0 add and the cast.
  That is 71 new flops.

The output handshake was rewritten so that nothing is lost or duplicated under backpressure. With the register, up to
three results can be held at once (the register plus the 2-entry output buffer).

**Cost.**

- Latency goes from 2 to 3 cycles.
- II is unchanged (2 for S=4, 1 for S=8), so throughput is unchanged: 50 MS/s at 100 MHz for S=4.

**Verification (measured):**

- Vector matching: 4/4 frames PASS, 8220 codes, latency 3, II 2.
- `test_rtl_time_opt.py`: 48 passed. These include the new structural tests for T-S4P1-C: a stall with three stored
  results, reset clearing `y_acc`, and fatal checks on illegal parameter values.
- Five handshake mutants were all caught.
- Full `pytest sim/python` on this branch (both domains integrated): 925/925. Three tests pass only when rerun with
  this machine's environment (child processes without the Nix libraries).
- `rtl/run.sh` all PASS. `check-vectors.sh` exit 0. Verilator shows only the 4 warnings that already existed.
- The routed final netlist matches the canonical frame at 10 ns: 2055/2055 codes, latency 3, II 2.

### 3.3 Results (measured, FAST 100 MHz, T41 conditions)

| | T-S4P1 | **T-S4P1-C** | T-S8P1 | T-S8P1-C |
|---|---|---|---|---|
| Setup slack, worst tt (ns) | −0.560 | **+1.556** | +0.023 | +1.858 |
| fmax at tt (MHz) | 94.7 | **118.4** | 100.2 | 122.8 |
| Setup violators at tt | 60 | 0 | 0 | 0 |
| Setup slack, worst ss (ns, diagnostic) | −10.450 | −6.276 | −9.379 | −5.34 |
| Hold slack, tt (ns) | +0.354 | +0.354 | +0.355 | +0.356 |
| Cell area (µm²) | 71,702.5 | 78,380.2 (+9.3 %) | 72,927.4 | 83,911.7 (+15.1 %) |
| Synthesis area (µm²) | 73,304.1 | 77,274.1 (+5.4 %) | 78,520.3 | 79,677.7 (+1.5 %) |
| Utilization | 0.539 | 0.562 | 0.514 | 0.583 |
| Power nom_tt, SAIF (mW) | 9.722 | 10.202 (+4.9 %) | 8.878 | not collected |
| Energy per output (nJ) | 0.1944 | 0.2040 | — | — |
| Latency / II (cycles) | 2 / 2 | 3 / 2 | 2 / 1 | 3 / 1 |
| DRC / LVS | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Antenna nets | 1 | 1 (met1, ratio 1.01) | 0 | 2 |
| OpenLane exit, `final/` | 2, none | 0, written | 0, written | 0, written |

**Where the new limit is (measured).** After the change, the worst path of T-S4P1-C runs from the input register
`x_i` through the constant products, the operand select and the 35-bit add (7.23 ns of logic) into the PE partial-sum
register. The cast path now has ≥ +4.96 ns and the slot paths ≥ +6.50 ns. The tap logic of every PE shares that new
limit, so variant 1 (replicating the slot register) is not needed.

**Why the area grew more than 71 flops (inference).** Synthesis grows 5.4 %, but the routed design grows 9.3 % (S=4)
and 15.1 % (S=8). The difference is resizer repair buffers.

- The resolved configuration has `RSZ_CORNERS=None`, so the resizer repairs over all corners. It keeps adding buffers
  for the ss corner, which still fails even though tt is positive.
- Restricting the resizer to tt would probably remove most of that growth. It was not tried, because it changes the
  flow conditions relative to T41.

### 3.4 Decision (time)

- **Propose T-S4P1-C as the FAST variant of T-S4P1.** It closes with +1.556 ns at the same throughput, for one extra
  cycle of latency, +9.3 % cell area and +4.9 % energy per output.
- **Do not implement variant 1.** The slot fanout is no longer on any critical path.
- **Keep T-S8P1-C as optional evidence only.** T-S8P1 already meets FAST (+0.023 ns), but with almost no margin. The
  `-C` variant buys +1.86 ns for +15 % area. Its run is in the evidence (`time/T-S8P1-C-fast`), but it has no F3
  metadata, no gate-level matching and no power. Whether to use it is the team's call.

## 4. Frequency domain at FAST

### 4.1 Starting point (measured)

- **F-U4 and F-U8 FAST had never been run.** The committed T43 evidence marks both `unrun`. Base F-U4 synthesis was still
  in ABC after 25 min / 3.3 GB. Base F-U8 used 6.3 of 7.8 GiB in ABC and had not finished after more than 1 h.
- **The engine's critical path comes from F-serial FAST,** the only routed frequency run at 100 MHz:
  `sim/python/artifacts/t43-freq-ppa/F-serial/fast/`, −7.752 ns at max_tt.
  - The path starts at the mode register `mode_q[0]`. All of the top 1000 paths start there.
  - It runs through the operand select (`a−b` / `b` / `X[k]`), the 45×16 complex multiply, the RNE and the add/sub, and
    ends at write-back. All of that happens in one cycle.
- **Routing calibration.** Slack after global routing (post-GRT) was −5.13 ns at nom_tt. After routing it was −7.75 ns
  at max_tt. So the post-GRT estimate was 2.63 ns optimistic against max_tt and 2.07 ns against nom_tt.

### 4.2 What was tried

**Change 1: pipelining the execute stage (`EXEC_STAGES` = L, a new engine parameter).**

- The execute stage is split into L stages:
  1. X1: the operand select.
  2. X2: the 45×16 complex product.
  3. X3: RNE, add/sub and write-back.
- L=1 keeps the base execute code.
- L=2 adds a product register.
- L=3 adds an operand register as well as the product register.
- One valid chain is shared by all lanes. The mode and the entry addresses travel with each lane.
- Each FFT pass now drains L cycles instead of 1, so the cycles per block become RUN = 80/U + 9L.

**Change 2: sparse work-buffer ports (`SPARSE_PORTS`, a new engine parameter, bit-exact).**

- Enumerating the fetch addressing shows that each lane only ever reaches a few entries of the shared 16-entry work
  buffer: 44 of 128 read taps at U=4 and 48 of 256 at U=8.
- With `SPARSE_PORTS=1`, the read and write multiplexers are built only over the reachable entries. A simulation-only
  `$fatal` fires if the schedule ever issues an unreachable address.

**Functional verification (measured):**

- Differential test over 13 engines (U ∈ {1,4,8} × L ∈ {1,2,3}, plus the sparse variants): bit-exact.
- Mutants caught, and reset with the pipeline full passes.
- F-U4-E3S and F-U8-E3S vector matching: each passes 4/4 frames, 8220 exact codes, VCD covering all 257 blocks.
- Full `pytest sim/python`: see §3.2 (925/925 on this branch).
- `rtl/run.sh` passes, with the base rows unchanged. `check-vectors.sh` passes. Verilator shows only the pre-existing
  warnings.

| Run | What it is | Configuration | Result |
|---|---|---|---|
| A | **Proxy** (U=1, `freq_opt_filter` without the row check) | L=3, full ports, FAST, full Classic flow | **Post-route:** max_tt **+1.053 ns**, nom_tt +1.277, min_tt +1.469 (fmax ≈ 111.8 MHz)<br>Hold at tt +0.282<br>DRC/LVS 0, antenna 151 nets<br>Area 328,432 µm², +1.8 % at synthesis vs L=1 (+442 flops)<br>Routing lost 0.89 ns at max_tt, vs 2.63 ns for the baseline |
| B | Real row F-U4, L=3, full ports | Table conditions (`FP_CORE_UTIL` 55) | Synthesis 4:34, 1,010,898 µm² (base F-U4 never finished)<br>Setup WS +0.872 ns at nom_tt after the post-CTS resizer<br>**Global routing failed: GRT-0118 "Routing congestion too high"** |
| C | Real row F-U4-E3S (L=3, sparse ports) | Table conditions | Synthesis 3:19, 925,804 µm² (−8.4 % vs B)<br>Setup WS +1.119 ns at nom_tt after the post-CTS resizer<br>**Global routing failed again: GRT-0118** after 53 min |
| D | Real row F-U4-E3S | ⚠️ `FP_CORE_UTIL` 50 + `GRT_ALLOW_CONGESTION` 1 | Global routing finished with overflow on 32 edges (54.9 % usage)<br>Setup WS after global routing, nom_tt: +1.020 ns<br>Detailed routing converged: 95,797 → 0 violations<br>Route DRC 0; magic/KLayout DRC and LVS pass<br>**Post-route setup:** max_tt **−1.536 ns** (125 violators), nom_tt −0.743 (15), min_tt −0.035 (1) → fmax ≈ 86.7 MHz<br>**Post-route hold at tt:** max_tt −0.273 ns (11 paths), nom_tt −0.171 (1)<br>Antenna 371 nets / 600 pins<br>OpenLane exit 2 (deferred checker errors), no `final/`<br>7 h 26 min wall, 6.2 GB peak |
| E | Real row F-U8-E3S | Table conditions, synthesis only | Synthesis 6:43, 1.42 GB peak, 156,715 cells, 1,626,133 µm²<br>The full flow was not run |

Every slack in the table is measured. The proxy (run A) is not the F-serial row. It shows what one pipelined lane can
reach after routing. It is not PPA of any row.

**RTL of each run (measured by synthesis netlist hash, recorded in the evidence manifest).**

- Runs C, D and E used the RTL of this PR. Synthesizing the committed F-U4-E3S and F-U8-E3S gives the same netlists,
  byte for byte (`verify/` in the evidence).
- Runs A and B used an earlier revision of the engine. It had per-lane valid flops instead of the shared valid chain,
  and no sparse ports. It is logically equivalent by simulation but not in this PR.

**Why run D misses after routing (measured, from the max_tt report).**

The worst paths are the ones that go into or out of the shared work buffer. The tables compare each path with the same
path in the U=1 proxy (run A).

| Path (start → end) | Violators at max_tt | Worst slack D | Same path in A |
|---|---|---|---|
| `emit_idx` → buffer read mux → RNE/sat cast → output register `sample_o` | 16 | −1.536 ns | +1.334 ns |
| `p_re_q` (product register) → RNE + add/sub → work-buffer write `wr_re` | 97 | −0.959 ns | +2.160 ns |
| `p_im_q` → work-buffer write `wr_im` | 7 | −0.369 ns | +1.586 ns |
| `mul_t_re` (multiplier) → `p_re_q` | 4 | −0.213 ns | +1.551 ns |
| `state` → twiddle register | 1 | −0.166 ns | +2.669 ns |

| Path | Cell delay D | Cell delay A | Wire delay D | Wire delay A |
|---|---|---|---|---|
| Emit → output | 9.91 ns | 8.30 ns | 1.00 ns | 0.19 ns |
| `p_re_q` → buffer write | 9.58 ns | 7.62 ns | 1.27 ns | 0.06 ns |

- The emit path also loses 0.56 ns to clock skew: the launch clock arrives later than the capture clock.
- The logic is the same in both runs. Inference: the extra delay comes from the size of the buffer and the routing
  detours around it. The long wires add wire delay, and the extra load raises the delay of the cells that drive them.
- The multiplier stage, the critical stage in the proxy, is only −0.21 ns.
- Routing lost 1.76 ns at nom_tt, from +1.02 ns after global routing to −0.74 ns after routing. The proxy lost 0.67 ns.
  The "≈ +0.1 ns" estimated before this run assumed the proxy's loss and was wrong.

**Where the congestion is (an estimate from the placement, then inference).**

The measurement is the global router's overflow: B and C abort with it, and D ends with 32 overflowed edges. To see
where the demand sits, the routing demand was estimated (RUDY) from the placement after the post-CTS resizer, with
the same 20 µm bins for every design (`analysis/rudy_*.txt` in the evidence).

| Placement | Mean demand | Max demand | Area above 4 µm/µm² | Area above 5 µm/µm² |
|---|---|---|---|---|
| A (U=1 proxy, 55 %) | 2.06 | 5.42 | 0.044 mm² (6.9 %) | 0.003 mm² |
| C (F-U4-E3S, 55 %) | 2.10 | 5.57 | 0.188 mm² (10.9 %) | 0.026 mm² |
| D (F-U4-E3S, 50 %) | 1.96 | 5.52 | 0.180 mm² (9.5 %) | 0.006 mm² |

Demand is in µm/µm².

- The peak demand is about the same in all three. What changes is the size of the hot region: it is about 4× larger in
  F-U4, and the area above 5 µm/µm² is about 9× larger at 55 % utilization.
- A small hotspot can be routed around. A large one cannot.
- The work buffer, the fetch registers, the X1 select and the X2 multiply sit in that region. The placer gathers every
  lane around the shared buffer, and each lane exchanges about 360 bits with it.
- Inference: the congestion comes from the shared U-port work buffer, which the base F-U4/F-U8 rows also have, not from
  the pipeline registers. Sparse ports cut the multiplexers by about 3× and still did not make it routable.
- An earlier reading of the same estimate ("the hottest bins are 2.3–2.5× the mean") does not tell the rows apart: the
  routable proxy has a 2.6× bin too.

### 4.3 Cost of the pipelined variants (measured from RTL/simulation)

| | F-U4 (base) | F-U4-E3S | F-U8 (base) | F-U8-E3S |
|---|---|---|---|---|
| RUN per block (cycles) | 29 | 47 | 19 | 37 |
| Latency (cycles) | 39 | 57 | 29 | 47 |
| Block II (cycles) | 47 | 65 | 37 | 55 |
| Throughput at 100 MHz | (FAST not met) | 12.3 MS/s | (FAST not met) | 14.5 MS/s |
| Synthesis area (µm²) | not finished | 925,804 | not finished | 1,626,133 |

Throughput is 8 output samples per block II at 100 MHz.

- The cost comes from the drain. A block has 9 passes (4 FFT, 1 product, 4 IFFT), and each drains L cycles. With L=3
  that is 27 cycles of RUN, more than the fetch cycles (20 at U=4, 10 at U=8).
- So pipelining adds 18 cycles to the block II whatever U is (+38 % at U=4, +49 % at U=8).

### 4.4 Decision (frequency)

- **F-U4 and F-U8 FAST do not close under the table's conditions.** That is shown by measurement for F-U4: two
  RTL versions (B and C) fail global routing with GRT-0118 at `FP_CORE_UTIL` 55, while timing is positive before routing.
  F-U8 has twice the lanes on the same shared buffer, so it is expected to be at least as congested (inference, not run).
- **Pipelining fixes timing and synthesis, not routing.**
  - Timing: one pipelined lane closes FAST after routing with +1.05 ns (proxy A).
  - Synthesis: F-U4 synthesizes in about 4 min and F-U8 in about 7 min. Neither base row finished.
- **Proposal (not applied).** Closing F-U4/F-U8 at FAST under the table's conditions needs a different work-buffer
  organization, or a sizing rule the team accepts. Options:
  - Banks per lane.
  - A pipelined FFT with no shared buffer.
  - A lower core utilization accepted by the team.
- **Keep the RTL work.** `EXEC_STAGES` and `SPARSE_PORTS` are in this PR as the variants F-U4-E3S and F-U8-E3S. They
  come with F3 metadata and matching evidence, and the exploration runs above, but no table row. Any future buffer
  reorganization will need them, because without pipelining the timing gap is about 7.75 ns.
- **Even with ⚠️ relaxed settings, F-U4-E3S does not close (run D, measured).**
  - It routes clean (DRC 0, LVS pass).
  - It misses FAST at tt by 1.536 ns (max_tt) and has hold violations at tt.
  - The failing paths are the write-back into the shared buffer and the emit read out of it, not the pipelined multiplier.
- **What another iteration would need (inference, not tried).**
  - Registering the emit read before the cast. That costs 1 cycle of latency.
  - Registering the X3 result before the buffer write. That is one more stage, so +9 cycles of RUN and block II.
  - Each full F-U4 run takes about 7.5 h and 6.2 GB on this machine, close to its memory limit.
  - Any result would still be under the relaxed settings, so it would not be a table result.
  - An L=4 cut was prepared but not applied. It registers the four real products before the complex sum, and it does
    not address these paths.
- **Decision: stop here and take it to the team.** Another iteration was not run. The open question is
  architectural (the shared work buffer), not one more register.

## 5. Deviations that need a team decision (⚠️ DESVÍO)

None of the following were applied to the contracts. Each one needs the team's approval.

1. ⚠️ **DESVÍO — rows outside the base matrix.** `ppa-matrix-18` defines six base rows. T-S4P1-C (and the frequency
   variants) are extension rows. Either they are accepted as extension rows, or T-S4P1-C replaces T-S4P1 as the FAST
   row. That needs an amendment of the contract.
2. ⚠️ **DESVÍO — the registered cast is not P.** The contract defines P=2 as a register between the multiply and the
   add. The cast register sits after the add, so calling the variant "T-S4P2" would be wrong. The suffix `-C` and the
   parameter `CAST_REGISTER` are proposed names.
3. ⚠️ **DESVÍO — F3 metadata for a non-base variant.** `gen_vectors.py` `_RTL_VARIANTS` gains `T-S4P1-C` (latency 3).
   Because of the hash cascade, F1, T20, T21, F2 and every F3 manifest were regenerated. Only JSON files and sidecars
   changed.
4. ⚠️ **DESVÍO — not in `openlane/ppa_runs.json`.** The T-S4P1-C run used an in-memory row with the table's sizing and
   overrides. To add it to the table, it also needs a SLOW run, `rows.json` regenerated, and possibly the T44 table.
5. ⚠️ **DESVÍO — frequency variants outside the base matrix.**
   - F-U4-E3S and F-U8-E3S add two engine parameters (`EXEC_STAGES`, `SPARSE_PORTS`) and their own F3 metadata, with
     latency 57/47 and block II 65/55.
   - Whether they may stand in for F-U4/F-U8 as FAST rows needs a `ppa-matrix-18` decision. They raise the block II by
     18 cycles.
6. ⚠️ **DESVÍO — relaxed physical settings in run D.** `FP_CORE_UTIL` 50 is inside the contract's 50–60 % band but
   below the table's 55, and `GRT_ALLOW_CONGESTION` 1 is not in the table at all. Both were used for measurement only.
   A result from run D is not a table result.
7. ⚠️ **DESVÍO — architecture change proposed, not applied.** Closing F-U4/F-U8 at FAST probably needs a work-buffer
   reorganization: banks per lane or a pipelined FFT (§4.4). That changes the T42 architecture and is a team decision.
8. ⚠️ **DESVÍO — the base rows' netlists change at the default parameters.** The new parameters default to the base
   behaviour (`CAST_REGISTER=0`, `EXEC_STAGES=1`, `SPARSE_PORTS=0`), and every base-row test and matching passes. But
   the RTL text of the base path changed, and the synthesis netlists differ from main's (measured, `verify/` in the
   evidence):

   | Row | Cells, main | Cells, this PR | Area, main (µm²) | Area, this PR (µm²) | Change |
   |---|---|---|---|---|---|
   | T-S4P1 | 6,492 | 6,492 | 73,304.1 | 73,270.3 | −0.05 % |
   | T-S8P1 | 7,179 | 7,173 | 78,520.3 | 78,930.7 | +0.5 % |
   | F-serial | 30,389 | 30,352 | 328,721.5 | 328,239.8 | −0.15 % |

   - Main's RTL, synthesized the same day from another path, reproduces the T41 netlists byte for byte. So the
     difference comes from the RTL, not from the tool or the path.
   - After this PR merges, a rerun of a base row would give slightly different PPA from the committed T41/T43 evidence.
   - Options for the team:
     - Accept it, with T44 citing the pre-merge commit for the base rows.
     - Keep the variants out of the base files (for example separate modules or wrappers), so the base netlists stay
       identical. That needs a rework of this PR.

## 6. Integration notes

- **One branch for both domains.** The time and frequency variants were developed apart and integrated here.
  - The runner, the testbench, `rtl_matching_stage.py`, `gen_vectors.py` and their tests carry both sets of options.
  - The `gen_vectors` provenance cascade was rerun once over every variant (F1, T20, T21, F2, F3). Only JSON manifests
    and sidecars changed.
- **Evidence is committed for the record, not as table rows.** `openlane/ppa_runs.json` and `rows.json` are unchanged.
  - T-S4P1-C is collected like a T41 row.
  - The other runs are curated reports. The evidence manifest describes how they were curated.
- **Tool issue for the T43 owner.** The `saif_applied` heuristic in `ppa_stage.py` labels the time rows'
  `power_status` as `partially-annotated`. OpenSTA's unannotated combinational estimate for these rows is only about
  6–8 µW, so any real SAIF raises it, and the check misfires.
  - The committed T41 evidence predates the check and says `annotated`.
  - Regenerating any time row with the current `ppa_stage.py` would flip it too (inference).

## 7. Not measured

- T-S4P1-C at SLOW was not run. It is needed only if the row enters `ppa_runs.json`.
- T-S8P1-C has no power figure, no F3 metadata and no gate-level matching.
- The resizer restricted to tt (`RSZ_CORNERS`) was not tried (§3.3).
- F-U4-E3S has a post-route result only under ⚠️ relaxed settings (run D): −1.536 ns at max_tt. It has none under the
  table's conditions, because it never got through global routing.
- F-U8-E3S was not taken past synthesis.
- The base F-U4/F-U8 rows were not taken past synthesis either, so there is no measured comparison of their
  routability. That they would congest too is an inference: they share the same buffer.
- The base rows at the default parameters were not proven equivalent to main's RTL. They are functionally identical
  by simulation (every base-row test and matching). Their netlists differ slightly (§5, item 8). No formal equivalence
  check was run.
  - For the frequency engine, the `L1-main-*` checks show that path and line numbers do not change the netlist, so the
    difference is structural.
- No frequency variant has a table row, power or gate-level matching.
- Runs A and B used an engine revision that is not in this PR. A rerun with the final RTL would change their
  numbers slightly (inference).
