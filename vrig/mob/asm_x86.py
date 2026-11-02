"""
Pieces for the asm-quiz exercises (unit0-asm, unit7-x64). Everything reads an
AsmTrace, which is VRIG's X86Emulator stepped one instruction at a time by
tools/vrig-trace/asm_x86-entry.ts.

cpu.py's RegisterFile is 32-bit only and has no notion of "this row just
changed", so the register file here is its own thing. Same look.
"""
from __future__ import annotations

import json
import re

from manimlib import *

from vrig.mob.memory import LIFT, mono, prose
from vrig.theme import T
from vrig.trace import TRACE_DIR

X86_GP = ["eax", "ebx", "ecx", "edx", "esi", "edi"]
X86_PTR = ["esp", "ebp", "eip"]
X64_GP = ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]
X64_PTR = ["rsp", "rbp", "rip"]
# the x64 exercises write edi/esi/... and VRIG keeps those as their own
# registers, separate from rdi/rsi. Show them next to their big sibling.
ALIAS32 = {"rax": "eax", "rbx": "ebx", "rcx": "ecx", "rdx": "edx", "rsi": "esi", "rdi": "edi"}
FLAGS = ["ZF", "SF", "CF", "OF"]
REG_RE = re.compile(r"\b(" + "|".join(X64_GP + X64_PTR + X86_GP + X86_PTR) + r")\b")


class AsmTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.arch = raw["arch"]
        self.word = raw["word"]
        self.hexw = raw["hexW"]
        self.ins = raw["instructions"]
        self.steps = raw["steps"]
        self.quiz = raw["quiz"]
        self.x64 = self.arch != "x86"
        self.sp, self.bp, self.ip = ("rsp", "rbp", "rip") if self.x64 else ("esp", "ebp", "eip")
        self.by_addr = {i["addr"]: n for n, i in enumerate(self.ins)}

    @classmethod
    def load(cls, name: str) -> "AsmTrace":
        return cls(json.loads((TRACE_DIR / f"{name}.json").read_text()))

    def state(self, i: int) -> dict:
        """State after step i. -1 is before anything ran."""
        return self.raw["initial"] if i < 0 else self.steps[i]

    def regs(self, i: int) -> dict:
        return self.state(i)["regs"]

    def width(self, reg: str) -> int:
        # hex digits AsmViz would print. 32-bit names stay 8 wide on x64
        return 8 if not self.x64 or reg in ALIAS32.values() else 16

    def shown_regs(self, all_regs: bool = False) -> list[str]:
        if not self.x64:
            return X86_GP + X86_PTR
        used = set(self.raw["initialRegs"])
        for ins in self.ins:
            used |= set(REG_RE.findall(ins["operands"]))
        for i in range(len(self.steps)):
            before, after = self.regs(i - 1), self.regs(i)
            used |= {r for r in after if after[r] != before.get(r, 0)}
        out = []
        for r in X64_GP:
            if all_regs or r in used:
                out.append(r)
            if ALIAS32.get(r) in used:
                out.append(ALIAS32[r])
        return out + X64_PTR

    def stack_range(self) -> tuple[int, int]:
        sps = [self.regs(i)[self.sp] for i in range(-1, len(self.steps))]
        return min(sps), max(max(sps), self.raw["stackBase"])

    def stack_words(self) -> list[int]:
        lo, hi = self.stack_range()
        return [a for a in self.raw["watch"] if lo - 4 * self.word <= a <= hi + 8 * self.word]

    def data_words(self) -> list[int]:
        st = set(self.stack_words())
        return [a for a in self.raw["watch"] if a not in st]

    def touches_stack(self) -> bool:
        lo, hi = self.stack_range()
        if lo != hi:
            return True
        return any(m["addr"] in self.stack_words() for s in self.steps for m in s.get("reads", []) + s.get("writes", []))

    def written(self, i: int) -> set[int]:
        return {a for a, _ in self.state(i)["bytes"]}

    def word_at(self, i: int, addr: int) -> int:
        return self.state(i)["words"][str(addr)]

    def next_ip(self, i: int) -> int:
        return self.regs(i)[self.ip]

    def fallthrough(self, i: int) -> bool:
        s = self.steps[i]
        n = self.by_addr.get(s["addr"])
        return n is not None and n + 1 < len(self.ins) and self.next_ip(i) == self.ins[n + 1]["addr"]


def vhex(v: int, w: int) -> str:
    """AsmViz's hex(): low 32 bits, padded to the arch width."""
    return f"0x{int(v) & 0xFFFFFFFF:0{w}x}"


