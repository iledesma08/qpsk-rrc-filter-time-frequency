"""T30 structural checks for the serial time-domain filter (S=1, P=1, SPC=1, II=8).

Expected codes come from the exact integer reference of the accepted time
policy in ``rtl_filter_fixture.py``, independent of the T20 FXP model
(``fxp.py``); the T20 integration checks below require both to agree. These
checks are not T31 vector matching against ``sim/vectors`` and claim no timing
or PPA result.
"""

from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pytest

import fxp
import rtl_filter_fixture
from rtl_filter_fixture import FRAC_BITS, MAX_CODE, MIN_CODE, W_ACC_TIME, W_PRODUCT, WIDTH
from stimulus import CORNER_CASES, generate_canonical_samples, generate_corner_samples


ROOT = Path(__file__).resolve().parents[3]
DUT_SOURCES = [
    ROOT / "rtl/common/rrc_pkg.sv",
    ROOT / "rtl/common/rrc_reset_sync.sv",
    ROOT / "rtl/time_serial/time_serial_filter.sv",
]
requires_icarus = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_time_serial(*arguments):
    return subprocess.run(
        ["bash", str(ROOT / "rtl/time_serial/run.sh"), *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )


def simulate(tmp_path, source, top="tb", plusargs=()):
    tb = tmp_path / f"{top}.sv"
    tb.write_text(source)
    binary = tmp_path / f"{top}.out"
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-Wall", "-s", top, "-o", str(binary), *map(str, DUT_SOURCES), str(tb)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(
        ["vvp", str(binary), *plusargs], capture_output=True, text=True, timeout=60, check=False,
    )


def packed(i_code, q_code):
    return f"{int(q_code) & 0xffff:04x}{int(i_code) & 0xffff:04x}"


