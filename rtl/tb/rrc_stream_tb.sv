`timescale 1ns/1ps
module rrc_stream_tb;
  `include "vector_manifest.svh"

  localparam integer INPUT_BEATS = accepted_input_samples / SPC;
  localparam integer OUTPUT_BEATS = raw_output_samples / SPC;
  logic clk = 1'b0;
  logic rst_n = 1'b0;
  logic valid_i = 1'b0;
  logic ready_i = 1'b0;
  logic ready_o, valid_o;
  logic [SPC-1:0][2*DATA_WIDTH-1:0] sample_i = '0;
  logic [SPC-1:0][2*DATA_WIDTH-1:0] sample_o;
  logic [31:0] input_codes [0:input_samples-1];
  logic [31:0] expected_codes [0:output_samples-1];
  string vector_dir;

  always #5 clk = ~clk;

  `DUT_MODULE #(
    .DATA_WIDTH(DATA_WIDTH), .SAMPLES_PER_CLOCK(SPC)
`ifdef FREQ_DUT
    , .FFT_LEN(FFT_LEN), .HOP(HOP), .DISCARD_PREFIX(DISCARD_PREFIX),
    .EMIT_START(EMIT_START), .EMIT_LEN(EMIT_LEN)
`endif
  ) dut (.*);

  function automatic logic [31:0] extend_code(input logic [2*DATA_WIDTH-1:0] packed_sample);
    logic signed [15:0] i_code, q_code;
    begin
      i_code = $signed(packed_sample[DATA_WIDTH-1:0]);
      q_code = $signed(packed_sample[2*DATA_WIDTH-1:DATA_WIDTH]);
      extend_code = {q_code, i_code};
    end
  endfunction

  task automatic check_vector_file(input string filename, input integer expected_count);
    integer fd, count, status;
    string token;
    begin
      fd = $fopen(filename, "r");
      if (fd == 0) $fatal(1, "Cannot open vector %s", filename);
      count = 0;
      while (!$feof(fd)) begin
        status = $fscanf(fd, "%s", token);
        if (status == 1) begin
          if (token.len() != 8) $fatal(1, "Vector record must be 8 hex digits: %s", filename);
          for (integer digit = 0; digit < 8; digit = digit + 1)
            if (!((token[digit] >= "0" && token[digit] <= "9") ||
                  (token[digit] >= "a" && token[digit] <= "f") ||
                  (token[digit] >= "A" && token[digit] <= "F")))
              $fatal(1, "Invalid hex vector record: %s", filename);
          count = count + 1;
        end
      end
      $fclose(fd);
      if (count != expected_count)
        $fatal(1, "Vector count mismatch %s expected=%0d got=%0d", filename, expected_count, count);
    end
  endtask

  task automatic check_reset;
    if (valid_o !== 1'b0 || ready_o !== 1'b0 || sample_o !== '0)
      $fatal(1, "Reset must clear output and disable transfers");
  endtask

  task automatic reset_dut;
    @(negedge clk);
    #2 rst_n = 1'b0;
    #1 check_reset();
    @(negedge clk);
    rst_n = 1'b1;
    valid_i = 1'b1;
    sample_i = '1;
    ready_i = 1'b0;
    repeat (2) begin
      @(posedge clk);
      check_reset();
      #1;
      if (valid_o !== 1'b0 || sample_o !== '0)
        $fatal(1, "Sample accepted before synchronized reset release");
    end
    if (ready_o !== 1'b1) $fatal(1, "Reset release must use two flops");
    @(negedge clk);
    valid_i = 1'b0;
    ready_i = 1'b1;
  endtask

  task automatic reset_accepted_prefix;
    integer accepted, cycle, prefix_beats;
    begin
      accepted = 0; cycle = 0;
      // A one-beat frame has no proper nonempty prefix to abort.
      prefix_beats = INPUT_BEATS > 2 ? 2 : INPUT_BEATS - 1;
      while (accepted < prefix_beats) begin
        @(negedge clk);
        valid_i = 1'b1; ready_i = 1'b1;
        for (integer lane = 0; lane < SPC; lane = lane + 1)
          if (accepted * SPC + lane < input_samples)
            sample_i[lane] = {input_codes[accepted*SPC+lane][16 +: DATA_WIDTH],
                              input_codes[accepted*SPC+lane][0 +: DATA_WIDTH]};
          else sample_i[lane] = '0;
        @(posedge clk);
        if (ready_o === 1'b1) accepted = accepted + 1;
        #1;
        cycle = cycle + 1;
        if (cycle > 100 * (INPUT_BEATS + latency_cycles + 1))
          $fatal(1, "Timeout accepting reset prefix");
      end
      reset_dut();
      $display("Midtraffic reset prefix_accepted=%0d restart_index=0", accepted);
    end
  endtask

  task automatic run_frame(input bit robustness);
    integer sent, received, matched, cycle, first_input, first_output, last_input;
    integer bubbles, stalls, backpressure, absolute_index;
    integer accepted_source, accepted_flush, accepted_padding, emitted_samples;
    integer interval_count, ii_min, ii_max, interval_cycles, tail_stalls;
    string measured_ii;
    logic input_fire, output_stalled;
    logic [SPC-1:0][2*DATA_WIDTH-1:0] held_output;
    logic [31:0] got;
    logic [31:0] rng;
    begin
      sent = 0; received = 0; matched = 0; cycle = 0;
      first_input = -1; first_output = -1; last_input = -1;
      bubbles = 0; stalls = 0; backpressure = 0;
      interval_count = 0; ii_min = -1; ii_max = -1; tail_stalls = 0;
      accepted_source = 0; accepted_flush = 0; accepted_padding = 0; emitted_samples = 0;
      input_fire = 1'b1; rng = 32'd2026;
      while (received < OUTPUT_BEATS || sent < INPUT_BEATS) begin
        @(negedge clk);
        rng = rng ^ (rng << 13); rng = rng ^ (rng >> 17); rng = rng ^ (rng << 5);
        // Bounded ready opportunities do not rely on the PRNG. Keep tail
        // backpressure until at least one valid post-input output is held.
        ready_i = !robustness || ((cycle < 2 || cycle > 8) && (rng[1] || cycle % 8 == 0));
        if (robustness && sent >= INPUT_BEATS && tail_stalls == 0) ready_i = 1'b0;
        // A pending source transaction cannot be changed until accepted.
        if (input_fire || !valid_i) begin
          valid_i = sent < INPUT_BEATS && (!robustness || (cycle > 0 && (sent < 2 || rng[0] || cycle % 8 == 0)));
          for (integer lane = 0; lane < SPC; lane = lane + 1) begin
            if (sent * SPC + lane < input_samples)
              sample_i[lane] = {input_codes[sent*SPC+lane][16 +: DATA_WIDTH],
                                input_codes[sent*SPC+lane][0 +: DATA_WIDTH]};
            else sample_i[lane] = '0;
          end
        end
        @(posedge clk);
        if ($isunknown(ready_o) || $isunknown(valid_o))
          $fatal(1, "Unknown post-reset controls ready_o=%b valid_o=%b", ready_o, valid_o);
        input_fire = valid_i && ready_o;
        output_stalled = valid_o && !ready_i;
        held_output = sample_o;
        if (!valid_i && sent < INPUT_BEATS) bubbles = bubbles + 1;
        if (output_stalled) begin
          stalls = stalls + 1;
          if (sent >= INPUT_BEATS) tail_stalls = tail_stalls + 1;
        end
        if (valid_i && !ready_o) backpressure = backpressure + 1;
        if (input_fire) begin
          if (first_input < 0) first_input = cycle;
          if (!robustness && last_input >= 0) begin
            interval_cycles = cycle - last_input;
            if (interval_count == 0 || interval_cycles < ii_min) ii_min = interval_cycles;
            if (interval_count == 0 || interval_cycles > ii_max) ii_max = interval_cycles;
            interval_count = interval_count + 1;
          end
`ifdef RRC_SHELL_FIXTURE
          if (!robustness && last_input >= 0 && cycle - last_input != 1)
            $fatal(1, "Shell II must be measured as one cycle, not inferred from SPC");