def labels_from_source(tr: AsmTrace) -> dict[int, str]:
    """
    Put the source's labels (loop:, add_nums:, gadget1:) on the instruction
    they name. The source lines don't map one to one onto asmInstructions
    (asm-10 writes "push ebp / mov ebp, esp" as one line), so match on the
    first instruction of the line after each label, falling back to VRIG's
    per-instruction comment, which for the ret2csu gadgets starts with the name.
    """
    src = tr.raw["source"]
    out, cursor = {}, 0
    for k, line in enumerate(src):
        t = line["text"].strip()
        if line["cls"] != "label" or not t.endswith(":") or t.startswith(";"):
            continue
        name = t[:-1]
        nxt = next((l["text"] for l in src[k + 1:] if l["cls"] == "asm"), "")
        head = re.split(r";|/", nxt)[0].strip()
        head = re.sub(r"\s+", " ", head)
        hit = None
        for n in range(cursor, len(tr.ins)):
            if tr.ins[n]["text"] == head:
                hit = n
                break
        if hit is None:
            for n in range(cursor, len(tr.ins)):
                if (tr.ins[n].get("comment") or "").lower().startswith(name.lower()):
                    hit = n
                    break
        if hit is None and head:
            mn = head.split()[0]
            hit = next((n for n in range(cursor, len(tr.ins)) if tr.ins[n]["mnemonic"] == mn), None)
        if hit is not None:
            # the source often skips the prologue (x64-30's main: sits on mov edx),
            # so snap back to a call target or the entry point just before it
            for t in sorted(starts(tr), reverse=True):
                if cursor <= t <= hit and hit - t <= 2:
                    hit = t
                    break
            out[hit] = name
            cursor = hit + 1
    return out


def starts(tr: AsmTrace) -> set[int]:
    """Instruction indices something jumps or calls to, plus the entry point."""
    out = {0}
    for ins in tr.ins:
        if ins["mnemonic"] == "call" or ins["mnemonic"].startswith("j"):
            m = re.fullmatch(r"0x([0-9a-fA-F]+)", ins["operands"].strip())
            if m and int(m[1], 16) in tr.by_addr:
                out.add(tr.by_addr[int(m[1], 16)])
    return out


class AsmListing(VGroup):
    """The instruction stream VRIG steps, with addresses and the source's labels."""

    def __init__(self, tr: AsmTrace, size: int = 15):
        self.tr = tr
        labels = labels_from_source(tr)
        aw = 8 if not tr.x64 else max(6, len(f"{max(i['addr'] for i in tr.ins):x}"))
        self.rows = {}
        lines = VGroup()
        for n, ins in enumerate(tr.ins):
            if n in labels:
                lab = mono(labels[n] + ":", size, T.highlight)
                lab.is_label = True
                lines.add(lab)
            addr = mono(f"{ins['addr']:0{aw}x}", size - 2, T.text_dim)
            body = mono(ins["text"], size, T.label)
            row = VGroup(addr, body).arrange(RIGHT, buff=0.3, aligned_edge=DOWN)
            self.rows[n] = row
            lines.add(row)
        lines.arrange(DOWN, aligned_edge=LEFT, buff=0.13)
        for m in lines:
            if not getattr(m, "is_label", False):
                m.shift(RIGHT * 0.25)
        self.lines = lines
        self.bar = self._bar_for(self.rows[0]).set_opacity(0)
        super().__init__(self.bar, lines)

    def _bar_for(self, row) -> Mobject:
        bar = Rectangle(self.lines.get_width() + 0.3, row.get_height() + 0.12)
        bar.set_stroke(width=0).set_fill(T.highlight, 0.16)
        bar.move_to(row).align_to(self.lines, LEFT).shift(LEFT * 0.15 - LIFT)
        return bar

    def focus(self, n: int, role: str = "highlight") -> Animation:
        target = self._bar_for(self.rows[n]).set_fill(getattr(T, role), 0.16 if role == "highlight" else 0.3)
        return Transform(self.bar, target)

    def body(self, n: int) -> Text:
        return self.rows[n][1]

    def jump_arrow(self, a: int, b: int, role: str = "highlight") -> Mobject:
        """Arc on the left edge from row a to row b, for taken jumps, call, and ret."""
        x = self.lines.get_left()[0] - 0.12
        p, q = self.rows[a].get_left(), self.rows[b].get_left()
        p, q = np.array([x, p[1], 0]), np.array([x, q[1], 0])
        bend = min(1.2, 0.25 + 0.12 * abs(p[1] - q[1]) / 0.3)
        arc = ArcBetweenPoints(p, q, angle=PI * 0.8 if q[1] < p[1] else -PI * 0.8)
        arc.set_stroke(getattr(T, role), 3)
        tip = Triangle().set_height(0.12).set_fill(getattr(T, role), 1).set_stroke(width=0)
        tip.rotate(-PI / 2).move_to(q + LEFT * 0.04)
        return VGroup(arc, tip)


