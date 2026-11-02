"""
Pieces for the ARM and MIPS asm-quiz exercises (unit13-arm, unit14-mips).
Everything reads an ArchTrace, which is VRIG's own ArmEmulator / MipsEmulator
stepped one instruction at a time by tools/vrig-trace/arch-entry.ts.

The x86 version of these lives in vrig/mob/asm_x86.py. The register files look
the same, but the trace shapes differ enough (NZCV vs a MIPS delay-slot flag,
a pc that the ARM emulator reads as pc+8) that this is its own module rather
than a parameter on the x86 one.
"""
from __future__ import annotations

import json
import re

from manimlib import *

from vrig.mob.memory import LIFT, mono, prose
from vrig.theme import T
from vrig.trace import TRACE_DIR

# r0-r12 are the general regs; r13/r14/r15 show as sp/lr/pc the way disassembly
# prints them. fp is r11 by convention but VRIG's emulator keeps a separate
# "fp" key, so treat it as its own name.
ARM_GP = [f"r{i}" for i in range(13)]
ARM_PTR = ["r13", "r14", "r15"]
ARM_SHOW = {"r13": "sp", "r14": "lr", "r15": "pc"}
ARM_REG_RE = re.compile(r"\b(r1[0-5]|r[0-9]|sp|lr|pc|fp)\b")

MIPS_GP = ["$v0", "$v1", "$a0", "$a1", "$a2", "$a3"] + [f"$t{i}" for i in range(10)] + [f"$s{i}" for i in range(8)]
MIPS_PTR = ["$sp", "$fp", "$ra", "pc"]
MIPS_REG_RE = re.compile(r"\$\w+")

ARM_FLAGS = ["N", "Z", "C", "V"]


class ArchTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.arch = raw["arch"]
        self.ins = raw["instructions"]
        self.steps = raw["steps"]
        self.quiz = raw["quiz"]
        for i in self.ins:
            i["text"] = f"{i['mnemonic']} {i['operands']}".strip()
        self.by_addr = {i["addr"]: n for n, i in enumerate(self.ins)}
        self.sp = "r13" if self.arch == "arm" else "$sp"

    @classmethod
    def load(cls, name: str) -> "ArchTrace":
        return cls(json.loads((TRACE_DIR / f"{name}.json").read_text()))

    @property
    def is_arm(self) -> bool:
        return self.arch == "arm"

    def state(self, i: int) -> dict:
        return self.raw["initial"] if i < 0 else self.steps[i]

    def regs(self, i: int) -> dict:
        return self.state(i)["regs"]

    def flags(self, i: int) -> dict:
        return self.state(i)["flags"]

    def shown_regs(self) -> list[str]:
        gp, ptr = (ARM_GP, ARM_PTR) if self.is_arm else (MIPS_GP, MIPS_PTR)
        rx = ARM_REG_RE if self.is_arm else MIPS_REG_RE
        used = {self._canon(r) for r in self.raw["initialRegs"]}
        for ins in self.ins:
            used |= {self._canon(m) for m in rx.findall(ins["operands"])}
        for i in range(len(self.steps)):
            before, after = self.regs(i - 1), self.regs(i)
            used |= {r for r in after if after[r] != before.get(r, 0)}
        out = [r for r in gp if r in used]
        # fp is written by arm-68's prologue but isn't in the canonical list
        if self.is_arm and "fp" in used:
            out.append("fp")
        return out + ptr

    def _canon(self, name: str) -> str:
        n = name.lower() if self.is_arm else name
        return {"sp": "r13", "lr": "r14", "pc": "r15"}.get(n, n) if self.is_arm else n

    def disp_name(self, reg: str) -> str:
        return ARM_SHOW.get(reg, reg) if self.is_arm else reg

    # -- memory -----------------------------------------------------------

    def mem_words(self) -> list[int]:
        return self.raw["memWords"]

    def word_at(self, i: int, addr: int) -> int:
        return self.state(i)["memory"].get(f"0x{addr & 0xFFFFFFFF:x}", 0)

    def live_words(self, i: int) -> set[int]:
        """Words seeded in initialMemory or written by step i or earlier."""
        live = set()
        for m in self.raw["initialMemory"]:
            for off in range(0, m["size"], 4):
                live.add((m["addr"] + off) & 0xFFFFFFFF)
        for s in self.steps[: i + 1]:
            for w in s["writes"]:
                live.add((w["addr"] & ~3) & 0xFFFFFFFF)
        return live

    def touches_stack(self) -> bool:
        base = self.raw.get("stackBase")
        if not base:
            return False
        return any(abs(a - base) <= 0x200 for a in self.mem_words())

    def stack_words(self) -> list[int]:
        base = self.raw["stackBase"]
        return sorted(a for a in self.mem_words() if abs(a - base) <= 0x200)

    def data_words(self) -> list[int]:
        st = set(self.stack_words()) if self.touches_stack() else set()
        return sorted(a for a in self.mem_words() if a not in st)


