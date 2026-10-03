# qpsk-rrc-filter-time-frequency

Two complex 8-tap RRC filters (50% roll-off, 2x oversampling) for QPSK symbols, one in the **time domain** and one in the **frequency domain**, with six base PPA architectures and paired target runs. The twelve-architecture matrix is extension-only, per the [PPA contract](docs/contracts/ppa-matrix-18.md).

## Project spec

The assignment fixes the filter and deliverables. The linked contracts also record the team's numeric, interface, and measurement decisions.

| Parameter | Value |
| --------- | ----- |
| Symbols | QPSK (±1 ± j), unnormalized, Es = 2 (#15) |
| Filter | RRC, α = 0.5, unit-energy, D = 3.5 samples (#13) |
| Oversampling | 2x |
| Coefficients | 8 (`rrc8-v1` artifact) |
| Versions | time (convolution) + frequency (FFT -> response multiply -> IFFT, FFT16 forced-50% OLS, H = 8) (#14) |
| Stimulus | 1024 symbols, `default_rng(2026)`, full 2055-sample causal window (#15) |
| Golden | float64 Python (ADR-0001) |
| Fixed point | Production `Q2.14` (`W_common=16`); diagnostic bit sweep retained; measured SQNR ≥ 40 dB in both domains (ADR-0005, #16) |
| Vectors | packed `{Q[15:0],I[15:0]}` `.hex` + manifest + SHA-256, generated only (ADR-0004) |
| Baseline RTL | serial + 100% vector matching before optimizing (ADR-0002) |
| Opt RTL | Base: two serials + time `S4P1/S8P1` + frequency `U4/U8`; additional pipeline-depth and folded comparisons only on extension (#18) |
| Clock | Serial main targets: SLOW 10 MHz; optimized main targets: FAST 100 MHz. Prepare both target runs per architecture; compare PPA at matched targets (ADR-0006). |
| Deliverables | best PPA + comparison slides + 4-person Gantt |

The production base uses ordinary signed RTL arithmetic, one validated fixed-
coefficient path, a conservative 35-bit time accumulator and frequency FFT A.
Custom Booth, alternate ROMs, narrower accumulators, FFT B and truncation/wrap
comparisons are optional experiments, not delivery gates. Extra architecture
variants, Q1.15 sensitivity and AWGN/BER/full-link analysis are outside the base.
See the [scope levels in the plan](docs/plan-gantt.md) for activation rules.

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
docs/contracts/  frozen decision contracts backing the ADRs (#13–#19, #35)
docs/slides/       final presentation
docs/plan-gantt.md phases, milestones, 4-way split
scripts/          repo utilities (labels, checks)
```

## Workflow

1. Read `AGENTS.md` + `CONTEXT.md` + `docs/plan-gantt.md`.
2. Everything via issue → `type/<issue>-description` branch → PR with `Closes #N` → 1 review → squash into `main`.
3. Phases: float (T10–T13) → fxp + SQNR (T20–T22) → serial + vector matching (T30–T33) → opt PPA (T40–T44) → slides (T50–T51).
4. Triage `needs-triage` → `ready-for-human`; learning gate (own-words design, recorded learning, test evidence, explain-ability) checked at review.
5. Conventions in `CONTRIBUTING.md`.

## Team (4)

| Person | Member | GitHub | Role |
| ------ | ------ | ------ | ---- |
| A | Ignacio Ledesma | @iledesma08 | Pre-travel coefficients, stimulus, time golden, shared infra and streaming skeleton; meetings via Zoom during travel |
| B | Juan Rondon | @JRondon23 | Frequency lane |
| C | Matias Costamagna | @matiascostamagna | FXP + vectors (sole regenerator) + time RTL lane + activity/evidence support |
| D | Andres Cesana | @AndresCesana | PPA + close |

Detailed split, travel dates, and support roles in [the execution plan](docs/plan-gantt.md); execution issues #38–#60 plus shared prerequisite #67.

Planning Project: [QPSK RRC Filter - Plan](https://github.com/users/iledesma08/projects/3). This Project tracks repository setup and Wayfinder map #1 only. Execution Project: [QPSK RRC Filter - Execution](https://github.com/users/iledesma08/projects/4) is the live tracker for execution issues and shared prerequisites, milestones M1–M5, and `Lane`/`Phase` fields.

## Status

The accepted contracts and their amendments are indexed in [docs/contracts/](docs/contracts/README.md). Live status lives in the Execution Project and milestones; measured results land in their issues (Q2.14 validation and precision frontier -> T21, PPA conclusion -> T44). Planned delivery and checkpoint dates live in the execution plan.
