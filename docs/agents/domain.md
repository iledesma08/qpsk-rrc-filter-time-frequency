# Domain Docs

How engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read

- **`CONTEXT.md`** at the repo root.
- **`docs/adr/`**: read the ADRs touching the area you are about to work in.

If any of these files don't exist, **proceed silently**. Don't report their absence; don't suggest creating them upfront. The `/domain-modeling` skill (via `/grill-with-docs`) creates them lazily when a term or decision actually gets resolved.

## File structure

Single-context repo (this repo):

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-python-float-golden-simulator.md
│   └── 0002-...
└── sim/ rtl/
```

## Use the glossary vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis, test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the needed concept isn't in the glossary, that's a signal: either you're inventing language the project doesn't use (reconsider), or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, flag it explicitly instead of silently overriding:

> _Contradicts ADR-0001 (Python float golden simulator), but worth reopening because…_
