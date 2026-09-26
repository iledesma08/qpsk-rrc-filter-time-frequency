# REQUIREMENTS — toolchain and dev environment

> Onboarding pointer, not a contract. Normative pins live in
> `docs/contracts/toolchain-gap-2.md`, `docs/contracts/openlane-env-19.md`,
> and `docs/adr/0006-systemverilog-openlane-ppa-flow.md`.
> This file only aggregates required versions, install, and usage.
> Clocks/sizing (`CLOCK_PERIOD`, `FP_SIZING`, PDN-0185) and PPA evidence
> (`metrics.json`, STA reports, VCD/SAIF policy) are intentionally excluded
> here — see the contracts above for those.

## 1. Project toolchain

| Tool | Required version | Use |
| ---- | ---------------- | --- |
| Python | `3.12.x` (`>=3.12,<3.13`) | sim venv, `pytest` |
| `numpy` | `==2.5.3` | sim (`sim/python/requirements.txt`) |
| `scipy` | `==1.18.1` | sim |
| `matplotlib` | `==3.11.2` | sim plots |
| `fxpmath` | `==0.4.10` | sim FXP model |
| `pytest` | `==9.1.1` | sim tests |
| Icarus Verilog `iverilog` + `vvp` | `>=11.0` with `-g2012` | required RTL simulator, `rtl/*/run.sh` |
| Verilator | any recent, lint-only | optional CI lint, DUT only |
| GTKWave | any recent | manual/debug VCD only, never CI |
| Nix | Determinate Nix 3.x | reproducible OpenLane env, never mixed with `.venv` |
| OpenLane 2 | `v2.3.10`, flow `Classic` | PPA runs (F4) |
| volare PDK | `0fe599b2afb6708d281543108caf8310912f54af` | `sky130A` PDK download |
| PDK / SCL | `sky130A` + `sky130_fd_sc_hd` | every comparable run |

## 2. Dev / repo environment (not project-specific)

| Tool | Version | Use |
| ---- | ------- | --- |
| `act` | any recent (`0.2.x` tested) | run `.github/workflows` locally |
| `pnpm` | `11.x` | node package manager, commitlint alternative |
| `node` | `22.x` LTS | runtime for node-based hooks |
| `convco` | any recent (recommended) | `convco check` Conventional Commits, no node needed |
| `pre-commit` | any recent 3.x | repo hygiene hooks |
| `svlint` | any recent 0.9.x | SystemVerilog lint complement |
| `gh` | any recent 2.x | issues/PRs (`gh issue view`, `gh pr create`) |
| `git` | system | branches `type/<issue>-slug`, Conventional Commits |
| `shellcheck` / `shfmt` | any recent (recommended) | `run.sh` + `scripts/*.sh` lint/fmt |
| `yamllint` / `actionlint` | any recent (recommended) | CI YAML lint |

> Install each tool however suits your machine and make sure it is in your
> `PATH`. Prefer `cargo install convco` for commit lint (no node needed);
> `pnpm add -D @commitlint/...` is the node-based alternative.

## 3. Install

```bash
# system sim tools (Ubuntu example)
sudo apt-get update && sudo apt-get install --no-install-recommends -y \
  iverilog verilator gtkwave

# python sim env (never install OpenLane tools into .venv)
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r sim/python/requirements.txt

# Nix (Determinate) + OpenLane 2 — separate from .venv
# See https://openlane2.readthedocs.io/en/stable/getting_started/installation_overview.html
git clone https://github.com/efabless/openlane2.git ~/openlane2
nix-shell --pure ~/openlane2/shell.nix --run "openlane --smoke-test"
# smoke also downloads the Sky130 PDK via volare; keep the log as evidence

# act — https://github.com/nektos/act/releases — ensure in PATH
act --version

# pnpm + node — https://pnpm.io/installation — ensure in PATH
pnpm --version
node --version

# convco (recommended: single binary, no node needed)
cargo install convco
# node-based alternative:
# pnpm add -D @commitlint/cli @commitlint/config-conventional

# repo hygiene (recommended)
pip install pre-commit yamllint
# shellcheck/shfmt/actionlint via apt or GitHub releases
```

## 4. Usage

```bash
# sim
source .venv/bin/activate
python -m pytest sim/python -v
bash scripts/check-vectors.sh

# RTL smoke (required path: Icarus/vvp, nonzero on mismatch)
bash rtl/run.sh
bash rtl/time_serial/run.sh
bash rtl/freq_serial/run.sh
bash rtl/time_opt/run.sh
bash rtl/freq_opt/run.sh
# GTKWave manual only:
# gtkwave <tb>.vcd

# Verilator lint-only, DUT only (never TBs, never vectors)
verilator --lint-only -sv -Wall -Wno-fatal \
  --top-module time_serial_filter \
  rtl/common/*.sv rtl/time_serial/*.sv
# repeat with freq_serial_filter / time_opt_filter / freq_opt_filter

# OpenLane smoke + per-variant run (F4; committed even if unrun per syn-commit rule)
nix-shell --pure ~/openlane2/shell.nix --run "openlane --smoke-test"
nix-shell --pure ~/openlane2/shell.nix --run \
  "openlane --pdk sky130A --scl sky130_fd_sc_hd --flow Classic openlane/<variant>/config.json"

# local CI
act -l
act -j sim
act -j rtl
act -j verilator-lint

# commits (CONTRIBUTING.md: type(scope): imperative, English)
# types: feat|fix|docs|test|refactor|chore|sim|rtl
# scopes: sim|rtl|docs|repo|tb|time|freq
convco check --from origin/main --to HEAD
pre-commit run --all-files
```

Branch/PR reminder: `git checkout main && git pull && git checkout -b chore/38-...`,
one branch per issue, no direct commits to `main`, PR `Closes #N` + 1 review +
green checks + evidence (`pytest` + `vvp` + smoke logs).

## 5. Check your installation

| Check | Expect |
| ----- | ------ |
| `python3.12 --version` | `3.12.x` |
| `python -m pip freeze \| grep -E "numpy\|scipy\|matplotlib\|fxpmath\|pytest"` | pins from `sim/python/requirements.txt` |
| `iverilog -V` | `>= 11.0` |
| `verilator --version` | any recent |
| `act --version` | any recent |
| `pnpm --version` | `11.x` |
| `node --version` | `22.x` |
| `pre-commit --version` / `svlint --version` / `gh --version` | any recent |
| `nix-shell --version` | Nix 3.x |
| `openlane --smoke-test` (inside `nix-shell --pure ~/openlane2/shell.nix`) | `Smoke test passed` |

## References

- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract, Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog + Icarus/vvp + Verilator lint-only + Classic 100MHz/10MHz-fallback.
- `CONTRIBUTING.md` — branches, Conventional Commits, PR evidence.
- `docs/plan-gantt.md` T02 — owner A+D, blocks T03.