`endif
          last_input = cycle;
          for (integer lane = 0; lane < SPC; lane = lane + 1) begin
            if (sent * SPC + lane < input_samples)
              accepted_source = accepted_source + 1;
            else if (sent * SPC + lane < input_samples + flush_samples)
              accepted_flush = accepted_flush + 1;
            else accepted_padding = accepted_padding + 1;
          end
          sent = sent + 1;
        end
        if (valid_o) begin
          if ($isunknown(sample_o)) $fatal(1, "X/Z in a valid output");
          if (first_output < 0) begin
            first_output = cycle;
            if (!robustness && first_output - first_input != latency_cycles)
              $fatal(1, "Latency mismatch expected=%0d got=%0d", latency_cycles, first_output-first_input);
          end
        end
        if (valid_o && ready_i) begin
          if (received >= OUTPUT_BEATS) $fatal(1, "Unexpected extra output beat");
          for (integer lane = 0; lane < SPC; lane = lane + 1) begin
            absolute_index = received * SPC + lane + latency_samples;
            if (absolute_index >= valid_start && absolute_index < valid_start + valid_len) begin
              got = extend_code(sample_o[lane]);
              if (got !== expected_codes[absolute_index])
                $fatal(1, "Mismatch index=%0d expected=%08h got=%08h", absolute_index,
                       expected_codes[absolute_index], got);
              matched = matched + 1;
            end
          end
          received = received + 1;
          emitted_samples = emitted_samples + SPC;
`ifdef RRC_SHELL_FIXTURE
          if (received > sent) $fatal(1, "Shell invented an output");