def vhex(v: int, w: int = 8) -> str:
    return f"0x{int(v) & 0xFFFFFFFF:0{w}x}"


class AsmListing(VGroup):
    """
    The instruction stream, addresses on the left. A focus bar marks the
    instruction VRIG fetched. On ARM that is not always where pc points, and
    the pc marker shows the gap.
    """

    def __init__(self, tr: ArchTrace, size: int = 15):
        self.tr = tr
        aw = len(f"{max(i['addr'] for i in tr.ins):x}")
        self.rows = {}
        lines = VGroup()
        for n, ins in enumerate(tr.ins):
            addr = mono(f"{ins['addr']:0{aw}x}", size - 2, T.text_dim)
            body = mono(ins["text"], size, T.label)
            row = VGroup(addr, body).arrange(RIGHT, buff=0.3, aligned_edge=DOWN)
            self.rows[n] = row
            lines.add(row)
        lines.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        self.lines = lines
        self.bar = self._bar_for(self.rows[0]).set_opacity(0)
        super().__init__(self.bar, lines)

    def _bar_for(self, row) -> Mobject:
        bar = Rectangle(self.lines.get_width() + 0.3, row.get_height() + 0.14)
        bar.set_stroke(width=0).set_fill(T.highlight, 0.16)
        bar.move_to(row).align_to(self.lines, LEFT).shift(LEFT * 0.15 - LIFT)
        return bar

    def focus(self, addr: int, role: str = "highlight") -> Animation:
        n = self.tr.by_addr[addr]
        target = self._bar_for(self.rows[n]).set_fill(getattr(T, role), 0.16 if role == "highlight" else 0.3)
        return Transform(self.bar, target)

    def body(self, addr: int) -> Text:
        return self.rows[self.tr.by_addr[addr]][1]

    def pc_marker(self) -> VGroup:
        tri = Triangle().set_height(0.16).set_fill(T.pointer, 1).set_stroke(width=0).rotate(-PI / 2)
        lab = mono("pc", 13, T.pointer)
        return VGroup(lab, tri).arrange(RIGHT, buff=0.05)

    def place_left(self, marker: VGroup, addr: int) -> VGroup:
        row = self.rows.get(self.tr.by_addr.get(addr, -1))
        x = self.lines.get_left()[0] - 0.2
        y = row.get_y() if row is not None else self.lines.get_top()[1] + 0.3
        return marker.move_to([x, y, 0], aligned_edge=RIGHT)

    def jump_arrow(self, a: int, b: int, role: str = "highlight") -> Mobject:
        x = self.lines.get_left()[0] - 0.12
        p, q = self.rows[self.tr.by_addr[a]].get_left(), self.rows[self.tr.by_addr[b]].get_left()
        p, q = np.array([x, p[1], 0]), np.array([x, q[1], 0])
        arc = ArcBetweenPoints(p, q, angle=PI * 0.8 if q[1] < p[1] else -PI * 0.8)
        arc.set_stroke(getattr(T, role), 3)
        tip = Triangle().set_height(0.12).set_fill(getattr(T, role), 1).set_stroke(width=0)
        tip.rotate(-PI / 2).move_to(q + LEFT * 0.04)
        return VGroup(arc, tip)


class RegFile(VGroup):
    """Register rows. A row that changed on the step lights up until the next."""

    def __init__(self, tr: ArchTrace, names: list[str], values: dict, size: int = 16, title: str = "registers"):
        self.tr = tr
        self.size = size
        self.names = names
        self.rows, self.glow = {}, {}
        self.values = {n: values.get(n, 0) for n in names}
        rows = VGroup()
        labw = max(len(tr.disp_name(n)) for n in names)
        for n in names:
            name = mono(tr.disp_name(n).ljust(labw), size, T.label)
            val = self._val(self.values[n])
            row = VGroup(name, val).arrange(RIGHT, buff=0.3)
            self.rows[n] = row
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        right = max(r[1].get_right()[0] for r in rows)
        for r in rows:
            r[1].shift(RIGHT * (right - r[1].get_right()[0]))
        self.body = rows
        self.bg = SurroundingRectangle(rows, buff=0.2).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.9)
        self.bg.shift(-LIFT)
        parts = [self.bg, rows]
        for n, r in self.rows.items():
            g = Rectangle(self.bg.get_width() - 0.08, r.get_height() + 0.08).set_stroke(width=0)
            g.set_fill(T.highlight, 0).move_to(r).set_x(self.bg.get_x())
            self.glow[n] = g
            parts.insert(1, g)
        self.heading = mono(title, 14, T.text_dim).next_to(self.bg, UP, buff=0.1, aligned_edge=LEFT)
        parts.append(self.heading)
        self.lit = set()
        super().__init__(*parts)

    k = 1.0

    def _val(self, v: int, color=None) -> Text:
        return mono(vhex(v), self.size, color or T.text).scale(self.k)

    def update_to(self, values: dict, quiet=()) -> list[Animation]:
        anims = []
        for n in list(self.lit):
            anims.append(self.rows[n][1].animate.set_color(T.text))
            anims.append(self.glow[n].animate.set_fill(opacity=0))
        self.lit.clear()
        for n in self.names:
            v = values.get(n, 0)
            if v == self.values[n]:
                continue
            self.values[n] = v
            loud = n not in quiet
            old = self.rows[n][1]
            new = self._val(v, T.highlight if loud else T.text).move_to(old, aligned_edge=RIGHT)
            anims = [a for a in anims if getattr(a, "mobject", None) is not old]
            anims.append(Transform(old, new))
            if loud:
                anims.append(self.glow[n].animate.set_fill(T.highlight, 0.18))
                self.lit.add(n)
        return anims

    def point(self, name: str, role: str = "highlight") -> Mobject:
        return SurroundingRectangle(self.rows[name], buff=0.08).set_stroke(getattr(T, role), 3)


