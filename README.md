# qpsk-rrc-filter-time-frequency

Two complex 8-tap RRC filters (50% roll-off, 2x oversampling) for QPSK symbols — one in the **time domain** and one in the **frequency domain** — with a contrasted PPA optimization.

## Fixed spec (per assignment)

| Parameter | Value |
| --------- | ----- |
| Symbols | QPSK (±1 ± j) |
| Filter | RRC, α = 0.5 |
| Oversampling | 2x |
| Coefficients | 8 |
| Versions | time (convolution) + frequency (FFT × IFFT) |
| Golden | floating-point Python |
| Fixed point | SQNR ≥ 40 dB |
| Baseline RTL | serial + vector matching vs golden |
| Opt RTL | unfolded / pipeline / systolic / folded or mixed |
| Clock | 100 MHz (fast) / 10 MHz (slow) |
| Deliverables | best PPA + comparison slides + 4-person Gantt |

## Layout

```text
sim/python/        golden float, fxp model, tests, SQNR
sim/vectors/       golden vectors (generated, NOT by hand)
rtl/common/        shared coefficients and packages
rtl/time_serial/   time-domain filter, serial
rtl/freq_serial/   frequency-domain filter, serial
rtl/time_opt/      time-domain filter, optimized
rtl/freq_opt/      frequency-domain filter, optimized
rtl/tb/            testbenches with vector matching
docs/adr/          decisions (see ADRs)
docs/slides/       final presentation
docs/plan-gantt.md phases, milestones, 4-way split
```

## Workflow

1. Read `AGENTS.md` + `CONTEXT.md` + `docs/plan-gantt.md`.
2. Everything via issue → `type/<issue>-description` branch → PR with `Closes #N` → 1 review → squash into `main`.
3. Phases: float → fxp (SQNR) → serial + vector matching → opt (PPA) → slides.
4. Conventions in `CONTRIBUTING.md`.

## Team (4)

| Person | Member | GitHub | Provisional role* |
| ------ | ------ | ------ | ----------------- |
| A | Ignacio Ledesma | @iledesma08 | Time lane |
| B | Juan Rondon | @JRondon23 | Frequency lane |
| C | Matias Costamagna | @matiascostamagna | Simulator + FXP |
| D | Andres Cesana | @AndresCesana | PPA + close |

\* See the detailed split in `docs/plan-gantt.md`. Fill in this table in the first PR.

Planning Project: [QPSK RRC Filter - Plan](https://github.com/users/iledesma08/projects/3). This Project tracks repository setup and Wayfinder map #1 only. The execution Project will be created with Wayfinder map #2; `docs/plan-gantt.md` is the setup milestone snapshot.

## Status

🚧 Freshly organized repo (Phase 0). See milestones in `docs/plan-gantt.md`.
