"""
Pieces for the advanced asm-quiz videos (units 15 to 20). Traces come from
tools/vrig-trace/asm_adv-entry.ts, which steps VRIG's own X86Emulator.

The x86 walkthrough family has its own copy of a listing + register walk.
This one is separate on purpose so the two can change without stepping on
each other.
"""
from __future__ import annotations

import json
import textwrap

from manimlib import *

from vrig.mob.cpu import RegisterFile
from vrig.mob.memory import LIFT, mono, prose
from vrig.theme import T
from vrig.trace import TRACE_DIR


def hx(v: int, w: int = 8) -> str:
    return f"0x{v:0{w}x}"


def para(text: str, width: int = 60, size: int = 22, color: str | None = None, mono_font=False) -> Text:
    s = "\n".join(textwrap.wrap(text, width))
    return (mono if mono_font else prose)(s, size, color or T.text)


class AsmTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.arch = raw["arch"]
        self.instructions = raw["instructions"]
        self.quiz = raw["quiz"]
        self.win_title = raw["winTitle"]
        self.win_msg = raw["winMsg"]
        self.ip = "eip" if self.arch == "x86" else "rip"
        self.addr_w = 8 if self.arch == "x86" else 16

    @classmethod
    def load(cls, name: str) -> "AsmTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def __getitem__(self, k):
        return self.raw[k]

    @property
    def steps(self) -> list[dict]:
        return self.raw["run"]["steps"]

    def first_sentence(self) -> str:
        msg = self.win_msg
        cut = msg.find(". ")
        return msg if cut < 0 else msg[:cut + 1]


class AsmListing(VGroup):
    """addr | bytes | instruction rows, with a bar that follows execution."""

    def __init__(self, instrs: list[dict], size: int = 16, addr_w: int = 8, show_bytes: bool = True,
                 max_bytes: int = 6, show_addr: bool = True):
        self.addrs = [i["addr"] for i in instrs]
        self.rows = VGroup()
        cols = []
        for ins in instrs:
            a = mono(hx(ins["addr"], addr_w), size, T.text_dim)
            bs = " ".join(f"{b:02x}" for b in ins["bytes"][:max_bytes])
            if len(ins["bytes"]) > max_bytes:
                bs += " .."
            b = mono(bs or ".", size, T.label)
            t = mono(f"{ins['mnemonic']} {ins['operands']}".strip(), size, T.text)
            cols.append((a, b, t))
        # fixed columns so mnemonics line up
        aw = max(c[0].get_width() for c in cols)
        bw = max(c[1].get_width() for c in cols)
        for a, b, t in cols:
            row = VGroup()
            x = 0
            if show_addr:
                a.move_to(RIGHT * x, aligned_edge=LEFT)
                row.add(a)
                x += aw + 0.35
            if show_bytes:
                b.move_to(RIGHT * x, aligned_edge=LEFT)
                row.add(b)
                x += bw + 0.35
            t.move_to(RIGHT * x, aligned_edge=LEFT)
            row.add(t)
            row.text = t
            self.rows.add(row)
        self.rows.arrange(DOWN, aligned_edge=LEFT, buff=0.13)
        self.bar = BackgroundRectangle(self.rows[0], buff=0.07).set_fill(T.highlight, 0.18).set_opacity(0)
        self.bar.shift(-LIFT)
        super().__init__(self.bar, self.rows)

    def index(self, addr: int) -> int:
        return self.addrs.index(addr)

    def row(self, addr: int) -> VGroup:
        return self.rows[self.index(addr)]

    def focus(self, addr: int, color: str | None = None) -> Animation:
        line = self.row(addr)
        target = BackgroundRectangle(line, buff=0.07).set_fill(color or T.highlight, 0.2)
        target.stretch_to_fit_width(self.rows.get_width() + 0.24).align_to(self.rows, LEFT).shift(LEFT * 0.12)
        target.shift(-LIFT)
        if self.bar.is_fixed_in_frame():
            target.fix_in_frame()
        return Transform(self.bar, target)