class RegFile(VGroup):
    """
    Register rows. A row that changed on this step lights up (value in the
    highlight color, faint bar behind it) until the next step calms it down.
    """

    def __init__(self, tr: AsmTrace, names: list[str], values: dict, size: int = 16, title: str | None = None):
        self.tr = tr
        self.size = size
        self.names = names
        self.rows, self.glow = {}, {}
        self.values = {n: values.get(n, 0) for n in names}
        rows = VGroup()
        name_w = max(len(n) for n in names)
        for n in names:
            name = mono(n.ljust(name_w), size, T.label)
            val = self._val(n, self.values[n])
            row = VGroup(name, val).arrange(RIGHT, buff=0.3)
            self.rows[n] = row
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        # values right-aligned so 8-wide aliases line up under the 16-wide regs
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
        self.heading = None
        if title:
            self.heading = mono(title, 14, T.text_dim).next_to(self.bg, UP, buff=0.1, aligned_edge=LEFT)
            parts.append(self.heading)
        self.lit = set()
        super().__init__(*parts)

    k = 1.0  # set by the scene after it scales the board

    def _val(self, name: str, v: int, color=None) -> Text:
        return mono(vhex(v, self.tr.width(name)), self.size, color or T.text).scale(self.k)

    def update_to(self, values: dict, quiet=()) -> list[Animation]:
        """Animations from the shown values to `values`. Names in `quiet` change without lighting up."""
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
            new = self._val(n, v, T.highlight if loud else T.text).move_to(old, aligned_edge=RIGHT)
            anims = [a for a in anims if getattr(a, "mobject", None) is not old]
            anims.append(Transform(old, new))
            if loud:
                anims.append(self.glow[n].animate.set_fill(T.highlight, 0.18))
                self.lit.add(n)
        return anims

    def point(self, name: str, role: str = "highlight") -> Mobject:
        return SurroundingRectangle(self.rows[name], buff=0.08).set_stroke(getattr(T, role), 3)


class FlagRow(VGroup):
    k = 1.0

    def __init__(self, flags: dict, size: int = 15):
        self.cells = {}
        self.size = size
        cells = VGroup()
        for f in FLAGS:
            box = RoundedRectangle(width=0.62, height=0.5, corner_radius=0.06).set_stroke(T.grid, 1.5)
            name = mono(f, size - 2, T.text_dim)
            bit = mono("0", size, T.text)
            VGroup(name, bit).arrange(DOWN, buff=0.04).move_to(box).shift(LIFT)
            cell = VGroup(box, name, bit)
            self.cells[f] = cell
            cells.add(cell)
        cells.arrange(RIGHT, buff=0.12)
        self.state = {f: False for f in FLAGS}
        super().__init__(cells)
        for f in FLAGS:
            self._paint(f, bool(flags.get(f)))
            self.state[f] = bool(flags.get(f))

    def _paint(self, f, on):
        box, name, bit = self.cells[f]
        box.set_fill(T.highlight if on else T.cell_fill, 0.85 if on else 1)
        name.set_color(T.background if on else T.text_dim)
        bit.set_color(T.background if on else T.text)

    def update_to(self, flags: dict) -> list[Animation]:
        anims = []
        for f in FLAGS:
            on = bool(flags.get(f))
            if on == self.state[f]:
                continue
            self.state[f] = on
            box, name, bit = self.cells[f]
            nb = mono("1" if on else "0", self.size).scale(self.k).move_to(bit)
            nb.set_color(T.background if on else T.text)
            # no Indicate on the box: it fights box.animate and the fill never lands
            anims += [Transform(bit, nb), box.animate.set_fill(T.highlight if on else T.cell_fill, 0.85 if on else 1),
                      name.animate.set_color(T.background if on else T.text_dim)]
        return anims


