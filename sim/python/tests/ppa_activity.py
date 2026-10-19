"""Activity window of a gate-level run as SAIF, for annotated power (T41 #52).

The testbench dumps the continuous run of the canonical frame (``+activity_vcd``)
from its first cycle until ``$dumpoff`` at the negedge after its last output, so
the VCD holds whole clock cycles. OpenSTA 2.6.0 cannot use that VCD as is:
``read_vcd`` measures every signal from time 0 to the last timestamp, so the
reset before the window would count as idle time. This module streams the VCD
once and writes the SAIF of the window: per name, the time at 0, 1 and X/Z and
the 0/1 transition count over ``DURATION = end - start``. OpenSTA reads it with
``read_saif -scope``. On request it also writes the window as a VCD that starts
at time 0, which ``read_vcd`` measures correctly: the cross-check of this
conversion.

Only the DUT scope and the level below it are kept: the netlist's ports and
nets, and the ports of every cell instance, which are the pins OpenSTA
annotates. The testbench never dumps cell model internals
(``$dumpvars(2, dut)``). Standard library only.
"""

import argparse
import gzip
import json
from pathlib import Path
import re


# Characters an unquoted SAIF identifier may hold (OpenSTA SaifLex.ll ``ID``).
_SAIF_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_$\[\]\\.]*")
_RANGE = re.compile(r"\[(-?\d+)(?::(-?\d+))?\]")


class _Bit:
    """Durations at 0, 1 and X/Z plus the 0/1 transition count of one dumped bit."""

    __slots__ = ("value", "since", "t0", "t1", "tx", "tc")

    def __init__(self, value: str, since: int):
        self.value, self.since = value, since
        self.t0 = self.t1 = self.tx = self.tc = 0

    def close(self, time: int) -> None:
        span = time - self.since
        if self.value == "0":
            self.t0 += span
        elif self.value == "1":
            self.t1 += span
        else:
            self.tx += span
        self.since = time

    def change(self, value: str, time: int) -> None:
        if value == self.value:
            return
        self.close(time)
        if {value, self.value} == {"0", "1"}:
            self.tc += 1
        self.value = value


def bit_names(name: str, width: int, declared_range: str | None) -> list[str]:
    """Return the per-bit names of a VCD variable, most significant first."""
    if declared_range is None:
        if width != 1:
            raise ValueError(f"{name}: a {width}-bit VCD variable needs its range")
        return [name]
    match = _RANGE.fullmatch(declared_range)
    if match is None:
        raise ValueError(f"{name}: unsupported VCD range {declared_range!r}")
    if match.group(2) is None:
        if width != 1:
            raise ValueError(f"{name}: range {declared_range} does not hold {width} bits")
        return [f"{name}[{match.group(1)}]"]
    msb, lsb = int(match.group(1)), int(match.group(2))
    step = -1 if msb >= lsb else 1
    indices = range(msb, lsb + step, step)
    if len(indices) != width:
        raise ValueError(f"{name}: range {declared_range} does not hold {width} bits")
    return [f"{name}[{index}]" for index in indices]


def expand(value: str, width: int) -> str:
    """Left-extend a VCD vector value to ``width`` bits (with X/Z when it starts with one)."""
    value = value.lower()
    if not value or len(value) > width:
        raise ValueError(f"vector value {value!r} does not fit {width} bits")
    return value.rjust(width, value[0] if value[0] in "xz" else "0")


def _read_header(stream, scope: tuple[str, ...], shifted) -> dict[str, list[tuple[tuple[str, ...], list[str]]]]:
    """Return the dumped variables inside ``scope`` (one level deep) by VCD identifier code."""
    variables: dict[str, list[tuple[tuple[str, ...], list[str]]]] = {}
    path: list[str] = []
    tokens: list[str] = []
    for line in stream:
        if shifted is not None:
            shifted.write(line)
        tokens += line.split()
        if not tokens or tokens[-1] != "$end":
            continue
        keyword, body = tokens[0], tokens[1:-1]
        tokens = []
        if keyword == "$timescale" and "".join(body) != "1ps":
            raise ValueError(f"the testbench dumps with a 1 ps timescale, got {' '.join(body)}")
        if keyword == "$scope":
            path.append(body[1])
        elif keyword == "$upscope":
            path.pop()
        elif keyword == "$var":
            kind, width, code, name = body[0], int(body[1]), body[2], body[3]
            inside = tuple(path[:len(scope)]) == scope and len(path) - len(scope) in (0, 1)
            if inside and kind in ("wire", "reg"):
                names = bit_names(name, width, body[4] if len(body) > 4 else None)
                variables.setdefault(code, []).append((tuple(path[len(scope):]), names))
        elif keyword == "$enddefinitions":
            return variables
    raise ValueError("VCD header has no $enddefinitions")


