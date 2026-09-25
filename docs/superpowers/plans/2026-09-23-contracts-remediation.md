# Contracts Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all doc-to-doc contradictions on docs/12-contracts-folder.

**Architecture:** Docs-only. Accepted contracts in docs/contracts/ are normative; research reports become history; new single manifest schema; same-util sizing with PDN floor.

**Tech Stack:** Markdown, OpenLane2 Classic sky130A sky130_fd_sc_hd, Icarus -g2012, Python 3.12 numpy==2.5.3 scipy==1.18.1.

**Spec:** Professor brief (8-tap RRC a=0.5 2x QPSK, float->FXP SQNR>=40dB->serial+matching->opt unfolded/pipeline/systolic/folded, 100MHz/10MHz, slides+Gantt) + branch docs/12-contracts-folder.

## Global Constraints

- QPSK I,Q in {+1,-1} unnormalized, never renormalize silently.
- RRC alpha=0.5 N=8 sps=2 grid t[n]=(n-(N-1)/2)/sps sum(h^2)=1 D=3.5.
- SQNR=10log10(sum|y_float|^2/sum|y_float-y_fxp|^2) >=40dB both domains, rtol=1e-10 atol=1e-12.
- Packed {Q[15:0],I[15:0]} $readmemh SHA256 never hand-edit.
- 100MHz CLOCK_PERIOD=10ns primary, 10MHz=100ns labelled fallback, never mixed.
- Conventional Commits type/<issue>-desc, no direct main, 1 review.
- Same-util sizing: max(sized-for-55%, 200x200 PDN floor).
- No Spanish draft.

---

### Task 1: Fix stale coef format in stimulus manifest

**Files:**
- Modify: `docs/contracts/qpsk-stimulus-15.md:210-218`
- Check: `docs/contracts/fxp-policy-16.md:21-23,178-187`, `docs/contracts/rrc-coefficient-contract-13.md:195-204`

**Interfaces:**
- Consumes: FXP D2 common Q2.(W-2).
- Produces: Correct coefficient_scale string for Task 6.

- [ ] **Step 1: Verify stale line**
Run: `grep -n coefficient_scale docs/contracts/qpsk-stimulus-15.md docs/contracts/fxp-policy-16.md`
Expected: stimulus Q1.15 vs policy Q2.14.

- [ ] **Step 2: Edit manifest**
Replace `coefficient_scale_16bit: Q1.15` with `coefficient_scale_16bit: Q2.14` plus line `coefficient_scale_sensitivity: Q1.15 (phase E only, never folded into common-width claim)`.

- [ ] **Step 3: Verify**
Run: `grep -rn Q1.15 docs/contracts/ | grep -v sensitivity | grep -v phase.E` should show only history rows.

- [ ] **Step 4: Commit**
```bash
git add docs/contracts/qpsk-stimulus-15.md
git commit -m "docs(stim): fix coef scale to common Q2.14 per FXP D2"
```

### Task 2: Fix freq block count 256->257

**Files:**
- Modify: `docs/contracts/ppa-matrix-18.md:223-234`
- Check: `docs/contracts/frequency-block-contract-14.md:169-183`, `docs/contracts/qpsk-stimulus-15.md:160-162`

**Interfaces:**
- Consumes: Full causal 2055 window.
- Produces: Correct block count for Task 8 VCD scope.

- [ ] **Step 1: Reproduce math**
`L=2048 M=8 full=2055 blocks=ceil(2055/8)=257`.

- [ ] **Step 2: Edit workload**
Replace `256 blocks of 8 valid outputs (2048 input samples at hop 8)` with `257 blocks (256 steady-state +1 tail-flush, 2055 causal outputs), input 2048 + zero-pad to cover S+M-2 per #14, trim to valid_len=2055`. Add `Report steady-state II on first 256, latency split fill vs tail, VCD covers all 257`.

- [ ] **Step 3: Commit**
```bash
git add docs/contracts/ppa-matrix-18.md
git commit -m "docs(ppa): fix freq block count to 257 with tail flush"
```