@pytest.mark.parametrize("frame", rtl_filter_fixture.FRAMES)
@requires_icarus
def test_structural_frame_matches_the_integer_reference_at_ii8(tmp_path, frame):
    rtl_filter_fixture.write_fixture(tmp_path, frame)
    source = len(rtl_filter_fixture.frame_codes(frame)[0])
    outputs = source + rtl_filter_fixture.FLUSH_SAMPLES
    result = run_time_serial("--vectors", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: vector window W=16 SPC=1 compared={outputs}" in result.stdout
    frames = [line for line in result.stdout.splitlines() if line.startswith("Frame robustness=")]
    assert len(frames) == 2
    # The TB has already asserted latency_cycles=9 on the continuous run.
    assert f"interval_count={outputs - 1} ii_min=8 ii_max=8 measured_ii=8" in frames[0]
    for line in frames:
        assert (f"compared={outputs} accepted_beats={outputs} emitted_beats={outputs}") in line
        assert (f"source_samples={source} flush_samples=7 transport_padding_samples=0 "
                f"accepted_input_samples={outputs} raw_output_samples={outputs}") in line
    assert "Midtraffic reset prefix_accepted=2 restart_index=0" in result.stdout


def test_frames_exercise_rounding_saturation_and_the_impulse_response():
    # filter_reference raises on any product or partial sum outside its declared width.
    counters = {frame: rtl_filter_fixture.build_frame(frame)[2].counters
                for frame in rtl_filter_fixture.FRAMES}
    # QPSK inputs are 0 or +/-2^14, so every canonical accumulator is a multiple of 2^14.
    assert counters["canonical"].inexact == 0 and counters["canonical"].saturated == 0
    assert counters["rne_ties"].ties > 0
    assert counters["arbitrary"].inexact > counters["arbitrary"].ties
    assert counters["saturation"].saturated > 0
    coefficients = rtl_filter_fixture.coefficient_codes()
    _, _, impulse = rtl_filter_fixture.build_frame("impulse")
    assert impulse.i_codes[:8] == coefficients
    assert impulse.q_codes[:8] == [-c for c in coefficients]
    assert not any(impulse.i_codes[8:]) and not any(impulse.q_codes[8:])


def test_reference_policy_is_the_contract_and_t20_production_policy():
    # Integers listed by fxp-policy-16 (Numeric Policy) for the accepted coefficients.
    assert rtl_filter_fixture.coefficient_codes() == [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]
    assert rtl_filter_fixture.coefficient_codes() == [int(c) for c in fxp.quantize_coefficients()]
    policy = fxp.PRODUCTION_POLICY.manifest_fields()
    assert (WIDTH, FRAC_BITS, FRAC_BITS, W_PRODUCT, W_ACC_TIME) == (
        policy["W_common"], policy["F_data"], policy["F_coeff"], policy["W_product"], policy["W_acc_time"])


def structural_inputs(frame):
    """Return the fixture input codes of ``frame`` and the samples the T20 model quantizes."""
    if frame in CORNER_CASES:
        samples = generate_corner_samples(frame)
        codes = ([rtl_filter_fixture.to_code(v) for v in samples.real],
                 [rtl_filter_fixture.to_code(v) for v in samples.imag])
        return codes, samples
    i_codes, q_codes = rtl_filter_fixture.frame_codes(frame)
    if frame == "canonical":
        return (i_codes, q_codes), generate_canonical_samples()
    # Directed frames are defined by their codes; every Q2.14 code decodes exactly.
    return (i_codes, q_codes), (np.array(i_codes) + 1j * np.array(q_codes)) / (1 << FRAC_BITS)


@pytest.mark.parametrize("frame", (*rtl_filter_fixture.FRAMES, *CORNER_CASES))
def test_reference_matches_the_t20_time_model(frame):
    # T20 integration gate: the independent reference that drives the RTL
    # fixtures and the accepted FXP model agree code for code and on every cast counter.
    (i_codes, q_codes), samples = structural_inputs(frame)
    model_i, model_q = fxp.quantize_samples(samples)
    assert [int(v) for v in model_i] == i_codes and [int(v) for v in model_q] == q_codes
    model = fxp.filter_time_fxp(samples)
    reference = rtl_filter_fixture.filter_reference(i_codes, q_codes)
    assert [int(v) for v in model.i_codes] == reference.i_codes
    assert [int(v) for v in model.q_codes] == reference.q_codes
    cast = model.monitor.rounding["output_cast"]
    counters = reference.counters
    assert (cast["operations"], cast["inexact"], cast["ties"]) == (
        counters.operations, counters.inexact, counters.ties)
    assert model.monitor.output_saturation_count == counters.saturated
    assert model.monitor.internal_overflow_count == 0


def test_fixture_refuses_the_protected_vector_directory():
    target = ROOT / "sim/vectors/t30-structural-fixture"
    with pytest.raises(ValueError, match="must not be written into sim/vectors"):
        rtl_filter_fixture.write_fixture(target, "impulse")
    assert not target.exists()


@requires_icarus
def test_rtl_coefficients_and_widths_match_the_numeric_policy(tmp_path):
    result = simulate(tmp_path, """`timescale 1ns/1ps
module tb;
  logic signed [rrc_pkg::DATA_WIDTH-1:0] coef;
  initial begin
    for (integer k = 0; k < rrc_pkg::RRC_TAPS; k = k + 1) begin
      coef = rrc_pkg::rrc_coef(k[2:0]);
      $display("COEF %0d %0d", k, coef);
    end
    $display("WIDTHS %0d %0d %0d %0d", rrc_pkg::DATA_WIDTH, rrc_pkg::FRAC_BITS,
             rrc_pkg::W_PRODUCT, rrc_pkg::W_ACC_TIME);
    $finish;
  end
endmodule
""")
    assert result.returncode == 0, result.stdout + result.stderr
    coefficients = [int(m[1]) for m in re.finditer(r"COEF \d+ (-?\d+)", result.stdout)]
    assert coefficients == rtl_filter_fixture.coefficient_codes()
    assert coefficients == [int(c) for c in fxp.quantize_coefficients()]
    assert f"WIDTHS {WIDTH} {FRAC_BITS} {W_PRODUCT} {W_ACC_TIME}" in result.stdout
    policy = fxp.PRODUCTION_POLICY.manifest_fields()
    widths = re.search(r"WIDTHS (\d+) (\d+) (\d+) (\d+)", result.stdout).groups()
    assert tuple(map(int, widths)) == (
        policy["W_common"], policy["F_data"], policy["W_product"], policy["W_acc_time"])


@requires_icarus
def test_output_cast_matches_exact_rne_and_saturation(tmp_path):
    width = W_ACC_TIME
    half = 1 << (FRAC_BITS - 1)
    one = 1 << FRAC_BITS
    limit = MAX_CODE + 1
    edges = [0, 1, -1, half, -half, half - 1, half + 1, -half - 1, -half + 1,
             (limit - 1) * one + half - 1, (limit - 1) * one + half,
             -limit * one - half, -limit * one - half - 1,
             (1 << (width - 1)) - 1, -(1 << (width - 1))]
    edges += [k * one + half for k in range(-4, 5)]
    rng = np.random.default_rng(30)
    values = edges + [int(v) for v in rng.integers(-(1 << (width - 1)), 1 << (width - 1), size=2000)]
    (tmp_path / "acc.hex").write_text("".join(f"{v & ((1 << width) - 1):09x}\n" for v in values))
    result = simulate(tmp_path, f"""`timescale 1ns/1ps
module tb;
  logic [rrc_pkg::W_ACC_TIME-1:0] acc [0:{len(values) - 1}];
  logic signed [rrc_pkg::DATA_WIDTH-1:0] cast;
  initial begin
    $readmemh("{tmp_path / 'acc.hex'}", acc);
    for (integer n = 0; n < {len(values)}; n = n + 1) begin
      cast = rrc_pkg::time_output_cast(acc[n]);
      $display("CAST %0d", cast);
    end
    $finish;
  end
endmodule
""")
    assert result.returncode == 0, result.stdout + result.stderr
    got = [int(m[1]) for m in re.finditer(r"CAST (-?\d+)", result.stdout)]
    counters = rtl_filter_fixture.CastCounters()
    expected = [rtl_filter_fixture.output_cast(v, counters) for v in values]
    assert counters.ties and counters.saturated
    assert MIN_CODE in expected and MAX_CODE in expected
    assert got == expected


STREAM_TB = """`timescale 1ns/1ps
module tb;
  logic clk = 1'b0, rst_n = 1'b1, valid_i = 1'b0, ready_i = 1'b0;
  logic [31:0] sample_i = '0;
  wire ready_o, valid_o;
  wire [31:0] sample_o;
  integer cycle = 0;
  logic [31:0] inputs [0:8];
  integer next = 0;
  time_serial_filter dut (.clk(clk), .rst_n(rst_n), .valid_i(valid_i), .ready_o(ready_o),
                          .sample_i(sample_i), .valid_o(valid_o), .ready_i(ready_i),
                          .sample_o(sample_o));
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
  endtask
  initial begin
    inputs[0] = 32'hc0004000;  // x[0] = 1 - j
    for (integer n = 1; n < 9; n = n + 1) inputs[n] = '0;
%BODY%
    $finish;
  end
endmodule
"""


def impulse_codes():
    return [packed(c, -c) for c in rtl_filter_fixture.coefficient_codes()] + ["00000000"]


def events(stdout, kind):
    return [(int(m[1]), m[2]) for m in re.finditer(rf"{kind} cycle=(\d+) data=([0-9a-f]+)", stdout)]


@requires_icarus
def test_sink_stall_holds_the_final_mac_and_backpressures_the_source(tmp_path):
    body = """
    #2 rst_n = 1'b0;
    #1 cleared("on async assert");
    @(negedge clk) rst_n = 1'b1;
    // Hold the sink for 40 cycles: x[0] fills the output register, x[1] is
    // accepted and waits at tap 7, and no third input may be accepted.
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
      $display("STALL ready_o=%b valid_o=%b sample_o=%08h", ready_o, valid_o, sample_o);
    end
    @(negedge clk) ready_i = 1'b1;
    repeat (120) @(posedge clk);
"""
    # Output hold under the stall is checked cycle by cycle by the monitor below.
    source = STREAM_TB.replace("%BODY%", body).replace(
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
    stall = re.search(r"STALL ready_o=(\d) valid_o=(\d) sample_o=([0-9a-f]+)", result.stdout)
    assert stall.groups() == ("0", "1", impulse_codes()[0]), result.stdout
    stalled_accepts = [cycle for cycle, _ in accepts if cycle < emits[0][0]]
    assert len(stalled_accepts) == 2 and stalled_accepts[1] - stalled_accepts[0] == 8
    assert [data for _, data in emits] == impulse_codes()
    assert len(accepts) == 9
    # After the release the engine resumes at II=8 with no loss or duplication.
    resumed = [cycle for cycle, _ in accepts[2:]]
    assert all(b - a == 8 for a, b in zip(resumed, resumed[1:]))


@requires_icarus
def test_reset_is_synchronized_and_clears_history_mid_computation(tmp_path):
    body = """
    #2 rst_n = 1'b0;
    #1 cleared("on async assert");
    @(negedge clk) rst_n = 1'b1;
    @(posedge clk); #1 cleared("one edge after release");
    if (dut.rst_sync_n !== 1'b0) $fatal(1, "release must take two flops");
    @(posedge clk); #1;
    if (dut.rst_sync_n !== 1'b1 || ready_o !== 1'b1) $fatal(1, "release must take exactly two edges");
    // Accept a full-scale sample, then reset asynchronously mid-computation.
    inputs[0] = 32'h7fff7fff;
    ready_i = 1'b1;
    @(posedge clk); @(posedge clk); @(posedge clk); #2;
    if (dut.busy !== 1'b1) $fatal(1, "reset must interrupt an active MAC sequence");
    rst_n = 1'b0;
    #1 cleared("mid computation");
    $display("RESTART");
    inputs[0] = 32'hc0004000;
    next = 0;
    @(negedge clk) rst_n = 1'b1;
    repeat (120) @(posedge clk);
"""
    result = simulate(tmp_path, STREAM_TB.replace("%BODY%", body))
    assert result.returncode == 0, result.stdout + result.stderr
    after = result.stdout.split("RESTART", 1)[1]
    # No residue of the pre-reset sample: the restarted impulse response is exact.
    assert [data for _, data in events(after, "EMIT")] == impulse_codes()
    assert len(events(after, "ACCEPT")) == 9


@pytest.mark.parametrize("parameters,width,lanes", [
    (".DATA_WIDTH(8)", 8, 1),
    (".SAMPLES_PER_CLOCK(2)", 16, 2),
])
@requires_icarus
def test_non_production_parameters_fail_at_elaboration(tmp_path, parameters, width, lanes):
    result = simulate(tmp_path, f"""`timescale 1ns/1ps
module tb;
  wire ready_o, valid_o;
  wire [{lanes - 1}:0][{2 * width - 1}:0] sample_o;
  time_serial_filter #({parameters}) dut (
    .clk(1'b0), .rst_n(1'b0), .valid_i(1'b0), .ready_o(ready_o),
    .sample_i('0), .valid_o(valid_o), .ready_i(1'b0), .sample_o(sample_o));
  initial begin #1; $display("PARAMETERS SURVIVED"); $finish; end
endmodule
""")
    assert result.returncode != 0
    assert "time_serial_filter requires DATA_WIDTH=16 (Q2.14), SPC=1" in result.stdout
    assert "PARAMETERS SURVIVED" not in result.stdout


@pytest.mark.parametrize("arguments", [("--data-width", "8"), ("--spc", "4")])
def test_runner_rejects_diagnostic_width_or_spc_for_time_serial(arguments):
    result = run_time_serial(*arguments)
    assert result.returncode == 2
    assert "time_serial implements only production DATA_WIDTH=16 at SPC=1" in result.stderr