def _read_window(stream, widths: dict[str, int], shifted) -> tuple[int, int, dict[str, list[_Bit]]]:
    """Return the window start, its end (``$dumpoff``) and every tracked bit, closed at the end."""
    bits: dict[str, list[_Bit]] = {}
    start = time = None

    def values(code: str, value: str) -> None:
        if code not in widths:
            return
        if code in bits:
            for bit, char in zip(bits[code], value):
                bit.change(char, time)
        elif time == start:
            bits[code] = [_Bit(char, time) for char in value]
        else:
            raise ValueError(f"VCD variable {code} has no value at the window start")

    for line in stream:
        line = line.strip()
        if not line:
            continue
        head = line[0]
        if head == "#":
            time = int(line[1:])
            start = time if start is None else start
            line = f"#{time - start}"
        elif head in "01xzXZ":
            values(line[1:], head.lower())
        elif head in "bB":
            value, code = line[1:].split()
            if code in widths:
                values(code, expand(value, widths[code]))
        elif line.startswith("$dumpoff"):
            missing = set(widths) - set(bits)
            if missing:
                raise ValueError(f"{len(missing)} VCD variables have no value at the window start")
            for code_bits in bits.values():
                for bit in code_bits:
                    bit.close(time)
            return start, time, bits
        elif head not in "rR$":
            raise ValueError(f"unexpected VCD line {line[:40]!r}")
        if shifted is not None:
            shifted.write(line + "\n")
    raise ValueError("the activity window was never closed with $dumpoff")


def vcd_to_saif(vcd: Path, saif: Path, scope: tuple[str, ...] = ("rrc_stream_tb", "dut"),
                window_ns: tuple[float, float] | None = None, window_vcd: Path | None = None) -> dict:
    """Write the SAIF of the dumped window of ``vcd`` (``.gz`` output when ``saif`` ends in ``.gz``).

    ``window_ns`` is the window the testbench reported (``Activity window
    start_ns=... end_ns=...``); the VCD must start and end exactly there.
    ``window_vcd`` also receives the window as a VCD starting at time 0.
    Returns the window, every name written (``instance/pin``, a port bit or a
    net) and the names a SAIF identifier cannot carry (escaped net names;
    OpenSTA annotates pins, not nets).
    """
    shifted = open(window_vcd, "w", encoding="ascii") if window_vcd is not None else None
    try:
        with open(vcd, encoding="ascii") as stream:
            variables = _read_header(stream, scope, shifted)
            widths = {code: len(entries[0][1]) for code, entries in variables.items()}
            start, end, bits = _read_window(stream, widths, shifted)
    finally:
        if shifted is not None:
            shifted.close()
    if window_ns is not None:
        expected = tuple(round(value * 1000) for value in window_ns)
        if (start, end) != expected:
            raise ValueError(f"{vcd}: dumped window {start}-{end} ps differs from the reported {expected}")
    # One SAIF entry per (instance, name); aliases of one VCD code share its counts.
    owners: dict[tuple[str, ...], dict[str, _Bit]] = {}
    for code, entries in variables.items():
        for owner, names in entries:
            for name, bit in zip(names, bits[code]):
                owners.setdefault(owner, {})[name] = bit
    written, unrepresentable = [], []
    opener = gzip.open if str(saif).endswith(".gz") else open
    with opener(saif, "wt", encoding="ascii") as out:
        out.write('(SAIFILE\n(SAIFVERSION "2.0")\n(DIRECTION "backward")\n(DESIGN )\n')
        out.write('(PROGRAM_NAME "sim/python/tests/ppa_activity.py")\n(DIVIDER / )\n')
        out.write(f"(TIMESCALE 1 ps)\n(DURATION {end - start})\n")
        for level in scope:
            out.write(f"(INSTANCE {level}\n")
        for owner in sorted(owners):
            entries = []
            for name, bit in sorted(owners[owner].items()):
                full = "/".join((*owner, name))
                if all(_SAIF_ID.fullmatch(part) for part in (*owner, name)):
                    entries.append(f"({name} (T0 {bit.t0}) (T1 {bit.t1}) (TX {bit.tx}) (TC {bit.tc}))\n")
                    written.append(full)
                else:
                    unrepresentable.append(full)
            if not entries:
                continue
            out.write((f"(INSTANCE {owner[0]}\n" if owner else "") + "(NET\n" + "".join(entries) + ")\n"
                      + (")\n" if owner else ""))
        out.write(")" * len(scope) + "\n)\n")
    return {
        "scope": "/".join(scope),
        "window_start_ps": start,
        "window_end_ps": end,
        "duration_ps": end - start,
        "written_names": written,
        "unrepresentable_names": unrepresentable,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the SAIF of a testbench activity window")
    parser.add_argument("vcd", type=Path)
    parser.add_argument("saif", type=Path)
    parser.add_argument("--scope", default="rrc_stream_tb/dut")
    parser.add_argument("--window-ns", type=float, nargs=2, metavar=("START", "END"))
    parser.add_argument("--window-vcd", type=Path, help="also write the window as a VCD starting at time 0")
    arguments = parser.parse_args()
    summary = vcd_to_saif(arguments.vcd, arguments.saif, tuple(arguments.scope.split("/")),
                          tuple(arguments.window_ns) if arguments.window_ns else None, arguments.window_vcd)
    summary["written_names"] = len(summary["written_names"])
    summary["unrepresentable_names"] = len(summary["unrepresentable_names"])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
