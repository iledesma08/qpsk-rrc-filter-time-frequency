# Toolchain Gap Research

Research ticket: [#2](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/2)

Date: 2026-09-21

Scope: unblock F1 now, and define the exact simulator and PPA contract for F3-F5. This note does not add infrastructure.

## Decision Summary

- Use Python 3.12.x for the simulator environment.
- Pin the Python packages below in `sim/python/requirements.txt` when the implementation ticket lands.
- Keep Icarus Verilog plus `vvp` as the required RTL simulator, following the course.
- Add Verilator as a separate, optional lint-only CI job. It complements Icarus and does not replace it.
- Use the OpenLane 2 `Classic` flow with `sky130A` and `sky130_fd_sc_hd` for the F4 PPA runs. OpenLane 2 should be installed through its Nix shell, not mixed with the simulator virtualenv.
- Treat area, timing, and power as separate reported measurements. Do not claim dynamic power from an unannotated power report.

## Course Baseline

The course repository was inspected through `gh api` at main commit [`c7d9c32a6460be9c512186f8e112fb4661da92a9`](https://github.com/iledesma08/rtl-marvell-formation-course/commit/c7d9c32a6460be9c512186f8e112fb4661da92a9). Its [recursive tree](https://api.github.com/repos/iledesma08/rtl-marvell-formation-course/git/trees/c7d9c32a6460be9c512186f8e112fb4661da92a9?recursive=1) contains no OpenLane configuration or Sky130 flow directory.

- The Mod2 register exercise runs `iverilog -g2012 -o sim.out tb_reg_ce.sv reg_ce.sv`, then `vvp sim.out`; it points to `gtkwave tb_reg_ce.vcd` for wave inspection. Source: [`mod2/ej2_8bit_reg/run.sh`](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod2/ej2_8bit_reg/run.sh).
- The Mod3 fixed-point exercise runs `python3 model.py`, then compiles each testbench with `iverilog -g2012` and runs it with `vvp`. Source: [`mod3/ej3_truncado_redondeo_saturacion/run.sh`](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod3/ej3_truncado_redondeo_saturacion/run.sh).
- The Mod3 model uses `fxpmath.Fxp` and writes input and expected-output `.hex` files for `$readmemh`-based self-checking testbenches. Sources: [`model.py`](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod3/ej3_truncado_redondeo_saturacion/model.py) and [`tutorial-fxpmath.md`](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod3/tutorial-fxpmath.md).
- The Mod6 folding exercise keeps the same Icarus/vvp flow, then uses Yosys to count inferred resources and documents GTKWave for the generated VCD. Source: [`mod6/ej3_folding/run.sh`](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod6/ej3_folding/run.sh).

The course command contract for this repository is therefore:

```bash
python3 model.py                         # when the test has generated vectors
iverilog -g2012 -o sim.out <tb>.sv <rtl>.sv
vvp sim.out
gtkwave <tb>.vcd                         # optional, manual/debug only
```

## Python Recommendation

The following versions were the current non-yanked versions reported by PyPI metadata on 2026-09-21:

```text
numpy==2.5.3
scipy==1.18.1
matplotlib==3.11.2
fxpmath==0.4.10
pytest==9.1.1
```

Use Python `>=3.12,<3.13`. NumPy 2.5.3 and SciPy 1.18.1 require Python 3.12 or newer; Matplotlib 3.11.2 requires 3.11 or newer; pytest 9.1.1 requires 3.10 or newer; fxpmath 0.4.10 requires 3.7 or newer and depends on NumPy. Sources: [NumPy metadata](https://pypi.org/pypi/numpy/json), [SciPy metadata](https://pypi.org/pypi/scipy/json), [Matplotlib metadata](https://pypi.org/pypi/matplotlib/json), [pytest metadata](https://pypi.org/pypi/pytest/json), and [fxpmath metadata](https://pypi.org/pypi/fxpmath/json).

Recommended local setup once the requirements file exists:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r sim/python/requirements.txt
python -m pytest sim/python -v
```

The package pins are a reproducible course baseline, not a promise that future package updates are unnecessary. Update them together after a deliberate simulator verification run.

## Verilator Recommendation

Yes: add Verilator as an optional CI lint complement, not as the normative simulator.

Use a separate job over RTL sources only, with the actual top module named explicitly:

```bash
verilator --lint-only -sv -Wall -Wno-fatal \
  --top-module <dut> \
  rtl/common/*.sv rtl/<variant>/*.sv
```

`--lint-only` checks without producing simulation output, `-Wall` enables style warnings, and `-Wno-fatal` prevents warnings from turning this optional job into a second simulator gate. Verilator documents all three options in its executable reference. Source: [Verilator arguments](https://verilator.org/guide/latest/exe_verilator.html).

Keep the required CI path as Python tests plus Icarus compile/run and vector matching. Do not lint testbenches in the first job: testbenches may use delay controls and VCD system tasks that are not part of the DUT lint contract. Add `--timing` only if a later Verilator testbench job is intentionally introduced. Promote selected Verilator warnings to required checks only after the first RTL baseline is clean.

This is consistent with OpenLane 2 itself, whose documented Classic run contains a `verilator-lint` step, while the course still uses Icarus/vvp for simulation. Source: [OpenLane 2 newcomer flow layout](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html).

## OpenLane 2 + Sky130 Minimal PPA Flow

### Installation and smoke test

OpenLane 2 recommends Nix for a reproducible tool environment. The documented setup is:

```bash
git clone https://github.com/efabless/openlane2.git ~/openlane2
nix-shell --pure ~/openlane2/shell.nix
openlane --log-level ERROR --condensed --show-progress-bar --smoke-test
```

The smoke test also downloads the Sky130 PDK. Do not install OpenLane tools into `.venv`. Sources: [OpenLane installation overview](https://openlane2.readthedocs.io/en/stable/getting_started/installation_overview.html) and [Nix/newcomer setup](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html).

### One run per RTL variant and target

Create one OpenLane design directory/configuration per top-level RTL variant. The minimal JSON config needs these four variables:

```json
{
  "DESIGN_NAME": "<dut>",
  "VERILOG_FILES": "dir::src/*.sv",
  "CLOCK_PORT": "clk",
  "CLOCK_PERIOD": 10.0
}
```

The actual source list must include only the DUT and shared RTL, never the testbench or generated simulation vectors. The documented config uses JSON and `dir::` paths; the four variables above are the minimum required variables.

Run explicitly against the same technology for every comparison:

```bash
openlane --flow Classic \
  --pdk sky130A \
  --scl sky130_fd_sc_hd \
  openlane/<variant>/config.json
```

Use `CLOCK_PERIOD: 10.0` ns for the 100 MHz target and `CLOCK_PERIOD: 100.0` ns for the 10 MHz target. Do not compare a 100 MHz candidate against a 10 MHz candidate without recording the target as part of the result. OpenLane documents `sky130A` as the fully qualified PDK name and `sky130_fd_sc_hd` as the Sky130 default SCL; the SkyWater documentation identifies `sky130_fd_sc_hd` as the high-density digital standard-cell library. Sources: [OpenLane design configuration](https://openlane2.readthedocs.io/en/stable/reference/configuration.html), [OpenLane PDK/SCL selection](https://openlane2.readthedocs.io/en/stable/usage/about_pdks.html), and [SkyWater standard-cell libraries](https://skywater-pdk.readthedocs.io/en/main/contents/libraries/foundry-provided.html).

Pin the toolchain for every F4 run: `iverilog --version` must report 11.0 or
newer, compiled with `-g2012`; DUT sources use the synthesizable SV subset
allowlist (no `interface`, no `randomize`, no `assert property` in the DUT —
testbench-only constructs stay out of `VERILOG_FILES`); OpenLane v2.3.10 via
Nix with volare `0fe599` (`0fe599b2afb6708d281543108caf8310912f54af`),
`sky130A`, `sky130_fd_sc_hd`, `Classic` flow (see
`docs/contracts/openlane-env-19.md`).

Provide the same SDC template to all variants via `PNR_SDC_FILE` and
`SIGNOFF_SDC_FILE`, identical except the clock period. Template:

```tcl
create_clock -name clk -period 10.000 [get_ports clk]
# 10 MHz fallback: create_clock -name clk -period 100.000 [get_ports clk]
set_input_delay 2.0 -clock clk [all_inputs]
set_output_delay 2.0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_n]
set_max_transition 1.5 [current_design]
set_max_fanout 16 [current_design]
```

`PNR_SDC_FILE` and `SIGNOFF_SDC_FILE` point to copies identical except the
`create_clock` period (10.0 ns for 100 MHz, 100.0 ns for the labelled 10 MHz
fallback). Size each die per `docs/contracts/ppa-matrix-18.md`: 50-60% core
utilization (target ~55%), floor `max(sized-for-target, 200x200 um)` for
PDN-0185; record die area, core area, and utilization per row. OpenLane
explicitly places responsibility for custom input/output constraints on the
designer. Source: [OpenLane timing closure](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html).

### Required PPA evidence

For each completed run, archive or link these outputs from the run directory. Step numbers are version-dependent, so match by step name rather than number:

- `final/metrics.json` and `final/metrics.csv`: canonical final metrics for the run. Record die area, core area, and utilization per row plus cell/design area in square micrometres and the final design health metrics. Source: [OpenLane final results](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html).
- `*-openroad-stapostpnr/summary.rpt`: multi-corner signoff summary. Record setup and hold worst slack, TNS, and violation counts.
- The per-corner `*-openroad-stapostpnr/<corner>/max.rpt` and `min.rpt`: the critical setup and hold paths used to explain the summary.
- The per-corner `checks.rpt`: max-capacitance, max-slew, fanout, unconstrained-path, and related timing checks.
- The per-corner `power.rpt`: report the power value and corner, but also record the VCD/SAIF file name and annotation coverage; report core + clock-tree power and exclude any IO split.
- DRC, LVS, antenna, and flow status: a PPA number is not an implementation pass if signoff checks failed.

OpenLane documents `summary.rpt`, `max.rpt`, `min.rpt`, `checks.rpt`, and `power.rpt` under the post-PnR STA step. OpenROAD documents `report_design_area` for area and accepts VCD or SAIF activity as inputs to STA power analysis. Sources: [OpenLane signoff reports](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html), [OpenLane timing reports](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html), [OpenROAD area reporting](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html), and [OpenSTA inputs](https://openroad.readthedocs.io/en/latest/main/src/sta/README.html).

Report `fmax` from the same signoff corner and constraint as timing. For a single clock, a useful derived value is:

```text
fmax_MHz = 1000 / critical_path_delay_ns
```

Take `critical_path_delay_ns` from the signoff critical path in `max.rpt`, or from `CLOCK_PERIOD_ns - signed_setup_slack_ns` when the report provides signed slack. Also retain the raw period and slack; the derived value must not hide a negative slack or a corner mismatch.

Power is the main caveat. A `power.rpt` generated without VCD/SAIF activity is not a measured workload-dependent dynamic-power result. Annotate with a VCD/SAIF from the full 257-block canonical workload (256 steady-state + 1 tail-flush) after warm-up; until that representative activity from the RTL testbench is annotated, label the number as an unannotated/static estimate and use it only for like-for-like comparison. Do not rank variants by power using different activity assumptions.

## Exact Implementation Checklist

This is the recommended checklist for the follow-up implementation work; it is intentionally not implemented by this ticket.

- Add `sim/python/requirements.txt` with the five pinned packages above.
- Use Python `>=3.12,<3.13` and verify `python -m pytest sim/python -v`.
- Install `iverilog`, `vvp`, and `gtkwave`; require Icarus/vvp for RTL simulation and keep GTKWave manual-only.
- Add `rtl/time_serial/run.sh`, `rtl/freq_serial/run.sh`, `rtl/time_opt/run.sh`, and `rtl/freq_opt/run.sh`. Each script must compile the DUT plus its testbench with `iverilog -g2012`, run `vvp`, and return nonzero on a mismatch.
- Make each vector generator the sole writer of `sim/vectors/`; the RTL testbench loads vectors with `$readmemh` or the selected documented format.
- Add an optional `verilator-lint` CI job using `verilator --lint-only -sv -Wall -Wno-fatal` over DUT sources only.
- Keep required CI to Python tests, Icarus compile/run, and vector matching; do not make Verilator replace Icarus.
- Before F4, install OpenLane 2 through Nix and pass its Sky130 smoke test.
- Add one OpenLane JSON config per top-level variant, excluding testbenches, and run with `sky130A` plus `sky130_fd_sc_hd`.
- Choose `CLOCK_PERIOD=10.0` ns for 100 MHz or `100.0` ns for 10 MHz per lane, and record that choice with every PPA result.
- For every PPA run, retain final metrics, post-PnR STA summary and critical reports, power report plus activity status, and DRC/LVS/antenna status.
- Add representative VCD/SAIF activity before using power as a ranking axis.
- Put the final area/fmax/power rows in the PPA table only after vector matching is already 100 percent, as required by [ADR 0002](../adr/0002-serial-rtl-before-optimization.md).

## Sources

- [Course repository at inspected commit](https://github.com/iledesma08/rtl-marvell-formation-course/tree/c7d9c32a6460be9c512186f8e112fb4661da92a9)
- [OpenLane 2 stable documentation](https://openlane2.readthedocs.io/en/stable/)
- [SkyWater SKY130 PDK documentation](https://skywater-pdk.readthedocs.io/en/main/)
- [OpenROAD documentation](https://openroad.readthedocs.io/en/latest/)
- [Verilator executable reference](https://verilator.org/guide/latest/exe_verilator.html)
- [PyPI project metadata: NumPy](https://pypi.org/pypi/numpy/json)
- [PyPI project metadata: SciPy](https://pypi.org/pypi/scipy/json)
- [PyPI project metadata: Matplotlib](https://pypi.org/pypi/matplotlib/json)
- [PyPI project metadata: fxpmath](https://pypi.org/pypi/fxpmath/json)
- [PyPI project metadata: pytest](https://pypi.org/pypi/pytest/json)