### Task 3: Demote research docs

**Files:**
- Modify: `docs/contracts/README.md:16-20`, prepend banner to `docs/contracts/ppa-experiment-matrix-18.md:1-10`, `docs/contracts/fxp-common-width-16.md:1-10`

- [ ] **Step 1: Update README** to `Research report — historical, superseded fields in Resolution Status; normative is ppa-matrix-18.md / fxp-policy-16.md`.
- [ ] **Step 2: Add banner** `> HISTORICAL RESEARCH — not normative. Accepted decisions live in ppa-matrix-18.md / fxp-policy-16.md. See Resolution Status. Do not implement workload/OLS wording from this file.` to both research files.
- [ ] **Step 3: Commit**
```bash
git add docs/contracts/README.md docs/contracts/ppa-experiment-matrix-18.md docs/contracts/fxp-common-width-16.md
git commit -m "docs(repo): mark research reports historical"
```

### Task 4: Repair ADR vs contracts split

**Files:**
- Modify: `docs/adr/0001-python-float-golden-simulator.md`, `0002-serial-rtl-before-optimization.md`, `0004-packed-external-vectors.md`, `0005-common-sqnr-contract.md`, `0006-systemverilog-openlane-ppa-flow.md`, `AGENTS.md:25`

- [ ] **Step 1: Add Status+pointer to each ADR** e.g. 0004 append `**Status:** accepted, extended by contracts. Normative manifest: qpsk-stimulus-15.md + fxp-policy-16.md + rtl-streaming-17.md + vector-manifest-schema.md. This ADR defines only packing {Q[15:0],I[15:0]} + $readmemh + hash.`
- [ ] **Step 2: Fix AGENTS.md** `Hard decisions in docs/adr/` → `Hard decisions in docs/contracts/ (accepted), recorded as ADRs in docs/adr/`.
- [ ] **Step 3: Commit**
```bash
git add docs/adr/ AGENTS.md
git commit -m "docs(repo): point ADRs to normative contracts"
```

### Task 5: Clarify SPC vs II vs ready

**Files:**
- Modify: `docs/contracts/rtl-streaming-17.md:192-201,213-229`, `docs/contracts/ppa-matrix-18.md:171-197`, `CONTEXT.md:79-81`

- [ ] **Step 1: Document** `SPC is interface width. II measured from handshake. Serial S=1 II=8: ready_o deasserts 7/8 cycles. Canonical vectors drive valid_i=1; DUT backpressures. ready_o=1 always only for fully-parallel variants.`
- [ ] **Step 2: CONTEXT gloss** append `(II depends on S; S=1 => II=8)` + pointer.
- [ ] **Step 3: TB check** `TB asserts no loss under ready deassertion; measures II from valid&&ready.`
- [ ] **Step 4: Commit**
```bash
git add docs/contracts/rtl-streaming-17.md docs/contracts/ppa-matrix-18.md CONTEXT.md
git commit -m "docs(rtl): clarify SPC vs II, serial backpressure"
```

### Task 6: New vector-manifest-schema.md

**Files:**
- Create: `docs/contracts/vector-manifest-schema.md`
- Modify: refs in `qpsk-stimulus-15.md`, `fxp-policy-16.md`, `rtl-streaming-17.md`, `sim/vectors/README.md`, `docs/contracts/README.md`