class FlagRow(VGroup):
    """The CPSR flags N, Z, C, V. ARM only; MIPS has no condition flags."""
    k = 1.0

    def __init__(self, flags: dict, size: int = 15):
        self.cells = {}
        self.size = size
        cells = VGroup()
        for f in ARM_FLAGS:
            box = RoundedRectangle(width=0.62, height=0.5, corner_radius=0.06).set_stroke(T.grid, 1.5)
            name = mono(f, size - 2, T.text_dim)
            bit = mono("0", size, T.text)
            VGroup(name, bit).arrange(DOWN, buff=0.04).move_to(box).shift(LIFT)
            cell = VGroup(box, name, bit)
            self.cells[f] = cell
            cells.add(cell)
        cells.arrange(RIGHT, buff=0.12)
        self.heading = mono("CPSR", 14, T.text_dim).next_to(cells, UP, buff=0.1, aligned_edge=LEFT)
        self.state = {f: False for f in ARM_FLAGS}
        super().__init__(cells, self.heading)
        for f in ARM_FLAGS:
            self._paint(f, bool(flags.get(f)))
            self.state[f] = bool(flags.get(f))

    def _paint(self, f, on):
        box, name, bit = self.cells[f]
        box.set_fill(T.highlight if on else T.cell_fill, 0.85 if on else 1)
        name.set_color(T.background if on else T.text_dim)
        bit.set_color(T.background if on else T.text)

    def update_to(self, flags: dict) -> list[Animation]:
        anims = []
        for f in ARM_FLAGS:
            on = bool(flags.get(f))
            if on == self.state[f]:
                continue
            self.state[f] = on
            box, name, bit = self.cells[f]
            nb = mono("1" if on else "0", self.size).scale(self.k).move_to(bit)
            nb.set_color(T.background if on else T.text)
            anims += [Transform(bit, nb), box.animate.set_fill(T.highlight if on else T.cell_fill, 0.85 if on else 1),
                      name.animate.set_color(T.background if on else T.text_dim)]
        return anims


class DelaySlot(VGroup):
    """
    MIPS's branch delay slot, shown as a small pipeline badge. It lights when
    the step being run is the instruction right after a taken branch, and names
    where the branch will land once the slot finishes.
    """
    k = 1.0

    def __init__(self, size: int = 15):
        self.box = RoundedRectangle(width=3.0, height=0.55, corner_radius=0.08).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
        self.text = mono("pipeline: running", size, T.text_dim).move_to(self.box).shift(LIFT)
        self.heading = mono("branch delay slot", 14, T.text_dim).next_to(self.box, UP, buff=0.1, aligned_edge=LEFT)
        super().__init__(self.box, self.text, self.heading)

    def update_to(self, in_slot: bool, pending) -> list[Animation]:
        if in_slot:
            msg, role, fill = f"delay slot -> {vhex(pending)}", "background", 0.85
        else:
            msg, role, fill = "pipeline: running", "text_dim", 0.0
        new = mono(msg, self.text.font_size, getattr(T, role)).scale(self.k).move_to(self.box).shift(LIFT)
        return [Transform(self.text, new), self.box.animate.set_fill(T.pointer if in_slot else T.cell_fill, fill if in_slot else 1)]


