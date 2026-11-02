"""
Load traces written by tools/vrig-trace. A trace is VRIG's StepEngine output
for one exercise + payload, step by step, with the stack bytes after each step.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TRACE_DIR = Path(__file__).parent.parent / "traces"

HEX = r"0x([0-9a-fA-F]{8})"


@dataclass
class GadgetEvent:
    addr: int
    text: str
    pops: list[tuple[str, int]] = field(default_factory=list)  # (reg, value)
    write: tuple[int, int] | None = None  # (value, addr) for mov [reg], reg
    next_eip: int | None = None


class StackTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.source = raw["source"]
        self.symbols = raw["symbols"]
        self.gadgets = {int(k): v for k, v in raw["gadgets"].items()}
        self.flag_addr = raw["flagAddr"]
        self.magic = raw["magicValue"]
        self.payload = raw["payload"]
        self.steps = raw["steps"]

        lay = raw["layout"]
        self.base = lay["base"]
        self.buf_size = lay["bufSize"]
        self.canary_size = lay["canarySize"]
        self.total = lay["totalSize"]
        self.ebp_off = self.buf_size + self.canary_size
        self.ret_off = self.ebp_off + lay["ebpSize"]
        self.word = lay["retSize"]

    @classmethod
    def load(cls, name: str) -> "StackTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def addr(self, offset: int) -> int:
        return self.base + offset

    def word_at(self, offset: int, step: int = -1) -> int:
        mem = self.steps[step]["memory"]
        return int.from_bytes(bytes(mem[offset:offset + self.word]), "little")

    def region(self, offset: int) -> str:
        """Theme role for whatever lives at this offset in the original frame."""
        if offset < self.buf_size:
            return "buffer"
        if offset < self.ebp_off:
            return "canary"
        if offset < self.ret_off:
            return "saved_fp"
        if offset < self.ret_off + self.word:
            return "saved_ret"
        return "arg"  # caller's frame, above the return address

    def step_index(self, label_start: str) -> int:
        for i, s in enumerate(self.steps):
            if s["label"].startswith(label_start):
                return i
        raise KeyError(label_start)

    def rop_events(self) -> list[GadgetEvent]:
        """Pull the gadget-by-gadget run out of the ROP step's log lines."""
        step = self.steps[self.step_index("ROP chain")]
        events: list[GadgetEvent] = []
        for line in (l["msg"] for l in step["logs"]):
            if m := re.match(rf"Execute gadget at {HEX}: (.+)", line):
                events.append(GadgetEvent(int(m[1], 16), m[2]))
            elif m := re.match(rf"\s*pop (\w+) → {HEX}", line):
                events[-1].pops.append((m[1], int(m[2], 16)))
            elif m := re.match(rf"\s*mov \[\w+\], \w+ → writing {HEX} to address {HEX}", line):
                events[-1].write = (int(m[1], 16), int(m[2], 16))
            elif m := re.match(rf"\s*ret → pop EIP = {HEX}", line):
                events[-1].next_eip = int(m[1], 16)
        return events

    def won(self) -> bool:
        return any(s["win"] for s in self.steps)


def h32(v: int) -> str:
    return f"0x{v:08x}"