class WordColumn(VGroup):
    """
    Memory as whole words, high addresses on top like everywhere else in
    vrig. Values are VRIG's readMem() of each word, so on x64 they show what
    the emulator really holds, top half and all.
    """

    def __init__(self, tr: AsmTrace, addrs: list[int], step: int = -1, size: int = 14, title: str = "stack"):
        self.tr = tr
        self.size = size
        self.slots = {}
        rows = VGroup()
        written = tr.written(step)
        for a in sorted(addrs, reverse=True):
            box = Rectangle(1.75 if tr.word == 4 else 2.0, 0.36).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            v = tr.word_at(step, a)
            val = self._val(v, a in written).move_to(box).shift(LIFT)
            lab = mono(f"{a:08x}", size - 2, T.text_dim).next_to(box, LEFT, buff=0.15)
            slot = VGroup(box, val, lab)
            slot.box, slot.val, slot.addr = box, val, a
            self.slots[a] = slot
            rows.add(slot)
        rows.arrange(DOWN, buff=0.06, aligned_edge=RIGHT)
        self.rows = rows
        self.heading = mono(title, 14, T.text_dim).next_to(rows, UP, buff=0.15).align_to(rows[0][0], LEFT)
        self.shown = {a: (tr.word_at(step, a), a in written) for a in addrs}
        super().__init__(rows, self.heading)

    k = 1.0

    def _val(self, v, written, color=None):
        txt = vhex(v, self.tr.hexw) if written else "--"
        return mono(txt, self.size, color or (T.text if written else T.text_dim)).scale(self.k)

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
        # a string, not the LEFT array: copy() deep-copies arrays and `is` stops matching
        g.side = "L" if side is LEFT else "R"
        return g

    def covers(self, a: int) -> bool:
        return min(self.slots) - self.tr.word <= a <= max(self.slots) + self.tr.word

    def place(self, marker: VGroup, a: int) -> VGroup:
        """Move `marker` next to word a, or just past the edge if a isn't shown."""
        slot = self.slots.get(a)
        if slot is not None:
            y = slot.get_y()
        else:
            top, bot = max(self.slots), min(self.slots)
            pitch = self.slots[top].get_y() - self.slots[bot].get_y()
            pitch = pitch / max(1, len(self.slots) - 1) if len(self.slots) > 1 else self.slots[top].get_height()
            # just past the edge, for sp sitting on a word we don't draw
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
    """One asmQuiz question, verbatim, with room under it for the answer."""

    def __init__(self, n: int, q: dict, width: float = 5.4):
        self.q = q
        tag = mono(f"Q{n}", 20, T.highlight)
        body = prose(wrap(q["question"], int((width - 1.1) / 0.1)), 21, T.text)
        head = VGroup(tag, body).arrange(RIGHT, buff=0.25, aligned_edge=UP)
        self.head = head
        self.frame = RoundedRectangle(width=width, height=head.get_height() + 1.5, corner_radius=0.12)
        self.frame.set_stroke(T.highlight, 2).set_fill(T.background, 0.96)
        head.move_to(self.frame, UP).shift(DOWN * 0.25)
        head.align_to(self.frame, LEFT).shift(RIGHT * 0.25)
        super().__init__(self.frame, head)

    def answer_text(self) -> str:
        q = self.q
        a = q["answer"]
        s = str(a) if q["format"] == "decimal" else f"0x{a:x}"
        # multiple-choice questions spell their choices out in the question or hint
        choice = choices(q).get(a)
        return f"{s} = {choice}" if choice else s

    def reveal(self, evidence: str) -> tuple[VGroup, list[Animation]]:
        ans = mono(self.answer_text(), 26, T.win)
        tick = mono("✓", 26, T.win)
        line = VGroup(ans, tick).arrange(RIGHT, buff=0.25)
        ev = mono(evidence, 16, T.label)
        if ev.get_width() > self.frame.get_width() - 0.5:
            ev.set_width(self.frame.get_width() - 0.5)
        g = VGroup(line, ev).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        g.next_to(self.head, DOWN, buff=0.3).align_to(self.head, LEFT)
        bottom = g.get_bottom()[1] - 0.25
        if bottom < self.frame.get_bottom()[1]:
            self.frame.stretch_to_fit_height(self.frame.get_top()[1] - bottom, about_edge=UP)
        return g, [FadeIn(line, shift=UP * 0.15), FadeIn(ev)]


def choices(q: dict) -> dict[int, str]:
    for text in (q["question"], q.get("hint") or ""):
        found = re.findall(r"(\d+)=(.+?)(?=,\s*\d+=|[.)]\s|[.)]$|$)", text)
        if len(found) >= 2:
            return {int(k): v.strip() for k, v in found}
    return {}
