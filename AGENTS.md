# AGENTS.md

> Guide for agents and humans: how we work in this repo.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical 5-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo: one `CONTEXT.md` at the root + ADRs in `docs/adr/`. See `docs/agents/domain.md`.

---

## Project in 30 seconds

RRC filters (50% roll-off, 2x oversampling, 8 taps) for QPSK, in **two versions**: **time** domain and **frequency** domain. Flow: Python floating-point simulator (golden) → fixed point with SQNR ≥ 40 dB → serial RTL + vector matching → optimized RTL (unfolded / pipeline / systolic / folded) at 100 MHz (fast) or 10 MHz (slow) → best PPA trade-off → slides + Gantt.

Canonical vocabulary in `CONTEXT.md`. Hard decisions in `docs/contracts/` (accepted), recorded as ADRs in `docs/adr/`. Plan and work split in `docs/plan-gantt.md`.

## How to work here

1. **Read before touching code:** `CONTEXT.md` + ADRs for the area + `docs/plan-gantt.md`.
2. **GitHub issues:** all work enters via an issue (`gh issue create/list/view`). See `docs/agents/issue-tracker.md`.
3. **Branches:** from updated `main` → `type/<issue>-short-description` (see `CONTRIBUTING.md`).
4. **Commits:** Conventional Commits with scope (`feat(sim): ...`, `fix(rtl): ...`). No direct commits to `main`.
5. **PRs:** use the template, link `Closes #N`, require 1 review + green checks + (for RTL/sim) verification evidence.
6. **Definition of done:** see `CONTRIBUTING.md` (SQNR, vector matching, timing/PPA per phase).

## Repo layout

```text
sim/python/      golden simulator (float), fxp model, tests, SQNR measurement
sim/vectors/     golden vectors for vector matching (DO NOT edit by hand)
rtl/common/      shared coefficients and packages
rtl/time_serial/ time-domain filter, serial version
rtl/freq_serial/ frequency-domain filter, serial version
rtl/time_opt/    time-domain filter, optimized version (pipeline/systolic/...)
rtl/freq_opt/    frequency-domain filter, optimized version (unfolded/folded/...)
rtl/tb/          testbenches (with vector matching against sim/vectors)
docs/adr/        architecture decisions
docs/slides/     final presentation
docs/plan-gantt.md  phases, milestones, 4-person split
scripts/         utilities (label setup, vector generation, etc.)
```

## Useful commands

```bash
# issues
gh issue list --state open
gh issue view <n> --comments

# labels (once, see scripts/setup-labels.sh)
bash scripts/setup-labels.sh

# sim (once it exists)
python -m venv .venv && source .venv/bin/activate
pip install -r sim/python/requirements.txt
pytest sim/python -v
```