- [ ] **Step 1: Create schema** with fields `stimulus_version,symbol_count,edge_pattern_symbols,random_seed,prng,symbol_map,samples_per_symbol,upsampling,input_samples,output_samples,valid_start,valid_len,symbol_center_offset_samples,W_common,F_data,F_coeff,rounding_mode,overflow_mode,W_product,W_acc_time,fft_mode,fft_stage_widths,W_acc_freq,ifft_scale,DATA_WIDTH,SPC,FFT_LEN,HOP,DISCARD_PREFIX,EMIT_START,EMIT_LEN,latency_samples,latency_cycles,block_cadence,fft_pipeline_cycles,component_sign_extension,hashes` + Q2.(W-2) + sign-extend + 257-block + example.
- [ ] **Step 2: Replace per-doc lists with pointer**, keep examples.
- [ ] **Step 3: Add README row** for new file.
- [ ] **Step 4: Commit**
```bash
git add docs/contracts/vector-manifest-schema.md docs/contracts/qpsk-stimulus-15.md docs/contracts/fxp-policy-16.md docs/contracts/rtl-streaming-17.md sim/vectors/README.md docs/contracts/README.md
git commit -m "docs(vectors): add single manifest schema"
```

### Task 7: Clock-policy gate

**Files:**
- Modify: `docs/plan-gantt.md:39,83-87`, `docs/contracts/ppa-matrix-18.md:211-219`

- [ ] **Step 1: Add note** `D3 interpretation: 10MHz is recovery, never ranked with 100MHz passes. If professor intended slow-power class, add low-power lane.`
- [ ] **Step 2: Commit**
```bash
git add docs/plan-gantt.md docs/contracts/ppa-matrix-18.md
git commit -m "docs(ppa): record clock-policy interpretation"
```

### Task 8: OpenLane hardening same-util with PDN floor

**Files:**
- Modify: `docs/contracts/ppa-matrix-18.md:236-253`, `docs/contracts/openlane-env-19.md:43-56,82-95`, `docs/contracts/toolchain-gap-2.md:94-121`

- [ ] **Step 1: Utilization rule** `Size each die for 50-60% core util, floor max(sized,200x200) for PDN-0185. Record die/core area+util per row. Same PDN strategy, not same die.`
- [ ] **Step 2: SDC template** `create_clock 10/100 + set_input/output_delay + set_false_path rst_n + set_max_transition/fanout via PNR_SDC_FILE/SIGNOFF_SDC_FILE identical except clock.`
- [ ] **Step 3: Toolchain pins** `iverilog --version (11.0+), DUT SV subset allowlist (no interface/randomize/assert-property in DUT), openlane v2.3.10 volare 0fe599...`
- [ ] **Step 4: Power scope** `VCD/SAIF from 257-block canonical workload after warm-up, record file+coverage, exclude IO split, clock-tree included.`
- [ ] **Step 5: Commit**
```bash
git add docs/contracts/ppa-matrix-18.md docs/contracts/openlane-env-19.md docs/contracts/toolchain-gap-2.md
git commit -m "docs(ppa): utilization sizing with PDN floor, SDC template"
```

### Task 9: Gantt/slides/TB/branches

**Files:**
- Modify: `docs/plan-gantt.md:100-157`, `docs/slides/README.md`, `rtl/tb/README.md`, `CONTRIBUTING.md:30-38`, `rtl/*/run.sh` comment only

- [ ] **Step 1: Gantt deps** Add `T13->T20->T22->T30/T32`, `SQNR-retry 7d if no W hits 40dB`, `signoff-respin 5d`, `professor-gate wait`; split runs A/B own lane runs+VCD, D owns table.
- [ ] **Step 2: Slides outline** `arch/SQNR vs W/12-row Pareto/ lessons (OLS H8 vs H9, Q2 vs Q1, II vs fmax)/ actual-vs-planned`.
- [ ] **Step 3: TB impulse + branch** `x[0]=impulse => y[0:8]=h`; allow `research/<issue>-...` or rename to docs/.
- [ ] **Step 4: run.sh smoke banner** `echo SMOKE ONLY — retired in F3`.
- [ ] **Step 5: Commit**
```bash
git add docs/plan-gantt.md docs/slides/README.md rtl/tb/README.md CONTRIBUTING.md rtl/time_serial/run.sh rtl/freq_serial/run.sh rtl/time_opt/run.sh rtl/freq_opt/run.sh
git commit -m "docs(plan): add deps, slides outline, TB impulse, branch fix"
```