`endif
        end
        #1;
        if (output_stalled && (valid_o !== 1'b1 || sample_o !== held_output))
          $fatal(1, "Output must hold under backpressure");
        cycle = cycle + 1;
        if (cycle > 100 * (INPUT_BEATS + OUTPUT_BEATS + latency_cycles + 1))
          $fatal(1, "Timeout sent=%0d received=%0d matched=%0d", sent, received, matched);
      end
      @(negedge clk);
      valid_i = 1'b0; ready_i = 1'b1;
      repeat (latency_cycles + 3) begin
        @(posedge clk);
        if ($isunknown(ready_o) || $isunknown(valid_o))
          $fatal(1, "Unknown post-reset controls ready_o=%b valid_o=%b", ready_o, valid_o);
        if (valid_o !== 1'b0) $fatal(1, "Extra or duplicated output after frame");
      end
      if (matched != valid_len) $fatal(1, "Valid window count mismatch");
      if (accepted_source != input_samples || accepted_flush != flush_samples ||
          accepted_padding != transport_padding_samples ||
          accepted_source + accepted_flush + accepted_padding != accepted_input_samples ||
          emitted_samples != raw_output_samples)
        $fatal(1, "Physical source/flush/padding/raw count mismatch");
`ifdef RRC_SHELL_FIXTURE
      if (received != sent) $fatal(1, "Shell accepted/emitted count mismatch");