class WordColumn(VGroup):
    """Memory as whole words, high addresses on top, like everywhere in vrig."""

    def __init__(self, tr: ArchTrace, addrs: list[int], step: int = -1, size: int = 14, title: str = "stack"):
        self.tr = tr
        self.size = size
        self.slots = {}
        rows = VGroup()
        live = tr.live_words(step)
        for a in sorted(addrs, reverse=True):
            box = Rectangle(1.9, 0.36).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            val = self._val(tr.word_at(step, a), a in live).move_to(box).shift(LIFT)
            lab = mono(f"{a:08x}", size - 2, T.text_dim).next_to(box, LEFT, buff=0.15)
            slot = VGroup(box, val, lab)
            slot.box, slot.val, slot.addr = box, val, a
            self.slots[a] = slot
            rows.add(slot)
        rows.arrange(DOWN, buff=0.07, aligned_edge=RIGHT)
        self.rows = rows
        self.heading = mono(title, 14, T.text_dim).next_to(rows, UP, buff=0.15).align_to(rows[0][0], LEFT)
        self.shown = {a: (tr.word_at(step, a), a in live) for a in addrs}
        super().__init__(rows, self.heading)

    k = 1.0

    def _val(self, v, live, color=None):
        txt = vhex(v) if live else "--"
        return mono(txt, self.size, color or (T.text if live else T.text_dim)).scale(self.k)

    def write(self, a: int, v: int, role: str, opacity: float = 1.0) -> list[Animation]:
        slot = self.slots[a]
        new = self._val(v, True).move_to(slot.box).shift(LIFT).set_opacity(opacity)
        self.shown[a] = (v, True)
        return [Transform(slot.val, new), slot.box.animate.set_fill(getattr(T, role), 0.55)]

    def marker(self, name: str, side=LEFT, role: str = "highlight") -> VGroup:
        tri = Triangle().set_height(0.16).set_fill(getattr(T, role), 1).set_stroke(width=0)
        tri.rotate(-PI / 2 if side is LEFT else PI / 2)
        lab = mono(name, 14, getattr(T, role))
        g = VGroup(lab, tri).arrange(RIGHT if side is LEFT else LEFT, buff=0.06)
        g.side = "L" if side is LEFT else "R"
        return g

    def place(self, marker: VGroup, a: int) -> VGroup:
        slot = self.slots.get(a)
        if slot is not None:
            y = slot.get_y()
        else:
            top, bot = max(self.slots), min(self.slots)
            pitch = (self.slots[top].get_y() - self.slots[bot].get_y()) / max(1, len(self.slots) - 1)
            y = self.slots[top].get_y() + pitch if a > top else self.slots[bot].get_y() - pitch
        if marker.side == "L":
            x = self.rows.get_left()[0] - 0.1
            marker.move_to([x, y, 0], aligned_edge=RIGHT)
        else:
            x = self.rows.get_right()[0] + 0.1
            marker.move_to([x, y, 0], aligned_edge=LEFT)
        return marker


def wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width))


class QuizCard(VGroup):
    """
    One asmQuiz question, verbatim. The answer area shows the textbook answer
    and, when it differs, what VRIG's emulator actually computed.
    """

    def __init__(self, n: int, q: dict, width: float = 5.4):
        self.q = q
        tag = mono(f"Q{n}", 20, T.highlight)
        body = prose(wrap(q["question"], int((width - 1.1) / 0.1)), 20, T.text)
        head = VGroup(tag, body).arrange(RIGHT, buff=0.25, aligned_edge=UP)
        self.head = head
        self.frame = RoundedRectangle(width=width, height=head.get_height() + 1.9, corner_radius=0.12)
        self.frame.set_stroke(T.highlight, 2).set_fill(T.background, 0.96)
        head.move_to(self.frame, UP).shift(DOWN * 0.25)
        head.align_to(self.frame, LEFT).shift(RIGHT * 0.25)
        super().__init__(self.frame, head)

    def _ans_text(self) -> str:
        a = self.q["answer"]
        return str(a) if self.q["format"] == "decimal" else vhex(a, 8 if a > 0xff else 2)

    def reveal(self) -> tuple[VGroup, list[Animation]]:
        q = self.q
        accepted = q["accepted"]
        textbook = mono(f"answer  {self._ans_text()}", 22, T.win if accepted else T.text)
        rows = VGroup(textbook)
        if accepted:
            tick = mono("matches VRIG", 16, T.win)
            rows.add(tick)
        else:
            if q["emulator"] is None:
                shown = f"VRIG never ran that line"
            else:
                ev = q["emulator"]
                shown = f"VRIG emulator  {vhex(ev, 8 if ev > 0xff else 2)}"
            rows.add(mono(shown, 18, T.crash))
            rows.add(mono("emulator disagrees", 14, T.crash))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        rows.next_to(self.head, DOWN, buff=0.3).align_to(self.head, LEFT)
        bottom = rows.get_bottom()[1] - 0.25
        if bottom < self.frame.get_bottom()[1]:
            self.frame.stretch_to_fit_height(self.frame.get_top()[1] - bottom, about_edge=UP)
        return rows, [FadeIn(rows, shift=UP * 0.15)]
