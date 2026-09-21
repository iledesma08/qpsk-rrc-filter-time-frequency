## Description

<!-- What changes and why. 2-4 lines. Use CONTEXT.md vocabulary. -->

Closes #<!-- issue number -->

## Type

<!-- Check: feat / fix / docs / sim / rtl / verif -->

## How it was tested

<!-- Mandatory. Delete what does not apply. -->
- [ ] `pytest sim/python -v` is green
- [ ] Measured SQNR: _____ dB (≥ 40 dB required if it touches fxp)
- [ ] Vector matching: _____ (pass/fail, attach log)
- [ ] Synthesis/timing: fmax _____ MHz / area _____ / power _____ (if it touches opt RTL)

## Evidence

<!-- Paste commands + output, or link artifacts. No merge of sim/rtl without evidence. -->

```text

```

## Checklist

- [ ] I read `CONTEXT.md` and use its terms
- [ ] Branch from updated `main`, one issue per branch
- [ ] Conventional Commits (`type(scope): ...`)
- [ ] No hand-generated vectors or secrets committed
- [ ] Updated docs/plan-gantt.md if scope or dates changed
- [ ] If it contradicts an ADR, I flagged it explicitly
