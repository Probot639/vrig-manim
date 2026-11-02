"""
Pieces for VRIG's guided "step" lessons. Their traces come from
tools/vrig-trace/walk_stack-entry.ts, which replays StepControls.handleStep()
and keeps the StackSim bytes, the AuxViz panels, the log, and the exec line
after every click.

Same memory rule as memory.py: low addresses at the bottom, byte 0 of a word
on the left.
"""
from __future__ import annotations

import json
from pathlib import Path

from manimlib import *

from vrig.mob.memory import CELL, GAP, LIFT, ROW, ByteCell, mono, prose
from vrig.theme import T

TRACE_DIR = Path(__file__).parent.parent.parent / "traces"


class WalkTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.source = raw["source"]
        self.asm = raw.get("asm")
        self.steps = raw["steps"]
        self.symbols = raw["symbols"]
        lay = raw["layout"]
        self.base = lay["base"]
        self.buf_size = lay["bufSize"]
        self.canary_size = lay["canarySize"]
        self.total = lay["totalSize"]
        self.ebp_off = self.buf_size + self.canary_size
        self.ret_off = self.ebp_off + lay["ebpSize"]
        self.win_title = raw["winTitle"]
        self.win_msg = raw["winMsg"]

    @classmethod
    def load(cls, name: str) -> "WalkTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def mem(self, step: int) -> list[int]:
        return self.raw["initial"]["memory"] if step < 0 else self.steps[step]["memory"]

    def written(self, step: int) -> list[int]:
        return self.raw["initial"]["written"] if step < 0 else self.steps[step]["written"]

    def word(self, off: int, step: int = -1, size: int = 4) -> int:
        return int.from_bytes(bytes(self.mem(step)[off:off + size]), "little")

    def aux(self, step: int) -> dict:
        return self.raw["initial"]["aux"] if step < 0 else self.steps[step]["aux"]


def h32(v: int) -> str:
    return f"0x{v:08x}"


