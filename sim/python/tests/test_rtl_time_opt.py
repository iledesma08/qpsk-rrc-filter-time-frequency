"""T40 (#51) structural checks for the optimized time filter, rows T-S4P1 and T-S8P1.

``time_opt_filter`` is one parameterized source (``SYSTOLIC_PES`` = S,
``PIPELINE_DEPTH`` = P); the two base rows differ only in S at P=1. Every
check runs on both rows against the exact integer reference of
``rtl_filter_fixture.py``, the same one that drives the serial filter (T30),
so passing rows are bit-exact with each other and with T-serial on the
structural frames, including RNE ties, saturation and arbitrary codes. The
proposed timing-closure variant T-S4P1-C (#55: T-S4P1 with
``CAST_REGISTER=1``, the y[n] register before the output cast) runs the same
checks with its own latency (3) and its third stored result. Vector matching
against ``sim/vectors`` is in ``test_rtl_time_opt_matching.py``. No timing or
PPA result is claimed here.
"""

from pathlib import Path
import re
import shutil
import subprocess

import pytest

import rtl_filter_fixture


ROOT = Path(__file__).resolve().parents[3]
DUT_SOURCES = [
    ROOT / "rtl/common/rrc_pkg.sv",
    ROOT / "rtl/common/rrc_reset_sync.sv",
    ROOT / "rtl/time_opt/time_opt_filter.sv",
]
# Base matrix rows (ppa-matrix-18): row id -> SYSTOLIC_PES, all at PIPELINE_DEPTH=1.
ROWS = {"T-S4P1": 4, "T-S8P1": 8}
# Proposed timing-closure variant (#55), not a base row: T-S4P1 with the registered cast.
CAST_ROWS = {"T-S4P1-C": 4}
# Every configuration the checks run: row id -> (SYSTOLIC_PES, CAST_REGISTER). The base rows never name
# CAST_REGISTER, so they build and report exactly as before it existed.
CONFIGS = {**{row: (pes, None) for row, pes in ROWS.items()}, **{row: (pes, 1) for row, pes in CAST_ROWS.items()}}
TAPS = 8
LATENCY_CYCLES = rtl_filter_fixture.DESIGN_LATENCY_CYCLES["time_opt"]
CAST_LATENCY_CYCLES = rtl_filter_fixture.DESIGN_LATENCY_CYCLES["time_opt_cast_register"]
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_script(script, *arguments):
    return subprocess.run(
        ["bash", str(ROOT / script), *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )


def run_row(pes, *arguments):
    return run_script("rtl/time_opt/run.sh", "--systolic-pes", str(pes), "--pipeline-depth", "1", *arguments)


def run_config(row, *arguments):
    """Run one configuration of CONFIGS through the runner (``--cast-register`` only when it names one)."""
    pes, cast = CONFIGS[row]
    return run_row(pes, *(("--cast-register", str(cast)) if cast is not None else ()), *arguments)


def fixture_variant(row):
    """The fixture variant whose declared latency the configuration must meet."""
    return "time_opt_cast_register" if CONFIGS[row][1] == 1 else "time_opt"


def parameters_line(row):
    """The ``DUT parameters`` line the testbench prints for the configuration, in full."""
    pes, cast = CONFIGS[row]
    return f"DUT parameters SYSTOLIC_PES={pes} PIPELINE_DEPTH=1" + (f" CAST_REGISTER={cast}" if cast is not None else "")


def simulate(tmp_path, source, top="tb"):
    tb = tmp_path / f"{top}.sv"
    tb.write_text(source)
    binary = tmp_path / f"{top}.out"
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-Wall", "-s", top, "-o", str(binary), *map(str, DUT_SOURCES), str(tb)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(["vvp", str(binary)], capture_output=True, text=True, timeout=60, check=False)


def packed(i_code, q_code):
    return f"{int(q_code) & 0xffff:04x}{int(i_code) & 0xffff:04x}"


@pytest.mark.parametrize("row", CONFIGS)
@pytest.mark.parametrize("frame", rtl_filter_fixture.FRAMES)
@requires_icarus
def test_structural_frame_matches_the_integer_reference_at_ii_8_over_s(tmp_path, frame, row):
    pes = CONFIGS[row][0]
    rtl_filter_fixture.write_fixture(tmp_path, frame, fixture_variant(row))
    source = len(rtl_filter_fixture.frame_codes(frame)[0])
    outputs = source + rtl_filter_fixture.FLUSH_SAMPLES
    result = run_config(row, "--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert parameters_line(row) in result.stdout.splitlines()
    assert f"PASS: vector window W=16 SPC=1 compared={outputs}" in result.stdout
    frames = [line for line in result.stdout.splitlines() if line.startswith("Frame robustness=")]
    assert len(frames) == 2
    # The TB has asserted latency_cycles (2, or 3 with the registered cast) on the continuous run; II = 8/S.
    ii = TAPS // pes
    latency = CAST_LATENCY_CYCLES if row in CAST_ROWS else LATENCY_CYCLES
    assert f"interval_count={outputs - 1} ii_min={ii} ii_max={ii} measured_ii={ii}" in frames[0]
    assert f"measured_latency_cycles={latency}" in frames[0]
    for line in frames:
        assert f"compared={outputs} accepted_beats={outputs} emitted_beats={outputs}" in line
        assert (f"source_samples={source} flush_samples=7 transport_padding_samples=0 "
                f"accepted_input_samples={outputs} raw_output_samples={outputs}") in line
    assert "Midtraffic reset prefix_accepted=2 restart_index=0" in result.stdout


@pytest.mark.parametrize("frame", ["rne_ties", "saturation", "arbitrary"])
@requires_icarus
def test_rows_and_the_serial_filter_emit_identical_codes_where_rounding_and_saturation_act(tmp_path, frame):
    # QPSK never rounds or saturates, so these directed frames are the evidence
    # that both rows share the serial filter's single RNE/saturating cast.
    serial_dir = tmp_path / "serial"
    rtl_filter_fixture.write_fixture(serial_dir, frame)
    result = run_script("rtl/time_serial/run.sh", "--vectors", str(serial_dir),
                        "--capture", str(tmp_path / "serial.hex"))
    assert result.returncode == 0, result.stdout + result.stderr
    captures = {"T-serial": (tmp_path / "serial.hex").read_bytes()}
    for row in CONFIGS:
        row_dir = tmp_path / row
        rtl_filter_fixture.write_fixture(row_dir, frame, fixture_variant(row))
        result = run_config(row, "--vectors", str(row_dir), "--capture", str(tmp_path / f"{row}.hex"))
        assert result.returncode == 0, result.stdout + result.stderr
        captures[row] = (tmp_path / f"{row}.hex").read_bytes()
    # The fixture writes upper-case hex digits and the TB capture lower-case.
    expected = (serial_dir / "expected.hex").read_bytes().lower()
    assert captures == {name: expected for name in captures}


STREAM_TB = """`timescale 1ns/1ps
module tb;
  logic clk = 1'b0, rst_n = 1'b1, valid_i = 1'b0, ready_i = 1'b0;
  logic [31:0] sample_i = '0;
  wire ready_o, valid_o;
  wire [31:0] sample_o;
  integer cycle = 0;
  logic [31:0] inputs [0:8];
  integer next = 0;
  time_opt_filter #(.SYSTOLIC_PES(%PES%), .PIPELINE_DEPTH(1)%CAST%) dut (
    .clk(clk), .rst_n(rst_n), .valid_i(valid_i), .ready_o(ready_o), .sample_i(sample_i),
    .valid_o(valid_o), .ready_i(ready_i), .sample_o(sample_o));
  always #5 clk = ~clk;
  // Values sampled at a rising edge are the pre-update values of that cycle.
  always @(posedge clk) begin
    if (valid_i && ready_o) $display("ACCEPT cycle=%0d data=%08h", cycle, sample_i);
    if (valid_o && ready_i) $display("EMIT cycle=%0d data=%08h", cycle, sample_o);
    cycle = cycle + 1;
  end
  // Offer inputs back to back; a pending offer changes only after it is accepted.
  always @(negedge clk) begin
    if (rst_n && next < 9) begin
      valid_i = 1'b1;
      sample_i = inputs[next];
    end else valid_i = 1'b0;
  end
  always @(posedge clk) if (valid_i && ready_o) next <= next + 1;
  task automatic cleared(input string where);
    if (ready_o !== 1'b0 || valid_o !== 1'b0 || sample_o !== '0)
      $fatal(1, "reset did not clear outputs %s", where);
%CLEARED%  endtask
  initial begin
    inputs[0] = 32'hc0004000;  // x[0] = 1 - j
    for (integer n = 1; n < 9; n = n + 1) inputs[n] = '0;
%BODY%
    $finish;
  end
endmodule
"""


# With the registered cast, reset must also empty the y[n] register.
CAST_CLEARED = """    if (dut.g_cast_register.y_valid !== 1'b0 || dut.g_cast_register.y_acc_i !== '0 ||
        dut.g_cast_register.y_acc_q !== '0)
      $fatal(1, "reset did not clear the cast register %s", where);
"""


def stream_tb(row, body):
    pes, cast = CONFIGS[row]
    return (STREAM_TB.replace("%PES%", str(pes)).replace("%BODY%", body)
            .replace("%CAST%", f", .CAST_REGISTER({cast})" if cast is not None else "")
            .replace("%CLEARED%", CAST_CLEARED if cast == 1 else ""))


def impulse_codes():
    return [packed(c, -c) for c in rtl_filter_fixture.coefficient_codes()] + ["00000000"]


def events(stdout, kind):
    return [(int(m[1]), m[2]) for m in re.finditer(rf"{kind} cycle=(\d+) data=([0-9a-f]+)", stdout)]


@pytest.mark.parametrize("row", CONFIGS)
@requires_icarus
def test_sink_stall_fills_both_output_entries_and_backpressures_the_source(tmp_path, row):
    pes, cast = CONFIGS[row]
    # Results the filter holds under a sink stall: the two output entries, plus y[n] in the cast register.
    stored = 3 if cast == 1 else 2
    body = """
    #2 rst_n = 1'b0;
    #1 cleared("on async assert");
    @(negedge clk) rst_n = 1'b1;
    // Hold the sink for 40 cycles: y[0] and y[1] fill both output entries (and
    // y[2] the cast register), the next input is accepted and waits at tap 0,
    // and no further input may be accepted.
    repeat (40) @(posedge clk);
    // No combinational path: valid_i/ready_i toggles between edges change nothing.
    @(negedge clk);
    begin
      logic ready_seen, valid_seen;
      logic [31:0] sample_seen;
      ready_seen = ready_o; valid_seen = valid_o; sample_seen = sample_o;
      ready_i = 1'b1; #1;
      if (ready_o !== ready_seen || valid_o !== valid_seen || sample_o !== sample_seen)
        $fatal(1, "ready_i reached a DUT output combinationally");
      valid_i = ~valid_i; #1;
      if (ready_o !== ready_seen || valid_o !== valid_seen || sample_o !== sample_seen)
        $fatal(1, "valid_i reached a DUT output combinationally");
      valid_i = ~valid_i; ready_i = 1'b0; #1;
      $display("STALL ready_o=%b valid_o=%b sample_o=%08h full=%b", ready_o, valid_o, sample_o, dut.out_full);
%STAGE%    end
    @(negedge clk) ready_i = 1'b1;
    repeat (60) @(posedge clk);
"""
    # The registered cast also reports what its register holds during the stall.
    stage = ('      $display("STAGE y_valid=%b y_acc_i=%0d", dut.g_cast_register.y_valid, '
             'dut.g_cast_register.y_acc_i);\n') if cast == 1 else ""
    # Output hold under the stall is checked cycle by cycle by the monitor below.
    source = stream_tb(row, body.replace("%STAGE%", stage)).replace(
        "  initial begin\n    inputs[0]",
        """  logic [31:0] held;
  logic stalled = 1'b0;
  always @(posedge clk) begin
    if (stalled && (valid_o !== 1'b1 || sample_o !== held)) $fatal(1, "stalled output changed");
    stalled = valid_o && !ready_i;
    held = sample_o;
  end
  initial begin
    inputs[0]""",
    )
    result = simulate(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    accepts = events(result.stdout, "ACCEPT")
    emits = events(result.stdout, "EMIT")
    stall = re.search(r"STALL ready_o=(\d) valid_o=(\d) sample_o=([0-9a-f]+) full=(\d)", result.stdout)
    assert stall.groups() == ("0", "1", impulse_codes()[0], "1"), result.stdout
    if cast == 1:
        # The third result waits in the cast register at full precision: y[2] = c[2] * 2^14 on I.
        stage_line = re.search(r"STAGE y_valid=(\d) y_acc_i=(-?\d+)", result.stdout)
        assert stage_line.groups() == ("1", str(rtl_filter_fixture.coefficient_codes()[2] << 14)), result.stdout
    stalled_accepts = [cycle for cycle, _ in accepts if cycle < emits[0][0]]
    ii = TAPS // pes
    # One accepted input per stored result, plus the one that waits at tap 0.
    assert [b - a for a, b in zip(stalled_accepts, stalled_accepts[1:])] == [ii] * stored
    # Nothing lost or emitted twice; after the release the rows resume at II = 8/S.
    assert [data for _, data in emits] == impulse_codes()
    assert len(accepts) == 9
    resumed = [cycle for cycle, _ in accepts[stored + 1:]]
    assert all(b - a == ii for a, b in zip(resumed, resumed[1:]))


@pytest.mark.parametrize("row", CONFIGS)
@requires_icarus
def test_reset_is_synchronized_and_clears_partial_sums_mid_computation(tmp_path, row):
    body = """
    #2 rst_n = 1'b0;
    #1 cleared("on async assert");
    @(negedge clk) rst_n = 1'b1;
    @(posedge clk); #1 cleared("one edge after release");
    if (dut.rst_sync_n !== 1'b0) $fatal(1, "release must take two flops");
    @(posedge clk); #1;
    if (dut.rst_sync_n !== 1'b1 || ready_o !== 1'b1) $fatal(1, "release must take exactly two edges");
    // Accept full-scale samples so every partial sum is nonzero, then reset
    // asynchronously while the filter still holds them.
    for (integer n = 0; n < 9; n = n + 1) inputs[n] = 32'h7fff7fff;
    ready_i = 1'b1;
    repeat (5) @(posedge clk);
    #2;
    // (s[1] can be zero here: with a constant input c[1] + c[2] = 0.)
    if (dut.partial_i[7] === '0 || dut.partial_q[4] === '0) $fatal(1, "partial sums must be in use");
    rst_n = 1'b0;
    #1 cleared("mid computation");
    $display("RESTART");
    inputs[0] = 32'hc0004000;
    for (integer n = 1; n < 9; n = n + 1) inputs[n] = '0;
    next = 0;
    @(negedge clk) rst_n = 1'b1;
    repeat (60) @(posedge clk);
"""
    result = simulate(tmp_path, stream_tb(row, body))
    assert result.returncode == 0, result.stdout + result.stderr
    after = result.stdout.split("RESTART", 1)[1]
    # No residue of the pre-reset samples: the restarted impulse response is exact.
    assert [data for _, data in events(after, "EMIT")] == impulse_codes()
    assert len(events(after, "ACCEPT")) == 9


@pytest.mark.parametrize("parameters,width,lanes,message", [
    (".DATA_WIDTH(8)", 8, 1, "time_opt_filter requires DATA_WIDTH=16 (Q2.14), SPC=1"),
    (".SAMPLES_PER_CLOCK(2)", 16, 2, "time_opt_filter requires DATA_WIDTH=16 (Q2.14), SPC=1"),
    (".SYSTOLIC_PES(1)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(2)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(3)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(16)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(4), .PIPELINE_DEPTH(2)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(8), .PIPELINE_DEPTH(0)", 16, 1, "extension-only"),
    (".SYSTOLIC_PES(4), .CAST_REGISTER(2)", 16, 1, "CAST_REGISTER is 0 (base rows) or 1 (registered cast)"),
    (".SYSTOLIC_PES(4), .CAST_REGISTER(-1)", 16, 1, "CAST_REGISTER is 0 (base rows) or 1 (registered cast)"),
])
@requires_icarus
def test_parameters_outside_the_base_rows_fail_at_elaboration(tmp_path, parameters, width, lanes, message):
    result = simulate(tmp_path, f"""`timescale 1ns/1ps
module tb;
  wire ready_o, valid_o;
  wire [{lanes - 1}:0][{2 * width - 1}:0] sample_o;
  time_opt_filter #({parameters}) dut (
    .clk(1'b0), .rst_n(1'b0), .valid_i(1'b0), .ready_o(ready_o),
    .sample_i('0), .valid_o(valid_o), .ready_i(1'b0), .sample_o(sample_o));
  initial begin #1; $display("PARAMETERS SURVIVED"); $finish; end
endmodule
""")
    assert result.returncode != 0
    assert message in result.stdout
    assert "PARAMETERS SURVIVED" not in result.stdout


@pytest.mark.parametrize("script,arguments,message", [
    ("rtl/run_variant.sh", ("time_opt", "--systolic-pes", "4", "--data-width", "8"),
     "time_opt implements only production DATA_WIDTH=16 at SPC=1"),
    ("rtl/run_variant.sh", ("time_opt", "--systolic-pes", "8", "--spc", "4"),
     "time_opt implements only production DATA_WIDTH=16 at SPC=1"),
    ("rtl/run_variant.sh", ("time_opt",), "time_opt needs its row: --systolic-pes S"),
    ("rtl/run_variant.sh", ("time_opt", "--systolic-pes", "four"), "time_opt needs its row: --systolic-pes S"),
    ("rtl/run_variant.sh", ("time_serial", "--systolic-pes", "4"), "apply only to time_opt"),
    ("rtl/run_variant.sh", ("freq_opt", "--pipeline-depth", "1"), "apply only to time_opt"),
    ("rtl/run_variant.sh", ("time_serial", "--cast-register", "1"), "apply only to time_opt"),
    ("rtl/run_variant.sh", ("time_opt", "--systolic-pes", "4", "--cast-register", "2"),
     "--cast-register is 0 (base rows) or 1 (registered cast)"),
    ("rtl/run_variant.sh", ("time_opt", "--systolic-pes", "4", "--cast-register", "yes"),
     "--cast-register is 0 (base rows) or 1 (registered cast)"),
    ("rtl/time_opt/run.sh", ("--capture", "out.hex"), "--vectors and --capture need --systolic-pes"),
    ("rtl/time_opt/run.sh", ("--vectors", "fixture"), "--vectors and --capture need --systolic-pes"),
])
def test_runner_rejects_diagnostic_overrides_and_runs_without_a_row(script, arguments, message):
    result = run_script(script, *arguments)
    assert result.returncode == 2
    assert message in result.stderr


@requires_icarus
def test_runner_reaches_the_elaboration_guard_for_an_extension_row(tmp_path):
    rtl_filter_fixture.write_fixture(tmp_path, "impulse", "time_opt")
    result = run_script("rtl/time_opt/run.sh", "--systolic-pes", "2", "--vectors", str(tmp_path))
    assert result.returncode != 0
    assert "extension-only" in result.stdout


@requires_icarus
def test_an_explicit_cast_register_0_elaborates_the_base_row():
    # CAST_REGISTER=0 is the base row: latency 2 on the canonical fixture, and the TB reports the parameter.
    result = run_row(4, "--cast-register", "0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DUT parameters SYSTOLIC_PES=4 PIPELINE_DEPTH=1 CAST_REGISTER=0" in result.stdout.splitlines()
    assert f"measured_latency_cycles={LATENCY_CYCLES}" in result.stdout
    assert "PASS: vector window W=16 SPC=1 compared=2055" in result.stdout


@requires_icarus
def test_default_run_covers_both_base_rows():
    result = run_script("rtl/time_opt/run.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    rows = re.findall(r"DUT parameters SYSTOLIC_PES=(\d+) PIPELINE_DEPTH=(\d+)", result.stdout)
    assert rows == [("4", "1"), ("8", "1")]
    assert result.stdout.count("PASS: vector window W=16 SPC=1 compared=2055") == 2
