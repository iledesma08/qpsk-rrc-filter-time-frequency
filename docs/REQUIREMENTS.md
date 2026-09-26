# REQUIREMENTS — toolchain and dev environment

> Onboarding pointer, not a contract. Normative pins live in
> `docs/contracts/toolchain-gap-2.md`, `docs/contracts/openlane-env-19.md`,
> and `docs/adr/0006-systemverilog-openlane-ppa-flow.md`.
> This file only aggregates versions, install, and usage.
> Clocks/sizing (`CLOCK_PERIOD`, `FP_SIZING`, PDN-0185) and PPA evidence
> (`metrics.json`, STA reports, VCD/SAIF policy) are intentionally excluded
> here — see the contracts above for those.

Closes #38 (T02) partially — full DoD also needs CI/SDC/JSON/smoke below.

## 1. Project toolchain

| Tool | Required version | Use |
| ---- | ---------------- | --- |
| Python | `3.12.x` (`>=3.12,<3.13`) | sim venv, `pytest` |
| `numpy` | `==2.5.3` | sim (`sim/python/requirements.txt`) |
| `scipy` | `==1.18.1` | sim |
| `matplotlib` | `==3.11.2` | sim plots |
| `fxpmath` | `==0.4.10` | sim FXP model |
| `pytest` | `==9.1.1` | sim tests |
| Icarus Verilog `iverilog` + `vvp` | `>=11.0`, `-g2012` (verified `12.0` here) | required RTL simulator, `rtl/*/run.sh` |
| Verilator | lint-only (verified `5.020` here) | optional CI lint, DUT only |
| GTKWave | any recent | manual/debug VCD only, never CI |
| Nix | `Determinate Nix 3.21.8` | reproducible OpenLane env, never mixed with `.venv` |
| OpenLane 2 | `v2.3.10` via `~/openlane2/shell.nix`, flow `Classic` | PPA runs (F4) |
| volare PDK | `0fe599b2afb6708d281543108caf8310912f54af` | `sky130A` PDK download |
| PDK / SCL | `sky130A` + `sky130_fd_sc_hd` | every comparable run |

## 2. Dev / repo environment (not project-specific)

| Tool | Status here | Use |
| ---- | ----------- | --- |
| `act` | `0.2.89` in `~/.local/bin/act`, **not in `PATH`** by default | run `.github/workflows` locally |
| `convco` | not installed (recommended) | `convco check` Conventional Commits, no node needed |
| `pre-commit` | `3.6.2` in `/usr/bin/pre-commit` | repo hygiene hooks |
| `svlint` | `0.9.5` in `/usr/local/bin/svlint` | SystemVerilog lint complement |
| `gh` | `2.101.0` | issues/PRs (`gh issue view`, `gh pr create`) |
| `git` | system | branches `type/<issue>-slug`, Conventional Commits |
| `shellcheck` / `shfmt` | not installed (recommended) | `run.sh` + `scripts/*.sh` lint/fmt |
| `yamllint` / `actionlint` | not installed (recommended) | CI YAML lint |

> `node v18.19.1` exists at `/usr/bin/node` on this machine **without**
> `npm`/`npx`/`pnpm`/`corepack`. Prefer `cargo install convco` over a
> node-based commitlint here until node toolchain is fixed (see §3).

## 3. Install

```bash
# system sim tools (Ubuntu)
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

# act (already in ~/.local/bin on this machine, just missing from PATH)
# upstream: https://github.com/nektos/act/releases (act 0.2.89 verified)
export PATH="$HOME/.local/bin:$PATH"

# Nix binaries (present under /nix but not in PATH in minimal shells)
export PATH="/nix/var/nix/profiles/default/bin:$PATH"

# persist both for interactive shells
grep -q '.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
grep -q '/nix/var/nix' ~/.bashrc || echo 'export PATH="/nix/var/nix/profiles/default/bin:$PATH"' >> ~/.bashrc

# convco (recommended over commitlint here: single Rust binary, no node needed)
cargo install convco
# alternative if you prefer the node stack (needs npm/pnpm first):
# pnpm add -D @commitlint/cli @commitlint/config-conventional

# repo hygiene (recommended)
pip install pre-commit yamllint
# shellcheck/shfmt/actionlint via apt or GitHub releases:
sudo apt-get install -y shellcheck shfmt 2>/dev/null || true
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

## 5. Verified on this machine (2026-09-26)

| Check | Result |
| ----- | ------ |
| `python3.12 --version` | `Python 3.12.3` |
| `iverilog -V` | `Icarus Verilog version 12.0 (stable)` — satisfies `>=11.0` |
| `verilator --version` | `Verilator 5.020 2024-01-01` |
| `~/.local/bin/act --version` | `act version 0.2.89` (needs `PATH` export) |
| `pre-commit --version` | `3.6.2` |
| `svlint --version` | `0.9.5` |
| `node --version` | `v18.19.1` (no `npm`/`npx`/`pnpm` alongside) |
| `nix-shell` | `/nix/var/nix/profiles/default/bin/nix-shell` (needs `PATH` export) |
| `~/openlane2` | clone present |
| `gh --version` | `2.101.0` |

## References

- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract, Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog + Icarus/vvp + Verilator lint-only + Classic 100MHz/10MHz-fallback.
- `CONTRIBUTING.md` — branches, Conventional Commits, PR evidence.
- `docs/plan-gantt.md` T02 — owner A+D, blocks T03.
