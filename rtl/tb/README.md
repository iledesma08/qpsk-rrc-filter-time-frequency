# rtl/tb — testbenches with vector matching

## T03 shell tests (#42)

`rrc_stream_tb.sv` is the shared manifest-driven family for all four wrappers.
It replaces `rrc_placeholder_tb.sv`. Current runs test transport, **not RRC
vector matching**. The filter impulse check (`x[0] => y[0:8] = h`) belongs to
the real datapaths in F3.

From the repository root:

```bash
bash rtl/run.sh
bash rtl/time_serial/run.sh --data-width 8 --spc 4
python -m pytest sim/python/tests/test_rtl_stream.py -v
```

The runners use `rtl/run_variant.sh`, generating transport fixtures with 33
original source records under `.build/rtl/<variant>/`, not `sim/vectors/`.
`sim/python/tests/rtl_shell_fixture.py` generates `input.hex`, `expected.hex`,
metadata-only `vector_manifest.svh`, and SHA-256 sidecars. Expected output is
identity transport, not filtered QPSK. Python 3 is needed for generation.

To consume an existing **shell fixture**, use
`bash rtl/time_serial/run.sh --vectors /path/to/fixture`. Files and sidecars
must exist and hashes must pass before compilation. Width/SPC overrides cannot
be combined with `--vectors`: the manifest owns those values. T03 runners
reject metadata without `RRC_SHELL_FIXTURE`; real RRC manifests are connected
only after the wrappers contain real datapaths.

## Scoreboard and coverage

The `.svh` supplies compile-time localparams for widths/SPC, source/expected file
counts, valid window, sample/cycle latencies, and frequency block metadata. It
also declares `flush_samples`, `transport_padding_samples`,
`accepted_input_samples`, and `raw_output_samples`. Names match
`docs/contracts/rtl-streaming-17.md`; the full production schema remains
`docs/contracts/vector-manifest-schema.md`.

The driver sends exactly `input_samples` original records, then `flush_samples`
zeros, then `transport_padding_samples` zeros, holding each beat until accepted.
Transfers are whole beats without `TKEEP`: input beats are
`accepted_input_samples / SPC` and output beats are `raw_output_samples / SPC`.
The TB validates exact divisibility and the declared count/window relationships;
it does not infer physical counts from expected-file length or sample latency.
It counts actual source, flush, padding, and total accepted samples on
`valid_i && ready_o`, and every physical output lane on `valid_o && ready_i`.

For each consumed output lane, the absolute index is
`received * SPC + lane + latency_samples`; lane 0 is earliest. Only indices in
`[valid_start, valid_start + valid_len)` look up `expected_codes[absolute_index]`
and consume a compared code. Declared raw padding outside that window still
counts physically but must not look up or consume an expected code. Stored codes
are compared after signed I/Q extension to 16 bits; mismatches report index,
expected code, and captured code. Cycle latency is checked separately in a
no-gap/no-stall run.

Completion requires all declared input and raw-output beats, exact physical and
valid-window counts, and a bounded drain check for extra emissions. Missing
outputs time out; invalid counts or undeclared outputs fail even if every
valid-window code matched. File counts/hex records, known controls/payload, and
output hold are also checked. Unequal source/expected lengths are supported.
Actual RRC matching is #48/#50; the frequency engine's 257-block schedule,
latency, II, and block cadence remain #49/#50 integration checks, not shell
results. Synthetic asymmetric frames exercise only the generic TB mechanics.

Continuous-run reports append `interval_count`, `ii_min`, `ii_max`, and
`measured_ii` from successive accepted-input edges. A constant nonempty cadence
has a numeric II; one-beat or variable-cadence measurements report `undefined`.
Robustness-induced waits do not enter those statistics. Synthetic constant-II8
and variable 4/8 adapters test this instrumentation, not a finished serial filter.

The robust run guarantees a valid post-input tail stall and keeps bounded ready
opportunities while capturing all declared raw outputs. The continuous run
remains always ready, and the final bounded extra-output check also forces
`ready_i=1`. `tail_stalls` reports actual covered holds, not just attempted stalls.
An accepted prefix is aborted by asynchronous reset under continuous offers;
the next full-frame run restarts at record zero with fresh counters. One-beat
frames explicitly have no proper nonempty prefix to abort.

Directed faulty adapters mutate a held payload, duplicate a code, drive X on a
valid payload, or retain stale post-reset data. Tests require their specific
hold/mismatch/unknown diagnostics and include a passing clean-adapter baseline.

Coverage includes async reset assertion, two-flop release, reset while an output
is pending, back-to-back traffic, deterministic seeded source gaps/sink stalls,
DUT backpressure, source tails padded to whole beats, and diagnostic W/SPC
configurations 8/1, 12/2, 16/4 across every variant. These widths do not redefine
production Q2.14. Finite-frame cases exercise explicit flush, unequal
source/expected/raw counts, and padding outside the valid window. Negative cases
exercise missing files, bad hashes, wrong expected codes, malformed transport
counts, extra records, missing/extra emissions, and false non-fixture passes. A
test-only non-fixture adapter preserves the 33-input/29-raw-output case with
`latency_samples=4`, without adding an RRC datapath. Coverage cases are not a
claim of a new passing run; updated evidence is recorded only after execution.
The robust run starts with a directed bubble. For frames of at least two beats,
the first two offers and the controlled sink stall guarantee stalls and
backpressure coverage. A one-beat frame cannot block another input; its codes
and physical counts are still checked, and multi-beat cases supply that coverage.
Known controls are checked during the drain as well as the capture loop.

