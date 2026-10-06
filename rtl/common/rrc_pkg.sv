`timescale 1ns/1ps
package rrc_pkg;
  parameter integer DATA_WIDTH = 16;
  parameter integer SAMPLES_PER_CLOCK = 1;
  parameter integer FFT_LEN = 16;
  parameter integer HOP = 8;
  parameter integer DISCARD_PREFIX = 8;
  parameter integer EMIT_START = DISCARD_PREFIX;
  parameter integer EMIT_LEN = FFT_LEN - DISCARD_PREFIX;
endpackage
