# REQUIREMENTS — toolchain and dev environment

> Onboarding pointer, not a contract. Normative pins live in
> `docs/contracts/toolchain-gap-2.md`, `docs/contracts/openlane-env-19.md`,
> and `docs/adr/0006-systemverilog-openlane-ppa-flow.md`.

## 1. Project toolchain

| Tool | Required version | Use |
| ---- | ---------------- | --- |
| Python | `3.12.x` (`>=3.12,<3.13`) | sim venv, `pytest` |
| `numpy` | `==2.5.3` | sim (`sim/python/requirements.txt`) |
| `scipy` | `==1.18.1` | sim |
| `matplotlib` | `==3.11.2` | sim plots |
| `fxpmath` | `==0.4.10` | sim FXP model |
| `pytest` | `==9.1.1` | sim tests |
| Icarus Verilog `iverilog` + `vvp` | `>=11.0` with `-g2012` (`12.0` tested) | required RTL simulator, `rtl/*/run.sh` |
| Verilator | any recent, lint-only (`5.020` tested) | optional CI lint, DUT only |
| GTKWave | any recent | manual/debug VCD only, never CI |
| Nix | Determinate Nix 3.x | reproducible OpenLane env, never mixed with `.venv` |
| OpenLane 2 | `v2.3.10`, flow `Classic` | PPA runs (F4) |
| volare PDK | `0fe599b2afb6708d281543108caf8310912f54af` | `sky130A` PDK download |
| PDK / SCL | `sky130A` + `sky130_fd_sc_hd` | every comparable run |

## 2. Dev / repo environment (not project-specific)

| Tool | Version | Use |
| ---- | ------- | --- |
| `act` | any recent (`0.2.89` tested) | run `.github/workflows` locally |
| `pnpm` | `11.x` (`11.23.0` tested) | node package manager, commitlint alternative |
| `node` | `22.x` LTS (`22.23.2` tested) | runtime for node-based hooks |
| `convco` | any recent (recommended) | `convco check` Conventional Commits, no node needed |
| `pre-commit` | any recent 3.x (`3.6.2` tested) | repo hygiene hooks |
| `svlint` | any recent 0.9.x (`0.9.5` tested) | SystemVerilog lint complement |
| `gh` | any recent 2.x (`2.101.0` tested) | issues/PRs (`gh issue view`, `gh pr create`) |
| `git` | system | branches `type/<issue>-slug`, Conventional Commits |
| `shellcheck` / `shfmt` | any recent (recommended) | `run.sh` + `scripts/*.sh` lint/fmt |
| `yamllint` / `actionlint` | any recent (recommended) | CI YAML lint |

> Install each tool however suits your machine and make sure it is in your
> `PATH`. Prefer `cargo install convco` for commit lint (no node needed);
> `pnpm add -D @commitlint/...` is the node-based alternative.

## References

- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract, Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog + Icarus/vvp + Verilator lint-only + Classic 100MHz/10MHz-fallback.
- `CONTRIBUTING.md` — branches, Conventional Commits, PR evidence.
- `docs/plan-gantt.md` T02 — owner A+D, blocks T03.
