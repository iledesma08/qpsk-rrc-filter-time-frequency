"""T42 (#53): the unfolded frequency engine (F-U4, F-U8) against the serial one on arbitrary codes.

The T22 frames are QPSK: they reach no RNE tie and no output saturation, so matching them cannot
tell a lane that rounds or wires a butterfly differently. Here three engines, U = 1, 4 and 8, run the
same stream of random, full-scale and alternating-extreme blocks, each with its own bubbles and sink
stalls, and every raw output must be equal bit for bit. The elaboration limits and the reset in the
middle of a block are in test_rtl_config.py and test_rtl_freq_serial.py. Standard library only.
"""

from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "rtl" / "common"
SOURCES = [COMMON / "rrc_pkg.sv", COMMON / "rrc_freq_pkg.sv", COMMON / "rrc_freq_engine.sv"]
pytestmark = pytest.mark.skipif(
    not shutil.which("iverilog") or not shutil.which("vvp"),
    reason="Icarus/vvp checks run in the required RTL CI job",
)

DIFFERENTIAL_TB = """`timescale 1ns/1ps
module diff_tb;
  localparam integer BLOCKS = 64;
  localparam integer N = BLOCKS * 8;        // accepted samples: 64 blocks, the last two are zeros
  logic clk = 1'b0, rst_sync_n = 1'b0;
  logic [31:0] input_mem [0:N-1];
  logic [2:0] done;
  always #5 clk = ~clk;

  integer i, b;
  initial begin
    for (i = 0; i < N; i = i + 1) begin
      b = i / 8;
      case (b %% 4)
        0: input_mem[i] = $urandom;                                     // arbitrary full-range codes
        1: input_mem[i] = 32'h8000_7fff;                                // I = +max, Q = -min
        2: input_mem[i] = (i %% 2) ? 32'h7fff_8000 : 32'h8000_7fff;     // alternating extremes
        default: input_mem[i] = {{{12{1'b0}}, 4'($urandom)}, 12'h000} ^ {16'h0, 8'h00, 8'($urandom)};
      endcase
      if (b >= BLOCKS - 2) input_mem[i] = 32'd0;                       // flush: the history drains
    end
  end

  genvar g;
  generate
    for (g = 0; g < 3; g = g + 1) begin : e
      localparam integer LANES = (g == 0) ? 1 : ((g == 1) ? 4 : 8);
      logic valid_i, ready_o, valid_o, ready_i;
      logic [31:0] sample_i, sample_o;
      logic [31:0] out_mem [0:N-1];
      logic [31:0] lfsr;
      integer sent, got;
      initial begin
        valid_i = 1'b0; ready_i = 1'b1; sample_i = 32'd0; lfsr = 32'hACE1_0001 + g * 32'h1357; sent = 0; got = 0;
        done[g] = 1'b0;
      end
      rrc_freq_engine #(.U(LANES)) dut (
        .clk(clk), .rst_sync_n(rst_sync_n), .valid_i(valid_i), .ready_o(ready_o), .sample_i(sample_i),
        .valid_o(valid_o), .ready_i(ready_i), .sample_o(sample_o));
      // Own bubbles and sink stalls per engine: the cadence differs, the codes may not.
      always @(negedge clk) if (rst_sync_n) begin
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        valid_i <= (sent < N) && (lfsr[2:0] != 3'd0);
        sample_i <= input_mem[(sent < N) ? sent : 0];
        ready_i <= (lfsr[6:4] != 3'd0);
      end
      always @(posedge clk) if (rst_sync_n) begin
        if (valid_i && ready_o) sent <= sent + 1;
        if (valid_o && ready_i) begin
          if ($isunknown(sample_o)) $fatal(1, "X/Z in an output of U=%%0d", LANES);
          out_mem[got] <= sample_o;
          got <= got + 1;
          if (got == N - 1) done[g] <= 1'b1;
        end
      end
    end
  endgenerate

  integer k, mismatches, saturated;
  logic [15:0] re_code, im_code;
  initial begin
    repeat (3) @(posedge clk);
    @(negedge clk) rst_sync_n = 1'b1;
    repeat (200000) begin
      @(posedge clk);
      if (&done) begin
        mismatches = 0; saturated = 0;
        for (k = 0; k < N; k = k + 1) begin
          if (e[1].out_mem[k] !== e[0].out_mem[k] || e[2].out_mem[k] !== e[0].out_mem[k]) begin
            if (mismatches < 4)
              $display("Mismatch output=%%0d U1=%%08h U4=%%08h U8=%%08h", k, e[0].out_mem[k], e[1].out_mem[k],
                       e[2].out_mem[k]);
            mismatches = mismatches + 1;
          end
          re_code = e[0].out_mem[k][15:0];
          im_code = e[0].out_mem[k][31:16];
          if (re_code == 16'h7fff || re_code == 16'h8000 || im_code == 16'h7fff || im_code == 16'h8000)
            saturated = saturated + 1;
        end
        $display("compared=%%0d mismatches=%%0d saturated=%%0d", N, mismatches, saturated);
        if (mismatches != 0) $fatal(1, "F-U4/F-U8 differ from the serial engine");
        $display("PASS: U=1, U=4 and U=8 agree bit for bit");
        $finish;
      end
    end
    $fatal(1, "Timeout: not every engine emitted %%0d outputs", N);
  end
endmodule
"""


def run_differential(tmp_path, sources=SOURCES):
    bench = tmp_path / "diff_tb.sv"
    bench.write_text(DIFFERENTIAL_TB % {})
    binary = tmp_path / "diff_tb.out"
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-Wall", "-s", "diff_tb", "-o", str(binary), *map(str, sources), str(bench)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(["vvp", str(binary)], cwd=tmp_path, capture_output=True, text=True, timeout=300, check=False)


def test_the_lane_counts_agree_bit_for_bit_on_arbitrary_and_full_scale_codes(tmp_path):
    result = run_differential(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: U=1, U=4 and U=8 agree bit for bit" in result.stdout
    saturated = int(re.search(r"saturated=(\d+)", result.stdout).group(1))
    # The check is only worth something if the output saturation path ran.
    assert saturated > 0, result.stdout


@pytest.mark.parametrize("mutation", [
    # A lane that reads the wrong twiddle (only a lane count above 1 has lane 1).
    ("wire [2:0] k_idx = k_full[2:0];", "wire [2:0] k_idx = (l == 1) ? (k_full[2:0] ^ 3'd1) : k_full[2:0];"),
    # A lane that writes its b operand back to the a position (only U > 1 lanes share a pass).
    ("wr_re[ib_q[i]] <= wb_re[i];", "wr_re[ib_q[i]] <= (i == 1) ? wa_re[i] : wb_re[i];"),
], ids=["twiddle-of-lane-1", "write-back-of-lane-1"])
def test_the_differential_check_catches_a_lane_mutant(tmp_path, mutation):
    original, mutant = mutation
    engine = (COMMON / "rrc_freq_engine.sv").read_text()
    assert engine.count(original) == 1
    mutated = tmp_path / "rrc_freq_engine.sv"
    mutated.write_text(engine.replace(original, mutant))
    result = run_differential(tmp_path, [COMMON / "rrc_pkg.sv", COMMON / "rrc_freq_pkg.sv", mutated])
    assert result.returncode != 0, "the mutant survived: " + result.stdout
    assert "Mismatch output=" in result.stdout or "differ from the serial engine" in result.stdout
