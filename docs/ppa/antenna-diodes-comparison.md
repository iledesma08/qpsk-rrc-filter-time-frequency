# Antenna trial: T44 baseline vs heuristic diodes at 45 % utilization

> **Unverified exploratory trial.** The numbers below come from local runs
> (`.build/ppa/`) whose manifests and `rows.json` are not committed, so nobody
> else can check them from the repo. They are not T44 evidence and no gate,
> Pareto front or D7 claim rests on them.

Hand-written comparison of every target run executed with the antenna trial
against the T44 baseline (`docs/ppa/t44-ppa-table.md`). It is **not** generated
by `ppa_table.py` and does not replace the T44 table.

## What changed

`ppa_stage.py run --antenna-trial` adds `antenna_trial.overrides` from
`openlane/ppa_runs.json` to the floorplan pre-pass and to the full run:

| Variable | T44 baseline | Trial |
| --- | ---: | ---: |
| `RUN_HEURISTIC_DIODE_INSERTION` | false | **true** |
| `GRT_ANTENNA_ITERS` | 3 | **10** |
| `GRT_ANTENNA_MARGIN` | 10 | **20** |
| `FP_CORE_UTIL` | 55 | **45** |

Everything else is the T44 setup: OpenLane 2.3.10 Classic, sky130A /
sky130_fd_sc_hd, signoff at `tt_025C_1v80`, same SDCs, same die floor rule.

## Results

Baseline = T44 table. Trial = the trial run's signoff metrics. fmax is derived
as 1 / (period − setup WS). Antenna = post-route nets (max ratio). Status uses
the T44 gates, including the amendment (≤ 3 residual nets, ratio ≤ 1.72).

| Run | Cell area baseline (µm²) | Cell area trial (µm²) | Area Δ | Setup WS baseline → trial (ns) | fmax trial (MHz) | Antenna baseline → trial | DRC / LVS | Status trial |
| --- | ---: | ---: | ---: | --- | ---: | --- | --- | --- |
| T-serial-SLOW | 47,035.1 | 54,915 | +16.8 % | +87.61 → +87.0 | 76.9 | 3 (1.64) → **0** | pass | **pass** (no amendment needed) |
| T-serial-FAST | 49,990.4 | 56,952 | +13.9 % | −0.86 → −1.11 | 90.0 | 3 (1.26) → **0** | pass | FAIL: timing |
| T-S4P1-SLOW | 67,811.3 | 77,328 | +14.0 % | +87.96 → +88.1 | 84.0 | 0 → 0 | pass | **pass** |
| T-S4P1-FAST | 71,702.5 | 82,850 | +15.5 % | −0.56 → −0.48 | 95.4 | 1 (1.13) → **0** | pass | FAIL: timing |
| T-S8P1-SLOW | 69,870.8 | 80,746 | +15.6 % | +88.98 → +88.8 | 89.3 | 3 (1.72) → **0** | pass | **pass** (no amendment needed) |
| T-S8P1-FAST | 72,927.4 | 86,054 | +18.0 % | +0.023 → **+0.20** | 102.0 | 0 → 0 | pass | **pass** |
| F-serial-SLOW | 314,206.0 | 412,238 | +31.2 % | +80.87 → +80.2 | 50.5 | 117 (5.13) → **8 (3.11)** | pass | FAIL: antenna over the amendment |
| F-serial-FAST | 317,850.0 | (414,689 pre-route) | (+30.5 %) | −7.75 → (−5.45 pre-route) | — | 129 (6.17) → (19 pre-route) | — | FAIL: global routing congestion (GRT-0232 in repair antennas, step 42, exit 2) |
| F-U4 / F-U8 | unrun | unrun | — | — | — | — | — | unrun |

F-serial-SLOW inserted 36,465 diodes. Its eight residual nets:

| Net | Ratio | Layer |
| --- | ---: | --- |
| net1792 | 3.11 | met1 |
| net747 | 3.03 | met2 |
| net1513 | 1.63 | met1 |
| _23188_ | 1.48 | met1 |
| net1365 | 1.33 | met2 |
| net175 | 1.28 | met1 |
| _15686_ | 1.26 | met3 |
| net899 | 1.17 | met3 |

## Effect on the T44 conclusions

- **Time domain, antenna.** All six time runs end with 0 antenna nets, so the
  amendment is no longer needed for them. Price: +14 % to +18 % cell area.
- **Time domain, timing.** Unchanged verdicts. T-S8P1-FAST keeps passing with
  more margin (+0.20 ns vs +0.023 ns). T-serial-FAST and T-S4P1-FAST still fail
  at 100 MHz; T-S4P1-FAST improves slightly (−0.48 ns), T-serial-FAST worsens
  (−1.11 ns).
- **Time domain, deltas vs serial (SLOW).** Throughput is unchanged (+300 % for
  T-S4P1, +700 % for T-S8P1). Area deltas: +40.8 % (T-S4P1) and +47.0 %
  (T-S8P1), against +44.2 % and +48.6 % in T44. The SLOW Pareto front stays
  T-serial, T-S4P1, T-S8P1; the FAST front stays T-S8P1.
- **Frequency domain.** The trial cuts F-serial-SLOW from 117 to 8 nets and from
  5.13 to 3.11, still over the amendment (≤ 3 nets, ≤ 1.72), at +31 % area.
  F-serial-FAST does not complete routing. D7 for frequency stays not
  demonstrated with these settings.
- **Energy.** Not compared: power was not re-measured for the trial runs, and
  the T44 energy per output does not apply to them (+14 % to +18 % cell area,
  36,465 diodes in F-serial).

## Caveats

- **Sizing record.** Before this change, `run.json` copied `sizing.FP_CORE_UTIL`
  from `ppa_runs.json` (55) even when the run used another value. The trial runs
  above were made with a local version of the same overrides, so **every
  trial record in this document has a `run.json` that says 55 while its
  `overrides` list carries `FP_CORE_UTIL=45`**: the record disagrees with the
  configuration that produced it. Read `sizing.sized_instance_utilization`
  (≈ 0.45 means the die was sized at 45 %). `run --antenna-trial` now records
  the value actually applied and an `antenna_trial` flag; a re-run with it
  produces consistent records.
- **Power and energy per output** were not re-measured for the trial runs; the
  T44 values do not apply to them (more cells, diode capacitance).
- **The cell area includes the diodes** and the extra tap/decap cells of the
  larger die; it is not comparable with T44 as a pure logic cost.
- **Evidence.** The trial runs are local (`.build/ppa/`); their manifests and
  rows are not committed here.

## Decisions (T44 owner, @AndresCesana, 2026-11-02)

1. **Not adopted as the T44 baseline.** Adopting it would need every run
   re-collected with committed evidence and power re-measured at gate level,
   and it would still leave F-serial-SLOW over the bound (8 nets, 3.11), so it
   would not remove the need for an antenna rule for frequency. T44 keeps the
   amendment at 55 %, scoped as written in ppa-matrix-18 (frequency fails it;
   D7 for frequency is not demonstrated).
2. **F-serial-SLOW: no manual fix.** Hand jumpers on eight nets of one run
   break the same-configuration rule of Measurement Conditions. Under the
   baseline it is recorded as an antenna FAIL in T44.
3. **F-serial-FAST trial: recorded here as FAIL** (global routing congestion
   in antenna repair) and not re-run.