class MemColumn(VGroup):
    """
    The StackSim as rows of four bytes. `offsets` picks which word rows to
    draw. A gap between two picked offsets turns into a dotted row with the
    byte count it hides, so a 64-byte buffer doesn't eat the whole screen.
    """

    def __init__(self, tr: WalkTrace, offsets: list[int] | None = None, step: int = -1,
                 base: int | None = None, ascii_col: bool = False):
        self.tr = tr
        self.base = tr.base if base is None else base
        offsets = offsets if offsets is not None else list(range(0, tr.total, 4))
        mem, wr = tr.mem(step), tr.written(step)
        self.rows: dict[int, VGroup] = {}
        self.cells: dict[int, ByteCell] = {}
        self.addr_labels: dict[int, Text] = {}
        self.ascii: dict[int, Text] = {}
        self.show_ascii = ascii_col
        stack = VGroup()
        prev = None
        for off in offsets:
            if prev is not None and off != prev + 4:
                hidden = off - prev - 4
                dots = mono(f"... {hidden} bytes ...", 14, T.text_dim)
                stack.add(dots)
            row_cells = VGroup()
            for b in range(4):
                i = off + b
                c = ByteCell(mem[i] if i < tr.total else None)
                c.label.set_color(T.text if i < tr.total and wr[i] else T.text_dim)
                self.cells[i] = c
                row_cells.add(c)
            row_cells.arrange(RIGHT, buff=GAP)
            addr = mono(h32(self.base + off), 15, T.text_dim).next_to(row_cells, LEFT, buff=0.25)
            self.addr_labels[off] = addr
            row = VGroup(addr, row_cells)
            if ascii_col:
                a = self._ascii(mem[off:off + 4]).next_to(row_cells, RIGHT, buff=0.2)
                self.ascii[off] = a
                row.add(a)
            row.cells = row_cells
            row.addr_label = addr
            self.rows[off] = row
            stack.add(row)
            prev = off
        # bottom of the list is the lowest address
        stack.arrange(UP, buff=ROW - CELL)
        self._align(stack)
        self.stack = stack
        self.tags = VGroup()
        super().__init__(stack, self.tags)

    def _align(self, stack):
        # rows and dotted rows share a right edge for the cells, whatever the
        # address label width does
        x = max(r.cells.get_right()[0] for r in self.rows.values())
        for r in self.rows.values():
            r.shift(RIGHT * (x - r.cells.get_right()[0]))
        for m in stack:
            if m not in self.rows.values():
                m.set_x(np.mean([r.cells.get_x() for r in self.rows.values()]))

    def _ascii(self, data) -> Text:
        s = "".join(chr(b) if 0x20 < b < 0x7f else "." for b in data)
        return mono(s, 16, T.text_dim)

    def cells_in(self, start: int, end: int) -> VGroup:
        return VGroup(*(self.cells[i] for i in range(start, end) if i in self.cells))

    def boxes_in(self, start: int, end: int) -> VGroup:
        return VGroup(*(self.cells[i].box for i in range(start, end) if i in self.cells))

    def row_of(self, off: int) -> VGroup:
        return self.rows[off - off % 4]

    def sync(self, mem: list[int], written: list[int]) -> list[Animation]:
        """Animate every byte that changed, and brighten bytes VRIG marks written."""
        anims = []
        for i, c in self.cells.items():
            if i >= len(mem):
                continue
            want = T.text if written[i] else T.text_dim
            if c.value != mem[i]:
                new = c.relabel(mem[i]).set_color(T.highlight if written[i] else want)
                anims.append(Transform(c.label, new))
            elif c.label.get_color().upper() != want.upper() and not getattr(c, "painted", False):
                anims.append(c.label.animate.set_color(want))
        if self.show_ascii:
            for off, a in self.ascii.items():
                new = self._ascii(mem[off:off + 4]).move_to(a, aligned_edge=LEFT)
                if new.text != a.text:
                    anims.append(Transform(a, new))
        return anims

    def settle(self, written: list[int]) -> list[Animation]:
        """Fresh bytes go from highlight to normal once the step is read."""
        return [c.label.animate.set_color(T.text) for i, c in self.cells.items()
                if i < len(written) and written[i] and not getattr(c, "painted", False)]

    def paint(self, start: int, end: int, role: str, opacity: float = 0.85) -> list[Animation]:
        anims = []
        for i in range(start, end):
            if i in self.cells:
                c = self.cells[i]
                c.painted = role != "cell_fill"
                color = getattr(T, role)
                anims.append(c.box.animate.set_fill(color, opacity if role != "cell_fill" else 1))
                dark = role != "cell_fill" and _luma(color) > 0.55
                anims.append(c.label.animate.set_color(T.background if dark else T.text))
        return anims

    def tag(self, off: int, size: int, text: str, role: str, buff: float = 0.15) -> VGroup:
        """Bracket + name to the right of the rows holding [off, off+size)."""
        lo, hi = off - off % 4, (off + size - 1) - (off + size - 1) % 4
        rows = [r for o, r in self.rows.items() if lo <= o <= hi]
        top, bot = rows[-1], rows[0]
        right = max(r.get_right()[0] for r in self.rows.values()) + buff
        line = Line([right, bot.cells.get_bottom()[1] + 0.04, 0], [right, top.cells.get_top()[1] - 0.04, 0])
        line.set_stroke(getattr(T, role), 4)
        label = mono(text, 17, getattr(T, role)).next_to(line, RIGHT, buff=0.12)
        t = VGroup(line, label)
        self.tags.add(t)
        return t


def _luma(hexcolor: str) -> float:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hl_rect(col: MemColumn, start: int, end: int) -> VMobject:
    """Outline around the bytes VRIG says this step touched."""
    cells = col.cells_in(start, end)
    if not len(cells):
        return VMobject()
    return SurroundingRectangle(cells, buff=0.05).set_stroke(T.highlight, 2.5).shift(LIFT)


class Panel(VGroup):
    """A titled box. Used for the AuxViz panels and the rit-00 schematic."""

    def __init__(self, title: str, body: Mobject | None = None, width: float = 3.4, height: float | None = None,
                 title_color: str | None = None):
        self.body = body if body is not None else VGroup()
        h = height if height is not None else (self.body.get_height() + 0.75 if len(self.body.get_points()) or len(self.body) else 1.2)
        self.frame = RoundedRectangle(width=width, height=h, corner_radius=0.08)
        self.frame.set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.7)
        self.title = mono(title, 15, title_color or T.text_dim)
        self.title.next_to(self.frame.get_corner(UL), DR, buff=0.12)
        if len(self.body):
            self.body.next_to(self.title, DOWN, buff=0.18, aligned_edge=LEFT)
        super().__init__(self.frame, self.title, self.body)


def perm_badge(perms: str) -> VGroup:
    """R W X as three little letters, the missing ones dimmed."""
    out = VGroup()
    for ch, want in zip(perms, "RWX"):
        on = ch == want
        out.add(mono(want if on else "-", 16, (T.highlight if want == "X" else T.text) if on else T.text_dim))
    return out.arrange(RIGHT, buff=0.06)
