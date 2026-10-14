"""Structural T03 checks only; no FFT arithmetic or hop-9 approval implied."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
VARIANTS = ("time_serial", "time_opt", "freq_serial", "freq_opt")
# time_serial carries the T30 filter; its reset test is in test_rtl_time_serial.py.
TRANSPORT_VARIANTS = ("time_opt", "freq_serial", "freq_opt")
FREQUENCY = ("freq_serial", "freq_opt")


def simulate(tmp_path, body, variant=None, sources=None):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus Verilog and vvp are required")
    tb = tmp_path / "config_tb.sv"
    tb.write_text("`timescale 1ns/1ps\nmodule config_tb;\n" + body + "\nendmodule\n")
    if sources is None:
        sources = sorted((ROOT / "rtl/common").glob("rrc_*.sv"))
        if variant:
            sources.append(ROOT / f"rtl/{variant}/{variant}_filter.sv")
    binary = tmp_path / "sim.out"
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-Wall", "-s", "config_tb", "-o", str(binary),
         *map(str, sources), str(tb)], capture_output=True, text=True, timeout=30,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(
        ["vvp", str(binary)], capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("variant", (*TRANSPORT_VARIANTS, "direct"))
def test_distributed_reset_and_elastic_hold(tmp_path, variant):
    if variant == "direct":
        instance = """
  rrc_reset_sync reset_sync (.clk(clk), .rst_n(rst_n), .rst_sync_n(sync_n));
  rrc_stream_shell dut (.clk(clk), .rst_sync_n(sync_n),
"""
        dut_variant = None
    else:
        instance = f"""
  assign sync_n = dut.rst_sync_n;
  {variant}_filter dut (.clk(clk), .rst_n(rst_n),
"""
        dut_variant = variant
    result = simulate(tmp_path, """
  logic clk = 0, rst_n = 1, valid_i = 1, ready_i = 1;
  wire sync_n, ready_o, valid_o;
  logic [31:0] sample_i = 32'h12345678;
  wire [31:0] sample_o;
  integer observer;
  // A future F3 state register shares exactly the shell's reset net.
  always @(posedge clk or negedge sync_n)
    if (!sync_n) observer <= 0;
    else observer <= observer + 1;
""" + instance + """
    .valid_i(valid_i), .ready_o(ready_o), .sample_i(sample_i),
    .valid_o(valid_o), .ready_i(ready_i), .sample_o(sample_o));
  task tick;
    #5 clk = 1;
    #1;
    #4 clk = 0;
  endtask
  task cleared;
    if (sync_n !== 0 || ready_o !== 0 || valid_o !== 0 ||
        sample_o !== 0 || observer !== 0) $fatal(1, "async reset not distributed");
  endtask
  task release_reset;
    rst_n = 1;
    #1; cleared();
    tick(); cleared();
    tick();
    if (sync_n !== 1 || ready_o !== 1 || valid_o !== 0 || observer !== 0)
      $fatal(1, "release must take exactly two edges, without early capture");
    tick();
    if (observer !== 1 || valid_o !== 1 || sample_o !== sample_i)
      $fatal(1, "shell and observer must start together, no double sync");
  endtask
  initial begin
    #2 rst_n = 0;
    #1; cleared();
    release_reset();
    // Full entry must hold despite input changes and source bubbles.
    ready_i = 0; sample_i = 32'habcdef01; valid_i = 0;
    repeat (3) begin
      tick();
      if (ready_o !== 0 || valid_o !== 1 || sample_o !== 32'h12345678)
        $fatal(1, "stalled entry changed");
    end
    valid_i = 1; ready_i = 1;
    if (sample_o !== 32'h12345678) $fatal(1, "combinational bypass");
    tick();
    if (ready_o !== 1 || valid_o !== 1 || sample_o !== 32'habcdef01)
      $fatal(1, "II=1 replacement failed");
    sample_i = 32'h87654321;
    tick();
    if (valid_o !== 1 || sample_o !== 32'h87654321) $fatal(1, "II=1 failed");
    valid_i = 0; tick();
    if (valid_o !== 0 || ready_o !== 1) $fatal(1, "bubble did not drain");
    valid_i = 1; tick(); ready_i = 0;
    // Pulse raw reset between clock edges, including while stalled.
    #2 rst_n = 0;
    #1; cleared();
    ready_i = 1;
    release_reset();
    $display("PASS distributed reset and elastic transport");
    $finish;
  end
""", dut_variant)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS distributed reset" in result.stdout


# Literal expectations catch stale package defaults under local overrides.
@pytest.mark.parametrize("variant", FREQUENCY)
@pytest.mark.parametrize("overrides,start,length", [
    ("", 8, 8),
    (".HOP(9), .DISCARD_PREFIX(7)", 7, 9),
    (".FFT_LEN(32), .HOP(24)", 8, 24),
    (".FFT_LEN(16), .HOP(16), .DISCARD_PREFIX(0)", 0, 16),
])
def test_valid_frequency_tuple(tmp_path, variant, overrides, start, length):
    params = f"#({overrides})" if overrides else ""
    result = simulate(tmp_path, f"""
  {variant}_filter {params} dut (
    .clk(1'b0), .rst_n(1'b0), .valid_i(1'b0), .ready_o(),
    .sample_i(32'b0), .valid_o(), .ready_i(1'b0), .sample_o());
  initial begin
    #1;
    if (dut.EMIT_START != {start} || dut.EMIT_LEN != {length})
      $fatal(1, "emit defaults must derive from wrapper parameters");
    $display("PASS structural tuple");
    $finish;
  end
""", variant)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS structural tuple" in result.stdout


@pytest.mark.parametrize("variant", FREQUENCY)
@pytest.mark.parametrize("overrides", [
    ".FFT_LEN(0)", ".FFT_LEN(-16)", ".FFT_LEN(15)",
    ".DISCARD_PREFIX(-1)", ".DISCARD_PREFIX(16)", ".DISCARD_PREFIX(17)",
    ".HOP(0)", ".HOP(-1)", ".HOP(17)",
    ".EMIT_START(7)", ".EMIT_LEN(7)", ".HOP(9)",
    ".HOP(9), .DISCARD_PREFIX(7), .EMIT_START(8), .EMIT_LEN(9)",
    ".HOP(9), .DISCARD_PREFIX(7), .EMIT_START(7), .EMIT_LEN(8)",
])
def test_invalid_frequency_tuple_fails_at_time_zero(tmp_path, variant, overrides):
    result = simulate(tmp_path, f"""
  {variant}_filter #({overrides}) dut (
    .clk(1'b0), .rst_n(1'b0), .valid_i(1'b0), .ready_o(),
    .sample_i(32'b0), .valid_o(), .ready_i(1'b0), .sample_o());
  initial begin #1; $display("INVALID TUPLE SURVIVED"); $finish; end
""", variant)
    assert result.returncode != 0, "invalid tuple survived: " + result.stdout
    assert "Invalid frequency parameters" in result.stdout
    assert "Time: 0" in result.stdout
    assert "INVALID TUPLE SURVIVED" not in result.stdout


def test_unknown_runner_variant_reports_error(tmp_path):
    result = subprocess.run(
        ["bash", str(ROOT / "rtl/run_variant.sh"), "unknown_config_variant"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "Unknown variant: unknown_config_variant" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("variant", VARIANTS)
def test_openlane_source_list_compiles_dut(tmp_path, variant):
    config_dir = ROOT / f"openlane/{variant}"
    config = json.loads((config_dir / "config.json").read_text())
    sources = []
    for entry in config["VERILOG_FILES"]:
        assert entry.startswith("dir::")
        path = config_dir / entry.removeprefix("dir::")
        sources.extend(sorted(path.parent.glob(path.name)))
    result = simulate(tmp_path, f"""
  {variant}_filter dut (
    .clk(1'b0), .rst_n(1'b0), .valid_i(1'b0), .ready_o(),
    .sample_i(32'b0), .valid_o(), .ready_i(1'b0), .sample_o());
  initial begin #1; $finish; end
""", sources=sources)
    assert result.returncode == 0, result.stdout + result.stderr
