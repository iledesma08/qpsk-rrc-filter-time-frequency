"""T32 (#49): freq_serial against the T22 vectors, its rounding primitives and a reset in mid block.

The structural fixture is built from the committed ``sim/vectors/fxp_expected``
codes into ``tmp_path``; nothing is written to ``sim/vectors/``. The committed
``rtl_matching`` manifest and the formal matching report are T33 (#50).
Standard library only, so it runs in the RTL CI job without NumPy.
"""

import hashlib
from fractions import Fraction
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtl_freq_fixture as fixture  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "rtl" / "common"
DUT_SOURCES = [
    COMMON / "rrc_pkg.sv", COMMON / "rrc_reset_sync.sv", COMMON / "rrc_freq_pkg.sv",
    COMMON / "rrc_freq_engine.sv", ROOT / "rtl" / "freq_serial" / "freq_serial_filter.sv",
]
TB = ROOT / "rtl" / "tb" / "rrc_stream_tb.sv"
pytestmark = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)


def run_variant(*arguments):
    return subprocess.run(
        ["bash", str(ROOT / "rtl/freq_serial/run.sh"), *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )


def rehash(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="utf-8")


def compile_and_run(tmp_path, sources, top, defines=(), arguments=()):
    binary = tmp_path / f"{top}.out"
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-Wall", *[f"-D{define}" for define in defines], "-s", top,
         "-o", str(binary), *map(str, sources)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(
        ["vvp", str(binary), *arguments], cwd=tmp_path, capture_output=True, text=True,
        timeout=300, check=False,
    )


# Vector matching against the T22 expected codes -----------------------------


@pytest.mark.parametrize("frame", sorted(fixture.FRAMES))
def test_freq_serial_matches_the_t22_codes_on_every_frame(tmp_path, frame):
    vectors = fixture.write_fixture(tmp_path / frame, frame)
    result = run_variant("--vectors", str(vectors))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: vector window W=16 SPC=1 compared=2055" in result.stdout
    frames = [line for line in result.stdout.splitlines() if line.startswith("Frame robustness=")]
    assert len(frames) == 2
    for line in frames:
        # 257 blocks: 2048 source records + 8 flush zeros in, 2056 raw outputs, 2055 compared.
        assert ("compared=2055 accepted_beats=2056 emitted_beats=2056" in line), line
        assert "source_samples=2048 flush_samples=8 transport_padding_samples=0" in line, line
    assert "cycles=27499 " in frames[0]


def test_default_runner_uses_the_canonical_structural_fixture():
    result = run_variant()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: vector window W=16 SPC=1 compared=2055" in result.stdout


def test_a_latency_change_fails_the_testbench(tmp_path):
    vectors = fixture.write_fixture(tmp_path / "canonical")
    manifest = vectors / "vector_manifest.svh"
    manifest.write_text(manifest.read_text().replace(
        f"latency_cycles = {fixture.LATENCY_CYCLES};", f"latency_cycles = {fixture.LATENCY_CYCLES - 1};"))
    rehash(manifest)
    result = run_variant("--vectors", str(vectors))
    assert result.returncode != 0
    assert f"Latency mismatch expected={fixture.LATENCY_CYCLES - 1} got={fixture.LATENCY_CYCLES}" in result.stdout


def test_a_wrong_expected_code_fails_the_testbench(tmp_path):
    vectors = fixture.write_fixture(tmp_path / "canonical")
    expected = vectors / "expected.hex"
    lines = expected.read_text().splitlines()
    lines[100] = "%08x" % (int(lines[100], 16) ^ 1)
    expected.write_text("\n".join(lines) + "\n")
    rehash(expected)
    result = run_variant("--vectors", str(vectors))
    assert result.returncode != 0
    assert "Mismatch index=100" in result.stdout


# Runner and fixture limits --------------------------------------------------


@pytest.mark.parametrize("option", [("--data-width", "8"), ("--spc", "2"), ("--data-width", "12", "--spc", "4")])
def test_runner_rejects_diagnostic_width_or_spc_for_freq_serial(option):
    result = run_variant(*option)
    assert result.returncode == 2
    assert "freq_serial implements only production DATA_WIDTH=16 at SPC=1" in result.stderr
    assert not result.stdout


def test_top_level_runner_skips_freq_serial_for_diagnostic_options():
    result = subprocess.run(
        ["bash", str(ROOT / "rtl/run.sh"), "--data-width", "8"],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping freq_serial: it implements only production DATA_WIDTH=16 at SPC=1" in result.stdout


def test_fixture_never_writes_into_sim_vectors():
    with pytest.raises(ValueError, match="never go into sim/vectors"):
        fixture.write_fixture(ROOT / "sim" / "vectors" / "freq_serial_fixture")
    assert not (ROOT / "sim" / "vectors" / "freq_serial_fixture").exists()


def test_fixture_has_the_declared_counts_and_a_marker(tmp_path):
    vectors = fixture.write_fixture(tmp_path / "canonical")
    assert len((vectors / "input.hex").read_text().split()) == 2048
    assert len((vectors / "expected.hex").read_text().split()) == 2055
    manifest = (vectors / "vector_manifest.svh").read_text()
    assert "`define RRC_STRUCTURAL_FIXTURE" in manifest
    assert "RRC_SHELL_FIXTURE" not in manifest
    assert "localparam integer accepted_input_samples = 2056;" in manifest


# Directed check of the narrowing primitives ---------------------------------
# The T22 frames reach no RNE tie and no output saturation (fxp-policy-16), so
# the vectors cannot tell RNE from round-half-up or catch a missing saturation.

ROUNDING_TB = """`timescale 1ns/1ps
module rounding_tb;
  import rrc_freq_pkg::*;
  localparam integer NA = %(na)d, NB = %(nb)d;
  logic [63:0] a_in [0:NA-1];
  logic [47:0] a_exp [0:NA-1];
  logic [47:0] b_in [0:NB-1];
  logic [15:0] b_exp [0:NB-1];
  logic signed [FREQ_PW-1:0] av;
  logic signed [FREQ_CW-1:0] bv;
  integer i, bad_a, bad_b;
  initial begin
    if (FREQ_PW != 62 || FREQ_CW != 45 || FREQ_FRAC != 14 || FREQ_OUT_SHIFT != 18)
      $fatal(1, "widths changed: regenerate the rounding vectors");
    $readmemh("a_in.hex", a_in); $readmemh("a_exp.hex", a_exp);
    $readmemh("b_in.hex", b_in); $readmemh("b_exp.hex", b_exp);
    bad_a = 0; bad_b = 0;
    for (i = 0; i < NA; i = i + 1) begin
      av = a_in[i][FREQ_PW-1:0];
      if (rne_shift_frac(av) !== a_exp[i][FREQ_CW-1:0]) bad_a = bad_a + 1;
    end
    for (i = 0; i < NB; i = i + 1) begin
      bv = b_in[i][FREQ_CW-1:0];
      if (output_cast(bv) !== b_exp[i]) bad_b = bad_b + 1;
    end
    $display("rne_shift_frac checked=%%0d bad=%%0d", NA, bad_a);
    $display("output_cast checked=%%0d bad=%%0d", NB, bad_b);
    if (bad_a != 0 || bad_b != 0) $fatal(1, "rounding or saturation mismatch");
    $display("PASS: narrowing primitives");
    $finish;
  end
endmodule
"""
MUTANTS = {
    "half_up_rne_shift_frac": (
        "round_up = dropped[FREQ_FRAC-1] && ((dropped[FREQ_FRAC-2:0] != 0) || floor_value[0]);",
        "round_up = dropped[FREQ_FRAC-1];"),
    "half_up_output_cast": (
        "round_up = dropped[FREQ_OUT_SHIFT-1] && ((dropped[FREQ_OUT_SHIFT-2:0] != 0) || floor_value[0]);",
        "round_up = dropped[FREQ_OUT_SHIFT-1];"),
    "no_saturation": (
        "if (rounded > OUT_MAX) output_cast = OUT_MAX[FREQ_IN_W-1:0];\n"
        "      else if (rounded < OUT_MIN) output_cast = OUT_MIN[FREQ_IN_W-1:0];\n"
        "      else output_cast = rounded[FREQ_IN_W-1:0];",
        "output_cast = rounded[FREQ_IN_W-1:0];"),
}


def rne(value, shift):
    return round(Fraction(value, 1 << shift))  # round() of a Fraction is ties-to-even


def hex_word(value, bits):
    return f"{value & ((1 << bits) - 1):0{bits // 4}x}"


def write_rounding_vectors(directory: Path):
    rng = random.Random(7)
    a = []
    for k in list(range(-40, 40)) + [rng.randrange(-2**43, 2**43) for _ in range(300)]:
        tie = (2 * k + 1) << 13
        a += [tie, tie - 1, tie + 1, -tie, -tie + 1, -tie - 1]
    a += [0, 1, -1, 1 << 13, -(1 << 13), (1 << 13) + 1, 2**57 - 1, -2**57]
    a += [rng.randrange(-2**57, 2**57) for _ in range(3000)]
    b = []
    for k in list(range(-60, 60)) + [rng.randrange(-2**26, 2**26) for _ in range(300)]:
        tie = (2 * k + 1) << 17
        b += [tie, tie - 1, tie + 1, -tie, -tie + 1, -tie - 1]
    b += [0, 1, -1, 2**44 - 1, -2**44, 32767 << 18, 32768 << 18, (32767 << 18) + (1 << 17),
          (32767 << 18) + (1 << 17) + 1, -(32768 << 18), -(32768 << 18) - (1 << 17),
          -(32768 << 18) - (1 << 17) - 1]
    b += [rng.randrange(-2**44, 2**44) for _ in range(3000)]
    (directory / "a_in.hex").write_text("".join(hex_word(v, 64) + "\n" for v in a))
    (directory / "a_exp.hex").write_text("".join(hex_word(rne(v, 14), 48) + "\n" for v in a))
    (directory / "b_in.hex").write_text("".join(hex_word(v, 48) + "\n" for v in b))
    (directory / "b_exp.hex").write_text(
        "".join(hex_word(max(-32768, min(32767, rne(v, 18))), 16) + "\n" for v in b))
    (directory / "rounding_tb.sv").write_text(ROUNDING_TB % {"na": len(a), "nb": len(b)})


def test_narrowing_primitives_match_exact_rne_and_saturation(tmp_path):
    write_rounding_vectors(tmp_path)
    result = compile_and_run(
        tmp_path, [COMMON / "rrc_freq_pkg.sv", tmp_path / "rounding_tb.sv"], "rounding_tb")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rne_shift_frac checked=" in result.stdout and "bad=0" in result.stdout
    assert "PASS: narrowing primitives" in result.stdout


@pytest.mark.parametrize("mutant", sorted(MUTANTS))
def test_the_directed_check_catches_each_mutant(tmp_path, mutant):
    """The vectors pass these mutants (no reachable tie or saturation); this check must not."""
    write_rounding_vectors(tmp_path)
    old, new = MUTANTS[mutant]
    package = (COMMON / "rrc_freq_pkg.sv").read_text()
    assert package.count(old) == 1, "the mutation target moved; update MUTANTS"
    mutated = tmp_path / "rrc_freq_pkg_mutant.sv"
    mutated.write_text(package.replace(old, new))
    result = compile_and_run(tmp_path, [mutated, tmp_path / "rounding_tb.sv"], "rounding_tb")
    assert result.returncode != 0, result.stdout
    assert "rounding or saturation mismatch" in result.stdout


# Reset in the middle of a block ---------------------------------------------
# rrc_stream_tb resets after two accepted samples, i.e. in ACCEPT. The work
# buffer and operand registers have no reset (documented in the engine), so a
# reset while a block is being computed or emitted must leave no trace.

RESET_TB = """`timescale 1ns/1ps
module reset_tb;
  localparam integer N = 40;           // five blocks
  logic clk = 1'b0, rst_n = 1'b0, valid_i = 1'b0, ready_i = 1'b1;
  wire ready_o, valid_o;
  logic [31:0] sample_i = 32'd0;
  wire [31:0] sample_o;
  logic [31:0] input_codes [0:2047];
  logic [31:0] expected_codes [0:2054];
  string vector_dir;
  integer idx, out_idx, cycles, quiet;
  logic hit, accept, capture;
  logic [31:0] captured;
  wire [2:0] st = dut.datapath.engine.state;
  wire [3:0] pass_count = dut.datapath.engine.pass;
  wire [4:0] step_count = dut.datapath.engine.step;
  wire [3:0] emit_count = dut.datapath.engine.emit_idx;

  always #5 clk = ~clk;
  freq_serial_filter dut (.clk(clk), .rst_n(rst_n), .valid_i(valid_i), .ready_o(ready_o),
    .sample_i(sample_i), .valid_o(valid_o), .ready_i(ready_i), .sample_o(sample_o));

  task automatic release_reset;
    begin
      @(negedge clk); rst_n = 1'b1;
      repeat (3) @(posedge clk);
    end
  endtask

  initial begin
    if (!$value$plusargs("vector_dir=%%s", vector_dir)) $fatal(1, "Missing vector_dir");
    $readmemh({vector_dir, "/input.hex"}, input_codes);
    $readmemh({vector_dir, "/expected.hex"}, expected_codes);
    repeat (3) @(posedge clk);
    release_reset();

    // Phase 1: stream until the engine reaches the chosen point, then reset it.
    idx = 0; cycles = 0; hit = 1'b0;
    while (!hit && cycles < 5000) begin
      @(negedge clk);
      valid_i = 1'b1; sample_i = input_codes[idx]; ready_i = 1'b1;
      case (`SCENARIO)
        0: hit = (st == 3'd2 && pass_count == 4'd4 && step_count == 5'd3);   // RUN, spectral product
        1: hit = (st == 3'd3 && emit_count == 4'd3);                         // EMIT, mid emission
        default: if (st == 3'd4) begin ready_i = 1'b0; hit = 1'b1; end       // DRAIN, last output pending
      endcase
      #1 accept = valid_i && ready_o;
      if (!hit) begin
        @(posedge clk);
        if (accept) idx = idx + 1;
      end
      cycles = cycles + 1;
    end
    if (!hit) $fatal(1, "Scenario %%0d never reached its state", `SCENARIO);
    valid_i = 1'b0;
    #1 rst_n = 1'b0;
    #1;
    if (valid_o !== 1'b0 || ready_o !== 1'b0 || sample_o !== 32'd0)
      $fatal(1, "Reset must clear the outputs asynchronously");
    repeat (3) @(posedge clk);
    release_reset();
    if (st !== 3'd0) $fatal(1, "The engine must restart in ACCEPT");

    // Phase 2: a full restart at x[0] must reproduce y[0:N] with nothing left over.
    idx = 0; out_idx = 0; cycles = 0;
    while (out_idx < N && cycles < 20000) begin
      @(negedge clk);
      ready_i = 1'b1;
      valid_i = (idx < N); sample_i = input_codes[idx];
      #1;
      accept = valid_i && ready_o;
      capture = valid_o && ready_i;
      captured = sample_o;
      @(posedge clk);
      if (accept) idx = idx + 1;
      if (capture) begin
        if (captured !== expected_codes[out_idx])
          $fatal(1, "Mismatch after reset index=%%0d expected=%%08h got=%%08h", out_idx,
                 expected_codes[out_idx], captured);
        out_idx = out_idx + 1;
      end
      cycles = cycles + 1;
    end
    if (out_idx != N) $fatal(1, "Timeout after reset: %%0d of %%0d outputs", out_idx, N);
    @(negedge clk); valid_i = 1'b0;
    for (quiet = 0; quiet < 150; quiet = quiet + 1) begin
      @(posedge clk);
      if (valid_o !== 1'b0) $fatal(1, "Extra output after the restarted frame");
    end
    $display("PASS: reset scenario %%0d, %%0d outputs after restart", `SCENARIO, N);
    $finish;
  end
endmodule
"""


@pytest.mark.parametrize("scenario,name", [(0, "RUN"), (1, "EMIT"), (2, "DRAIN")])
def test_reset_in_the_middle_of_a_block_leaves_no_trace(tmp_path, scenario, name):
    vectors = fixture.write_fixture(tmp_path / "canonical")
    bench = tmp_path / "reset_tb.sv"
    bench.write_text(RESET_TB % {})
    result = compile_and_run(
        tmp_path, [*DUT_SOURCES, bench], "reset_tb", defines=[f"SCENARIO={scenario}"],
        arguments=[f"+vector_dir={vectors}"])
    assert result.returncode == 0, f"reset in {name}\n" + result.stdout + result.stderr
    assert f"PASS: reset scenario {scenario}, 40 outputs after restart" in result.stdout