`endif
      // One beat can stall at the tail without backpressuring another input.
      if (robustness && (bubbles == 0 || tail_stalls == 0 ||
          (INPUT_BEATS >= 2 && (stalls == 0 || backpressure == 0))))
        $fatal(1, "Robustness run did not exercise bubbles, stalls and ready_o loss");
      measured_ii = "undefined";
      if (interval_count > 0 && ii_min == ii_max) measured_ii = $sformatf("%0d", ii_min);
      $display("Frame robustness=%0d compared=%0d accepted_beats=%0d emitted_beats=%0d cycles=%0d source_samples=%0d flush_samples=%0d transport_padding_samples=%0d accepted_input_samples=%0d raw_output_samples=%0d interval_count=%0d ii_min=%0d ii_max=%0d measured_ii=%s tail_stalls=%0d",
                robustness, matched, sent, received, cycle, accepted_source, accepted_flush,
                accepted_padding, accepted_source + accepted_flush + accepted_padding, emitted_samples,
                interval_count, ii_min, ii_max, measured_ii, tail_stalls);
    end
  endtask

  initial begin
`ifdef RRC_TRANSPORT_DUT
`ifndef RRC_SHELL_FIXTURE
    $fatal(1, "T03 transport DUT requires a shell fixture; RRC vector matching is not implemented");
`endif
`endif
    if (DATA_WIDTH < 2 || DATA_WIDTH > 16 || SPC < 1 || input_samples < 1 || output_samples < 1 ||
        valid_start < 0 || valid_len < 1 || valid_start + valid_len > output_samples ||
        latency_samples < 0 || latency_samples > valid_start || latency_cycles < 0)
      $fatal(1, "Invalid manifest dimensions/window/latency; records support at most 16 bits");
    if (flush_samples < 0 || transport_padding_samples < 0 ||
        accepted_input_samples < 1 || accepted_input_samples < input_samples || raw_output_samples < 1 ||
        accepted_input_samples != input_samples + flush_samples + transport_padding_samples ||
        accepted_input_samples % SPC != 0 || raw_output_samples % SPC != 0 ||
        transport_padding_samples != (SPC - (input_samples + flush_samples) % SPC) % SPC ||
        raw_output_samples + latency_samples < valid_start + valid_len)
      $fatal(1, "Invalid manifest transport counts");
    if (FFT_LEN != rrc_pkg::FFT_LEN || HOP != rrc_pkg::HOP ||
        DISCARD_PREFIX != rrc_pkg::DISCARD_PREFIX || EMIT_START != rrc_pkg::EMIT_START ||
        EMIT_LEN != rrc_pkg::EMIT_LEN || block_cadence != HOP)
      $fatal(1, "Manifest block parameters disagree with the accepted baseline");
    if (!$value$plusargs("vector_dir=%s", vector_dir)) $fatal(1, "Missing vector_dir");
    check_vector_file({vector_dir, "/input.hex"}, input_samples);
    check_vector_file({vector_dir, "/expected.hex"}, output_samples);
    $readmemh({vector_dir, "/input.hex"}, input_codes);
    $readmemh({vector_dir, "/expected.hex"}, expected_codes);
    for (integer n = 0; n < input_samples; n = n + 1)
      if ($isunknown(input_codes[n]) || extend_code({input_codes[n][16 +: DATA_WIDTH],
          input_codes[n][0 +: DATA_WIDTH]}) !== input_codes[n])
        $fatal(1, "Invalid input code/sign extension index=%0d", n);
    for (integer n = 0; n < output_samples; n = n + 1)
      if ($isunknown(expected_codes[n]) || extend_code({expected_codes[n][16 +: DATA_WIDTH],
          expected_codes[n][0 +: DATA_WIDTH]}) !== expected_codes[n])
        $fatal(1, "Invalid expected code/sign extension index=%0d", n);

    reset_dut();
`ifdef RRC_SHELL_FIXTURE
    // Reset a pending, stalled transaction and prove no stale output survives.
    @(negedge clk); valid_i = 1'b1; sample_i = '1; ready_i = 1'b0;
    @(posedge clk); #1;
    if (valid_o !== 1'b1 || ready_o !== 1'b0) $fatal(1, "Pending shell transaction not created");
    reset_dut();
`endif
    run_frame(1'b0);
    reset_dut();
    reset_accepted_prefix();
    run_frame(1'b1);
`ifdef RRC_SHELL_FIXTURE
    $display("PASS: shell stream W=%0d SPC=%0d (reset, latency, bubbles, stalls)", DATA_WIDTH, SPC);
`else
    $display("PASS: vector window W=%0d SPC=%0d compared=%0d", DATA_WIDTH, SPC, valid_len);
`endif
    $finish;
  end
endmodule