class Flags(VGroup):
    """ZF SF CF OF, lit when set."""

    NAMES = ("ZF", "SF", "CF", "OF")

    def __init__(self, size: int = 18):
        self.items = {n: mono(n, size, T.text_dim) for n in self.NAMES}
        super().__init__(*self.items.values())
        self.arrange(RIGHT, buff=0.3)

    def show(self, flags: dict) -> list[Animation]:
        return [m.animate.set_color(T.highlight if flags.get(n) else T.text_dim) for n, m in self.items.items()]


class MemBox(VGroup):
    """
    A named struct or table in memory: title on top, one row per field,
    each row "addr  value". Rows are addressable by field index.
    """

    def __init__(self, title: str, base: int, fields: list[tuple[str, int | str]], role: str = "cell_fill",
                 size: int = 15, show_addr: bool = True, width: float | None = None):
        self.base = base
        self.cells = VGroup()
        self.values = []
        for i, (name, val) in enumerate(fields):
            box = Rectangle(width or 2.3, 0.4).set_stroke(T.grid, 1.5)
            box.set_fill(getattr(T, role), 0.85 if role != "cell_fill" else 1)
            v = mono(val if isinstance(val, str) else hx(val), size, T.text).move_to(box).shift(LIFT)
            n = mono(name, size - 2, T.text_dim).next_to(box, RIGHT, buff=0.12)
            parts = [box, v, n]
            if show_addr:
                parts.append(mono(hx(base + 4 * i), size - 3, T.text_dim).next_to(box, LEFT, buff=0.12))
            cell = VGroup(*parts)
            cell.box, cell.val, cell.name = box, v, n
            self.cells.add(cell)
            self.values.append(val)
        self.cells.arrange(DOWN, buff=0.04)
        self.title = mono(title, size + 2, T.label).next_to(self.cells, UP, buff=0.14)
        super().__init__(self.title, self.cells)

    def box(self, i: int):
        return self.cells[i].box

    def set_value(self, i: int, val, color: str | None = None) -> Animation:
        old = self.cells[i].val
        new = mono(val if isinstance(val, str) else hx(val), int(old.font_size), color or T.highlight).move_to(old)
        self.values[i] = val
        return Transform(old, new)


def pointer(a, b, color: str | None = None, angle: float = -0.6, width: float = 3) -> Arrow:
    return CurvedArrow(a, b, angle=angle).set_stroke(color or T.pointer, width).set_fill(color or T.pointer)


def regs_for(names, values: dict, width: int = 8) -> RegisterFile:
    return RegisterFile(names=names, values={n: values.get(n) for n in names}, width=width)


class QuizCard(VGroup):
    """One quiz row: Q number, a short restatement, and the value VRIG accepts."""

    def __init__(self, n: int, label: str, typed: str, width: float = 9.5):
        q = mono(f"Q{n}", 20, T.text_dim)
        lab = para(label, 62, 22, T.text)
        ans = mono(typed, 24, T.win)
        q.next_to(lab, LEFT, buff=0.35, aligned_edge=UP)
        ans.next_to(lab, RIGHT, buff=0.5).align_to(lab, UP)
        ans.set_x(width / 2, LEFT)
        self.q, self.label, self.ans = q, lab, ans
        super().__init__(q, lab, ans)


class QuizBoard(VGroup):
    def __init__(self, trace: AsmTrace, labels: list[str]):
        assert len(labels) == len(trace.quiz), "one label per VRIG question"
        self.cards = VGroup(*(QuizCard(i + 1, lab, q["typed"]) for i, (lab, q) in enumerate(zip(labels, trace.quiz))))
        self.cards.arrange(DOWN, aligned_edge=LEFT, buff=0.38)
        for c in self.cards:
            c.ans.set_x(self.cards.get_left()[0] + 9.6, LEFT)
        super().__init__(self.cards)
