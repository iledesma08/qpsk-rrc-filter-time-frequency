# qpsk-rrc-filter-time-frequency

Two complex 8-tap RRC filters (50% roll-off, 2x oversampling) for QPSK symbols — one in the **time domain** and one in the **frequency domain** — with a contrasted 12-row PPA optimization.

## Fixed spec (per assignment)

| Parameter | Value |
| --------- | ----- |
| Symbols | QPSK (±1 ± j), unnormalized, Es = 2 (#15) |
| Filter | RRC, α = 0.5, unit-energy, D = 3.5 samples (#13) |
| Oversampling | 2x |
| Coefficients | 8 (`rrc8-v1` artifact) |
| Versions | time (convolution) + frequency (FFT × IFFT, FFT16 forced-50% OLS, H = 8) (#14) |
| Stimulus | 1024 symbols, `default_rng(2026)`, full 2055-sample causal window (#15) |
| Golden | float64 Python (ADR-0001) |
| Fixed point | common width, SQNR ≥ 40 dB in both domains (ADR-0005, #16) |
| Vectors | packed `{Q[15:0],I[15:0]}` `.hex` + manifest + SHA-256, generated only (ADR-0004) |
| Baseline RTL | serial + 100% vector matching before optimizing (ADR-0002) |
| Opt RTL | time S×P (pipeline+systolic) + freq U (unfolded) + one folded contrast, 12-row matrix (#18) |
| Clock | 100 MHz primary; 10 MHz labeled fallback, never ranked together (ADR-0006) |
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
| A | Ignacio Ledesma | @iledesma08 | Time + infra (absent 10-15→11-08, covered pre-travel) |
| B | Juan Rondon | @JRondon23 | Frequency lane |
| C | Matias Costamagna | @matiascostamagna | Sim + FXP + vectors (sole regenerator) |
| D | Andres Cesana | @AndresCesana | PPA + close |

\* Detailed split, dates, and support roles in `docs/plan-gantt.md`; execution issues #38–#60.

Planning Project: [QPSK RRC Filter - Plan](https://github.com/users/iledesma08/projects/3). This Project tracks repository setup and Wayfinder map #1 only. Execution Project: [QPSK RRC Filter - Execution](https://github.com/users/iledesma08/projects/4) — live tracker with the 23 execution issues (#38–#60), milestones M1–M5, and `Lane`/`Phase` fields.

## Status

Contracts #13–#19 accepted (see `docs/contracts/`); execution issues #38–#60 created with owners, milestones M1–M5, and blocking edges; kickoff Mon 09-28. Live status lives in the Execution Project and milestones — measured results land in their issues (width → T21, PPA winner → T44), so this file needs no update for them.