Learning: scoreboard indices/counts track accepted emissions, not elapsed clocks;
arrival latency, sample alignment and II are distinct. Icarus 12 required
separate `$isunknown` checks for ready/valid rather than their concatenation.
The 10 ns TB clock is functional simulation, not 100 MHz physical-timing proof.

## Current PR #73 review verification

On 2026-10-06 after the reviewer changes:

- `.venv/bin/python -m pytest sim/python -v`: **208 passed**, no skips
  (92 inherited + 9 fixtures + 61 stream + 46 reset/configuration cases), after
  integrating the current `main` with its staged float-reference generator.
- `bash rtl/run.sh`: all four wrappers passed both frames. The continuous frame
  measured 32 intervals at II=1; the robust frame covered a post-input tail stall
  and restarted at index zero after resetting a two-beat accepted prefix.
- DUT-only Verilator commands from CI passed without warnings. Frequency
  parameters are now used in structural checks, not FFT arithmetic.
- `bash scripts/check-vectors.sh` and `git diff --check` passed.

The common reset source precedes the shell in simulation/lint/OpenLane lists.
Icarus compilation of OpenLane source lists is not synthesis or physical signoff.
No SQNR, actual RRC matching, physical timing, or PPA is established here.

## Historical post-#70 verification

After integrating the current `main` on 2026-10-05,
`.venv/bin/python -m pytest sim/python -v` passed all 104 cases without skips
(51 inherited, 9 fixture, 44 Icarus). `bash rtl/run.sh` again passed both frames
for all four wrappers. The 92-case results below describe the earlier branch
checkpoint, before the frequency-golden tests were integrated.

Rechecked locally on 2026-10-05 before the atomic #42 commits:
`.venv/bin/python -m pytest sim/python -v` passed all 92 cases without skips,
and `bash rtl/run.sh` passed both frames for each of the four wrappers.
The four DUT-only Verilator commands from CI exited successfully with the
documented unused frequency-parameter warnings. The RTL job retains the
published check name `RTL smoke tests` because `main` protection requires it;
the Python check name also agrees with the live protection settings.
The `act` results below are prior local evidence, not a new execution on this
date. No hosted GitHub check or physical flow was run for this recheck.

On `feat/42-streaming-skeleton` based on `a4df828`, after the explicit-count and
review fixes:

- `.venv/bin/python -m pytest sim/python -v`: **92 passed**, no local skips
  (39 inherited tests + 9 fixture tests + 44 Icarus cases).
- `bash rtl/run.sh`: all four wrappers passed both continuous and robustness
  frames, with 33 compared/source samples and 33 accepted/raw samples at SPC=1.
- `act push -W .github/workflows/ci.yml --container-architecture linux/amd64
  -P ubuntu-latest=catthehacker/ubuntu:act-latest --pull=false`: all three jobs
  succeeded. `sim` passed 48 tests and skipped 44 Icarus cases; the required
  `rtl` job ran those 44 cases successfully. Optional Verilator lint retained
  unused frequency-parameter warnings; it is not a required physical gate.
- Review regressions cover the valid two-beat flush fixture and a one-beat
  frame, plus a test-only adapter exposing `ready_o=X` after its last output.
  Those cases were reproduced RED before the minimal fixes and passed afterward.
- Local ignored logs: `.build/issue42-post70/pytest.log`, `rtl.log`, `act.log`.
  These are local evidence, not published GitHub artifacts. No SQNR, actual
  RRC matching, OpenLane run or PPA result is claimed.

## Historical local evidence (2026-10-02, pre-#70)

The results below predate #70 and the explicit finite-frame adaptation. The
coordinator reported a passing post-#70 local baseline before this adaptation;
neither that baseline nor this historical evidence verifies the adapted code.
The coordinator records new test counts/metrics only after an actual run.

- Recreated Python 3.12 `.venv` with pinned requirements: full suite **65 passed**.
- `bash rtl/run.sh`: four transport PASS results, each comparing 33 records in
  both the uninterrupted and robustness runs.
- Independent Standards/Spec review: sample-offset counting and non-fixture
  pass classification findings reproduced RED, fixed, then regression GREEN.
- `/home/askesis/.local/bin/act push -W .github/workflows/ci.yml
  --container-architecture linux/amd64
  -P ubuntu-latest=catthehacker/ubuntu:act-latest --pull=false`: all three jobs
  succeeded. `sim`: 41 passed, 24 Icarus tests skipped; the required `rtl` job
  ran those 24 tests successfully. Verilator lint passed with expected unused
  frequency-block parameter warnings while the block engine is absent.
- Local ignored logs are in `.build/issue42/`: `act.log`, `pytest.log`,
  `rtl.log`, and `compile-time_serial.log`. They are local evidence, not a
  published GitHub artifact. OpenLane synthesis/signoff and PPA remain unrun.
