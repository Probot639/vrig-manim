"""
The stack family: imagine-rit, unit1-stack, unit2-logic, and the three new
unit3-stack-ii lessons. Every address, byte, register value, and win/crash on
screen is replayed from a trace that tools/vrig-trace/stack-entry.ts produced
by running VRIG's own engine. Nothing here is a number typed by hand.

    manimgl scenes/stack.py Rit03 -w -l            # quick look
    manimgl scenes/stack.py Rit03 -w --hd          # mp4

The 3D ROP half (RitRop, Stack2_13) borrows CodeBlock and the chain style from
scenes/unit3_stack_ii.py (RopBasics), which is the quality bar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from manimlib import *

sys.path.insert(0, str(Path(__file__).parent))
from unit3_stack_ii import CodeBlock  # noqa: E402

from vrig.mob.cpu import CodeListing, RegisterFile  # noqa: E402
from vrig.mob.memory import (  # noqa: E402
    CELL, GAP, LIFT, ByteCell, PayloadStrip, StackView, Word, le_assemble, mono, prose, tex,
)
from vrig.mob.space import arc3d, billboard  # noqa: E402
from vrig.scene import Vrig3DScene, VrigScene  # noqa: E402
from vrig.theme import T  # noqa: E402
from vrig.trace import TRACE_DIR, StackTrace, h32  # noqa: E402


def target_box(name: str, addr: int | None, role: str, width: float = 3.2) -> VGroup:
    """A named code/data destination with its address underneath."""
    box = RoundedRectangle(width=width, height=1.0, corner_radius=0.12)
    box.set_stroke(getattr(T, role), 3).set_fill(T.cell_fill, 1)
    label = mono(name, 22, T.text)
    parts = [label]
    if addr is not None:
        parts.append(mono(h32(addr), 16, T.text_dim))
    VGroup(*parts).arrange(DOWN, buff=0.08).move_to(box)
    return VGroup(box, *parts)


def ascii_glyph(b: int) -> str:
    return chr(b) if 0x20 <= b <= 0x7e else f"{b:02x}"


class TextStrip(VGroup):
    """Input shown as the letters a person types, not hex."""

    def __init__(self, data: list[int], per_row: int = 24):
        self.cells = VGroup(*(ByteCell(b, "attacker_bytes", glyph=ascii_glyph(b)) for b in data))
        rows = VGroup()
        for r in range(0, len(data), per_row):
            row = VGroup(*self.cells[r:r + per_row]).arrange(RIGHT, buff=0.03)
            rows.add(row)
        rows.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        rows.set_width(min(rows.get_width(), 6.4))
        super().__init__(rows)


class FlatStack(VrigScene):
    """Shared build for the 2D overwrite lessons."""

    trace_name: str = ""
    text_mode = False
    vuln_hint = "gets"

    def setup_trace(self):
        self.tr = StackTrace.load(self.trace_name)
        return self.tr

    def open_title(self, subtitle: str | None = None):
        title = prose(self.tr.title, 46).to_edge(UP, buff=0.4)
        anims = [Write(title)]
        sub = None
        if subtitle:
            sub = prose(subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.2)
            anims.append(FadeIn(sub, shift=UP * 0.2))
        self.play(*anims)
        self.beat()
        out = [title.animate.scale(0.55).to_corner(UL, buff=0.25)]
        if sub:
            out.append(FadeOut(sub))
        self.play(*out)
        self.title = title

    def build_code_stack(self, n_words: int | None = None):
        tr = self.tr
        src = [l for l in tr.source if not l.startswith("#include")]
        code = CodeListing(src, size=16).to_corner(UL, buff=0.5).shift(DOWN * 0.5)
        n_words = n_words if n_words is not None else len(tr.payload) // tr.word
        stack = StackView(tr, n_words=n_words).shift(RIGHT * 2.0 + UP * 0.1)
        # a tall buffer would run off the frame, so shrink the whole stack to fit
        if stack.get_height() > 6.6:
            stack.set_height(6.6)
        stack.shift(RIGHT * 2.0 + UP * 0.1 - stack.get_center() * np.array([0, 1, 0]))
        self.code, self.stack = code, stack

        tags = stack.frame_tags()
        if tr.canary_size:
            tags.add(stack.region_tag(tr.buf_size, "canary", "canary"))
        self.tags = tags

        vuln_line = next((i for i, l in enumerate(src) if self.vuln_hint in l), 0)
        self.play(FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.3),
                  code.focus(vuln_line))

    def make_strip(self):
        tr = self.tr
        if self.text_mode:
            strip = TextStrip(tr.payload)
        else:
            strip = PayloadStrip(tr.payload)
        strip.next_to(self.code, DOWN, buff=0.5, aligned_edge=LEFT)
        lab = mono("input", 16, T.text_dim).next_to(strip, UP, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(lab), FadeIn(strip, lag_ratio=0.02, run_time=1.0))
        self.strip, self.strip_lab = strip, lab
        return strip

    def feed(self, on_ret=None):
        """Walk VRIG's write steps, moving bytes from the strip onto the stack."""
        tr, stack, strip = self.tr, self.stack, self.strip
        for step in tr.steps:
            lbl = step["label"]
            if "write" not in lbl or not any(lbl.startswith(p) for p in ("gets", "memcpy", "read_byte")):
                continue
            hl = step["hl"]
            off, end = hl[0], hl[1]
            data = step["memory"][off:end]
            src_cells = strip.cells[off:end]
            dst_cells = VGroup(*stack.at(off).cells[:len(data)])
            self.play(
                *[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, dst_cells)],
                src_cells.animate.set_opacity(0.2),
                run_time=0.4 if off < tr.buf_size else 0.6,
            )
            over = off >= tr.buf_size
            self.play(*stack.write_word(off, data, "attacker_bytes", overflow=over), run_time=0.3)
            if on_ret and off == tr.ret_off:
                on_ret()

    def clear_input(self):
        self.play(FadeOut(self.strip), FadeOut(self.strip_lab), FadeOut(self.tags))

    def meaning(self, v: int) -> tuple[str, str]:
        tr = self.tr
        if v == tr.symbols.get("win"):
            return "win()", "win"
        if v == tr.symbols.get("system"):
            return "system()", "libc"
        if v == tr.symbols.get("binsh"):
            return '"/bin/sh"', "libc"
        if v in tr.gadgets:
            return "gadget", "gadget"
        if v == tr.raw.get("flagAddr"):
            return "&flag_check", "attacker_bytes"
        return "garbage", "crash"

    def read_ret(self, color_role="highlight"):
        tr = self.tr
        word = self.stack.at(tr.ret_off)
        value, anims = le_assemble(word, color=getattr(T, color_role))
        self.play(*anims, run_time=0.8)
        return word, value

    def jump_to(self, box, color, win=False):
        """Curved arrow from the return slot to a destination box."""
        start = self.stack.at(self.tr.ret_off).cells.get_right() + RIGHT * 0.05
        arrow = CurvedArrow(start, box.get_left() + LEFT * 0.05,
                            angle=-30 * DEG, color=color, stroke_width=5)
        self.play(ShowCreation(arrow))
        if win:
            self.play(box[0].animate.set_fill(color, 0.35), Flash(box, color=color, flash_radius=1.1))
        else:
            self.play(Flash(box, color=color, flash_radius=1.0), WiggleOutThenIn(box))
        return arrow


# --- crash: input runs off the end -----------------------------------------

class CrashOverflow(FlatStack):
    def construct(self):
        tr = self.setup_trace()
        self.open_title()
        self.build_code_stack()
        self.say("gets reads until a newline. It never checks how big buf is.")
        self.make_strip()

        def reached():
            self.say("Past buf and the saved frame, the input reaches the return address.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("crash")
        name, _ = self.meaning(tr.word_at(tr.ret_off))
        lab = mono(name, 16, T.crash).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.crash, 0.85))
        self.say("The return address is garbage now. The CPU will trust it anyway.")
        self.beat()

        dest = tr.word_at(tr.ret_off)
        box = target_box("nothing here", dest, "crash", width=3.0).move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.crash)
        self.say(self.outro)
        self.beat(pause=2)


class Rit02(CrashOverflow):
    trace_name = "rit-02"
    outro = "The program jumps into nothing and segfaults. Next you steer where it goes."


class Stack02(CrashOverflow):
    trace_name = "stack-02"
    text_mode = True

    def construct(self):
        # same shape, but the input is typed text, so narrate that once
        tr = self.setup_trace()
        self.open_title()
        self.build_code_stack()
        self.say("You type a name. Each letter is one byte on the stack.")
        self.make_strip()

        def reached():
            self.say("Sixteen letters fill buf. Four more cover the saved frame, then you hit the return address.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("crash")
        lab = mono("garbage", 16, T.crash).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.crash, 0.85))
        self.say("Those last four letters are now the return address.")
        self.beat()

        dest = tr.word_at(tr.ret_off)
        box = target_box("nothing here", dest, "crash", width=3.0).move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.crash)
        self.say("Letters became an address, and the program crashes on it. In lesson 3 you pick the address.")
        self.beat(pause=2)


# --- hijack: overwrite the return address with win() ------------------------

class HijackWin(FlatStack):
    intro_cap = "Keep the padding, then overwrite the return address with win()."

    def construct(self):
        tr = self.setup_trace()
        self.open_title()
        self.build_code_stack()
        self.say(self.intro_cap)
        self.make_strip()

        def reached():
            self.say("The last four bytes are win(), written back to front.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("win")
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        self.say("Read back little-endian, the return address is win().")
        self.beat()

        box = target_box("win()", tr.symbols["win"], "win").move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.win, win=True)
        self.say(self.outro)
        self.beat(pause=2)


class Rit03(HijackWin):
    trace_name = "rit-03"
    outro = "You made the program run a function it never meant to call. FLAG{you_own_the_program}"


class Stack03(HijackWin):
    trace_name = "stack-03"
    outro = "The return went into win() instead of back to main. FLAG{you_own_the_eip}"


# --- ASLR: one leak, then arithmetic ----------------------------------------

class AslrWin(FlatStack):
    def construct(self):
        tr = self.setup_trace()
        self.open_title("Addresses are randomized. Last lesson's number is wrong now.")
        self.build_code_stack()

        main = tr.symbols["main"]
        win = tr.symbols["win"]
        leak = VGroup(
            mono("DEBUG: main is at", 20, T.text_dim),
            mono(h32(main), 24, T.leak),
        ).arrange(RIGHT, buff=0.2)
        panel = SurroundingRectangle(leak, buff=0.22).set_stroke(T.grid, 2).set_fill(T.background, 0.92)
        term = VGroup(panel, leak).next_to(self.code, DOWN, buff=0.5, aligned_edge=LEFT)
        self.play(FadeIn(term, shift=UP * 0.1))
        self.say("The program leaks one address. main() is right there.")
        self.beat()

        math = VGroup(
            tex(rf"\text{{win}} = \text{{main}} + \text{{0x150}}", 34),
            tex(rf"= {h32(main)} + \text{{0x150}}", 32, T.text_dim),
            tex(rf"= {h32(win)}", 34, T.win),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18).next_to(term, DOWN, buff=0.35, aligned_edge=LEFT)
        self.play(Write(math[0]))
        self.play(FadeIn(math[1], shift=UP * 0.1))
        self.play(TransformFromCopy(math[1], math[2]))
        self.say("win() sits a fixed 0x150 above main, so the leak gives it away.")
        self.beat()
        self.play(FadeOut(term), FadeOut(math))

        self.say("Build the same overwrite, this time with the computed address.")
        self.make_strip()

        def reached():
            self.say("Twenty bytes of padding, then the win() you just worked out.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("win")
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        self.beat()

        box = target_box("win()", win, "win").move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.win, win=True)
        self.say(self.outro)
        self.beat(pause=2)


class Rit04(AslrWin):
    trace_name = "rit-04"
    outro = "Randomized addresses fell to one leak and some addition. FLAG{aslr_defeated}"


class Stack04(AslrWin):
    trace_name = "stack-04"
    outro = "One leaked address, a little math, and ASLR is beaten. FLAG{aslr_defeated}"


# --- canary: step over the tripwire -----------------------------------------

class Stack05(FlatStack):
    trace_name = "stack-05"

    def construct(self):
        tr = self.setup_trace()
        self.open_title("A canary now sits between buf and the saved frame.")
        self.build_code_stack()

        canary = tr.raw["canaryValue"]
        leak = VGroup(
            mono("printf(buf) leaks the canary:", 19, T.text_dim),
            mono(h32(canary), 24, T.leak),
        ).arrange(RIGHT, buff=0.2)
        panel = SurroundingRectangle(leak, buff=0.22).set_stroke(T.grid, 2).set_fill(T.background, 0.92)
        term = VGroup(panel, leak).next_to(self.code, DOWN, buff=0.5, aligned_edge=LEFT)
        self.play(FadeIn(term, shift=UP * 0.1))
        self.say("A format string bug prints the secret value. Note the low byte is zero.")
        self.beat()
        self.play(FadeOut(term))

        self.say("Overflow as before, but drop the real canary into its slot on the way past.")
        self.make_strip()

        canary_hit = [False]

        def on_canary():
            self.say("Same bytes VRIG leaked, back in the tripwire's slot.")
            self.beat()
        # feed, and fire a note when the canary word gets written
        for step in tr.steps:
            lbl = step["label"]
            if "write" not in lbl or not lbl.startswith("gets"):
                continue
            off, end = step["hl"][0], step["hl"][1]
            data = step["memory"][off:end]
            src_cells = self.strip.cells[off:end]
            dst = VGroup(*self.stack.at(off).cells[:len(data)])
            self.play(*[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, dst)],
                      src_cells.animate.set_opacity(0.2), run_time=0.4 if off < tr.buf_size else 0.6)
            role = "canary" if off == tr.buf_size else "attacker_bytes"
            self.play(*self.stack.write_word(off, data, role, overflow=off >= tr.buf_size), run_time=0.3)
            if off == tr.buf_size and not canary_hit[0]:
                canary_hit[0] = True
                on_canary()
            if off == tr.ret_off:
                self.say("Then win() over the return address.")
                self.beat()
        self.clear_input()

        # the check
        self.say("Function returns. First the tripwire is checked.")
        canary_word = self.stack.at(tr.buf_size)
        self.play(Indicate(canary_word.cells, color=T.canary, scale_factor=1.05))
        check = mono("canary intact", 20, T.win).next_to(canary_word, LEFT, buff=0.4)
        self.play(FadeIn(check, shift=RIGHT * 0.1))
        self.beat()

        word, value = self.read_ret("win")
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        self.say("Tripwire untouched, return address owned. FLAG{canary_bypassed}")
        self.beat(pause=2)


# --- integer overflow: a size that wraps ------------------------------------

class Logic06(FlatStack):
    trace_name = "logic-06"

    def log_value(self, start: str, idx=0) -> str:
        for s in self.tr.steps:
            for l in s["logs"]:
                if l["msg"].startswith(start):
                    return l["msg"]
        return ""

    def construct(self):
        tr = self.setup_trace()
        self.open_title("A length you pick gets 64 added to it, then becomes the buffer size.")

        # the wrap, pulled from VRIG's own preamble logs
        user_log = self.log_value("scanf")
        wrap_log = next(l["msg"] for s in tr.steps for l in s["logs"] if "wraps to" in l["msg"])
        user_len = user_log.split("entered:")[-1].strip()
        total = wrap_log.split("wraps to")[-1].strip().split()[0]

        math = VGroup(
            tex(rf"\text{{len}} = {user_len}", 34),
            tex(rf"\text{{total}} = \text{{len}} + 64", 32, T.text_dim),
            tex(rf"= {total} \ \text{{(wrapped)}}", 34, T.crash),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to(UP * 0.4)
        self.play(Write(math[0]))
        self.play(FadeIn(math[1], shift=UP * 0.1))
        self.play(TransformFromCopy(math[1], math[2]))
        self.say("A huge length plus 64 overflows the counter and wraps to a tiny number.")
        self.beat()
        note = prose(f"buf is only {total} bytes, but your whole input still gets read.", 24, T.text_dim)
        note.next_to(math, DOWN, buff=0.4)
        self.play(FadeIn(note, shift=UP * 0.1))
        self.beat()
        self.play(FadeOut(math), FadeOut(note))

        self.build_code_stack()
        self.say("The tiny buffer can't hold the input, so it overflows the return address.")
        self.make_strip()

        def reached():
            self.say("The read runs long and reaches the return slot.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("win")
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        box = target_box("win()", tr.symbols["win"], "win").move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.win, win=True)
        self.say("A wrapped size turned a safe read into an overflow. FLAG{integer_wrap}")
        self.beat(pause=2)


# --- signedness: negative slips past the check ------------------------------

class Logic10(FlatStack):
    trace_name = "logic-10"
    vuln_hint = "memcpy"

    def construct(self):
        tr = self.setup_trace()
        self.open_title("The length check uses a signed compare, but memcpy wants unsigned.")

        signed = next(l["msg"].split("entered:")[-1].strip()
                      for s in tr.steps for l in s["logs"] if l["msg"].startswith("scanf"))
        cast = next(l["msg"] for s in tr.steps for l in s["logs"] if "(size_t)" in l["msg"])
        unsigned = cast.split("→")[-1].strip()

        math = VGroup(
            tex(rf"\text{{len}} = {signed}", 34),
            tex(rf"{signed} > 64 ? \ \text{{no}}", 30, T.text_dim),
            tex(rf"\text{{(size\_t)}}\ {signed} = {unsigned}", 32, T.crash),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to(UP * 0.4)
        self.play(Write(math[0]))
        self.play(FadeIn(math[1], shift=UP * 0.1))
        self.say("A negative length is always less than 64, so the check waves it through.")
        self.beat()
        self.play(TransformFromCopy(math[1], math[2]))
        self.say("Cast to unsigned for memcpy, that same value is enormous.")
        self.beat()
        self.play(FadeOut(math))

        self.build_code_stack()
        self.say("memcpy copies far past buf and into the return address.")
        self.make_strip()

        def reached():
            self.say("The copy keeps going until it overwrites the return slot.")
            self.beat()
        self.feed(on_ret=reached)
        self.clear_input()

        word, value = self.read_ret("win")
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        box = target_box("win()", tr.symbols["win"], "win").move_to(RIGHT * 3.2 + UP * 2.4)
        self.play(FadeIn(box))
        self.jump_to(box, T.win, win=True)
        self.say("One negative number became a giant copy. FLAG{signed_vs_unsigned}")
        self.beat(pause=2)


# --- off-by-one: one byte shifts the frame ----------------------------------

class Logic09(FlatStack):
    trace_name = "logic-09"
    vuln_hint = "i <="

    def construct(self):
        tr = self.setup_trace()
        self.open_title("The loop runs one step too far and writes one byte past buf.")
        self.build_code_stack(n_words=tr.total // tr.word)
        self.say("buf holds 16 bytes. The loop writes 17.")
        self.make_strip()

        for step in tr.steps:
            lbl = step["label"]
            if "write" not in lbl or not lbl.startswith("read_byte"):
                continue
            off, end = step["hl"][0], step["hl"][1]
            data = step["memory"][off:end]
            src_cells = self.strip.cells[off:end]
            dst = VGroup(*self.stack.at(off).cells[:len(data)])
            self.play(*[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, dst)],
                      src_cells.animate.set_opacity(0.2), run_time=0.4 if off < tr.buf_size else 0.7)
            over = off >= tr.buf_size
            role = "saved_fp" if off == tr.buf_size else "attacker_bytes"
            self.play(*self.stack.write_word(off, data, role, overflow=over), run_time=0.3)
            if off == tr.buf_size:
                self.say("The 17th byte lands on the low byte of the saved frame pointer.")
                self.beat()
        self.clear_input()

        # VRIG reads main's return from a shifted location
        obo = next(s for s in tr.steps if s["label"].startswith("main() returns"))
        shift_log = next(l["msg"] for l in obo["logs"] if "shifted location" in l["msg"])
        self.say("When main returns, the bent frame pointer shifts where it reads the return address.")
        self.beat()
        read_at = shift_log.split("(buf+")[-1].split(")")[0]
        src_word = self.stack.at(int(read_at))
        value, anims = le_assemble(src_word, color=T.win)
        self.play(Indicate(src_word.cells, color=T.highlight, scale_factor=1.05))
        self.play(*anims, run_time=0.8)
        lab = mono("win()", 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), src_word.boxes().animate.set_fill(T.win, 0.85))
        self.say(f"It now reads from buf+{read_at}, where you left win(). FLAG{{off_by_one}}")
        self.beat(pause=2)


# --- ROP: the stack becomes the program ------------------------------------

class RopScene(Vrig3DScene):
    """Flat overflow, then tilt into 3D and walk the gadget chain.

    Modeled on RopBasics in scenes/unit3_stack_ii.py. Handles a single combined
    gadget (rit-rop) and a stack pivot (stack2-13) off the same trace fields.
    """

    trace_name = ""
    subtitle = "NX is on, so nothing on the stack can run."

    def construct(self):
        tr = StackTrace.load(self.trace_name)
        assert tr.won(), "trace payload doesn't win, re-export it"
        self.tr = tr
        self.frame.reorient(0, 0)
        self.act_overflow()
        self.act_chain()

    def meaning(self, v: int) -> tuple[str, str]:
        tr = self.tr
        if v in tr.gadgets:
            return "gadget", "gadget"
        if v == tr.symbols.get("win"):
            return "win()", "win"
        if v == tr.raw.get("flagAddr"):
            return "&flag_check", "attacker_bytes"
        if v == tr.magic:
            return "magic", "attacker_bytes"
        if tr.base <= v < tr.base + tr.total:
            return "&chain", "pointer"
        return "data", "attacker_bytes"

    def blk_title(self, addr: int) -> str:
        if addr == self.tr.symbols.get("win"):
            return "win()"
        g = self.tr.gadgets.get(addr, "")
        return g if len(g) <= 18 else "write gadget"

    def esp_marker(self) -> VGroup:
        tri = Triangle().rotate(-90 * DEG).set_height(CELL * 0.5)
        tri.set_fill(T.highlight, 1).set_stroke(width=0)
        lab = mono("esp", 18, T.highlight).next_to(tri, LEFT, buff=0.1)
        return VGroup(lab, tri)

    def act_overflow(self):
        tr = self.tr
        title = prose(tr.title, 46).to_edge(UP, buff=0.4)
        sub = prose(self.subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()

        src = [l for l in tr.source if not l.startswith("#include")]
        code = CodeListing(src, size=15).to_corner(UL, buff=0.5).shift(DOWN * 0.4)
        stack = StackView(tr, n_words=len(tr.payload) // tr.word).shift(RIGHT * 2.1 + UP * 0.1)
        if stack.get_height() > 6.6:
            stack.set_height(6.6)
            stack.to_edge(RIGHT, buff=1.4).shift(UP * 0.1)
        tags = stack.frame_tags()

        self.play(FadeOut(sub), title.animate.scale(0.55).to_corner(UL, buff=0.25),
                  FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.3))
        self.stack, self.title, self.code = stack, title, code
        self.beat()

        gets_line = next((i for i, l in enumerate(src) if "gets(" in l), 0)
        self.play(code.focus(gets_line))
        self.say("gets copies until a newline, so your whole chain lands on the stack.")

        strip = PayloadStrip(tr.payload).next_to(code, DOWN, buff=0.4, aligned_edge=LEFT)
        strip_lab = mono("input", 16, T.text_dim).next_to(strip, UP, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(strip_lab), FadeIn(strip, lag_ratio=0.02, run_time=1.0))
        self.beat()

        w = tr.word
        for step in tr.steps:
            if not step["label"].startswith("gets(): write"):
                continue
            off = step["hl"][0]
            data = step["memory"][off:off + w]
            src_cells = strip.cells[off:off + w]
            self.play(*[TransformFromCopy(sc, c, path_arc=-20 * DEG)
                        for sc, c in zip(src_cells, stack.at(off).cells)],
                      src_cells.animate.set_opacity(0.2), run_time=0.35 if off < tr.buf_size else 0.5)
            self.play(*stack.write_word(off, data, "attacker_bytes", overflow=off >= tr.buf_size), run_time=0.25)
            if off == tr.ret_off:
                self.say("Past buf and the saved frame, the first return address is in place.")
                self.beat()

        self.play(FadeOut(strip), FadeOut(strip_lab), FadeOut(tags))
        self.say("Read each word above the buffer the way ret will.")
        self.beat()

        meanings = VGroup()
        for off in range(tr.ret_off, len(tr.payload), w):
            name, role = self.meaning(tr.word_at(off))
            word = stack.at(off)
            value, anims = le_assemble(word)
            self.play(*anims, run_time=0.5)
            m = mono(name, 15, getattr(T, role)).next_to(value, RIGHT, buff=0.2)
            self.play(FadeIn(m, shift=LEFT * 0.12), word.boxes().animate.set_fill(getattr(T, role), 0.85), run_time=0.35)
            meanings.add(VGroup(value, m))
        self.say(self.chain_caption)
        self.meanings = meanings
        self.beat()

    def act_chain(self):
        tr, stack, frame = self.tr, self.stack, self.frame
        self.play(FadeOut(self.code), FadeOut(self.meanings), FadeOut(self.title))
        self.unsay()

        stack.tags.set_opacity(0)
        self.play(stack.animate.shift(LEFT * 3.5))
        self.play(stack.tags.animate.set_opacity(1), run_time=0.5)
        self.play(frame.animate.reorient(-24, 50, 0, center=(0.9, 0.0, 0.6), height=9.2), run_time=2.5)

        order = sorted(set(tr.gadgets) | {tr.symbols["win"]})
        blocks = {}
        text_group = Group()
        for addr in order:
            name, role = (self.blk_title(addr), "win" if addr == tr.symbols["win"] else "gadget")
            blocks[addr] = CodeBlock(name, addr, role, frame)
            text_group.add(blocks[addr])
        text_group.arrange(UP, buff=0.45).move_to(RIGHT * 3.9 + DOWN * 0.7)
        text_lab = billboard(mono(".text  r-x", 20, T.text_dim).next_to(text_group, DOWN, buff=0.3), frame)

        flag = CodeBlock("flag_check = 0", tr.flag_addr, "cell_fill", frame, width=2.6)
        flag.move_to(RIGHT * 3.9 + UP * 3.5)
        data_lab = billboard(mono(".data  rw-", 20, T.text_dim).next_to(flag.slab, LEFT, buff=0.3), frame)
        nx = billboard(mono("stack  rw-  NX", 20, T.mitigation).next_to(stack.words, UP, buff=0.35), frame)

        self.play(LaggedStart(*(FadeIn(b, shift=OUT * 0.5) for b in text_group), lag_ratio=0.2),
                  FadeIn(text_lab), FadeIn(flag, shift=OUT * 0.5), FadeIn(data_lab), FadeIn(nx))

        regs = RegisterFile().to_corner(UR, buff=0.35).fix_in_frame()
        self.play(FadeIn(regs))
        self.say("The stack is the program now. esp is its program counter.")
        self.beat()

        w = tr.word
        esp_arrow = self.esp_marker()
        esp_arrow.next_to(stack.at(tr.ret_off), LEFT, buff=0.12)

        def esp_to(off):
            return esp_arrow.animate.next_to(stack.at(off), LEFT, buff=0.12)

        self.play(FadeIn(esp_arrow), *regs.set("esp", tr.addr(tr.ret_off), role="label"))
        self.beat()

        trail = VGroup()
        src_off = tr.ret_off
        esp = tr.ret_off + w
        eip = tr.word_at(tr.ret_off)
        eax = 0

        for ev in tr.rop_events():
            assert ev.addr == eip, f"trace disagrees with stack: {h32(ev.addr)} vs {h32(eip)}"
            blk = blocks[ev.addr]
            jump = arc3d(stack.at(src_off).cells.get_right(), blk.top())
            self.play(ShowCreation(jump), stack.at(src_off).cells.animate.set_opacity(0.35), esp_to(esp),
                      *regs.set("eip", ev.addr), *regs.set("esp", tr.addr(esp), role="label"), run_time=1.0)
            trail.add(jump)
            self.play(blk.slab.animate.set_color(T.highlight), run_time=0.3)
            self.say(f"ret lands on  {ev.text}", run_time=0.4)

            for reg, val in ev.pops:
                slot = stack.at(esp)
                self.play(Indicate(slot.cells, color=T.highlight, scale_factor=1.05), *regs.set(reg, val))
                slot.cells.set_opacity(0.35)
                if reg == "eax":
                    eax = val
                esp += w
                self.play(esp_to(esp), *regs.set("esp", tr.addr(esp), role="label"), run_time=0.4)

            if "xchg eax, esp" in ev.text:
                new_off = eax - tr.base
                self.say("xchg eax, esp drops esp onto the staged chain.")
                self.play(Indicate(stack.at(new_off).cells, color=T.pointer),
                          esp_arrow.animate.next_to(stack.at(new_off), LEFT, buff=0.12),
                          *regs.set("esp", eax, role="highlight"), run_time=0.9)
                esp = new_off

            if ev.write:
                val, addr = ev.write
                assert addr == tr.flag_addr
                hop = arc3d(blk.top(), flag.top(), lift=1.2, color=T.attacker_bytes)
                newlab = mono(f"flag_check = {val:#x}", 22, T.text).move_to(flag.title)
                billboard(newlab, frame)
                self.play(ShowCreation(hop), run_time=0.8)
                self.play(flag.slab.animate.set_color(T.attacker_bytes), FadeTransform(flag.title, newlab))
                self.say("mov [ebx], eax writes the magic value into flag_check.")
                trail.add(hop)

            self.play(blk.slab.animate.set_color(getattr(T, blk.role)), run_time=0.3)
            self.beat(pause=0.4)
            src_off, eip = esp, ev.next_eip
            esp += w

        assert eip == tr.symbols["win"]
        win = blocks[eip]
        jump = arc3d(stack.at(src_off).cells.get_right(), win.top(), color=T.win)
        self.play(ShowCreation(jump), stack.at(src_off).cells.animate.set_opacity(0.35), esp_to(esp - w),
                  *regs.set("eip", eip, role="win"), run_time=1.0)
        trail.add(jump)
        self.play(win.slab.animate.set_color(T.win).stretch(2.2, 2, about_edge=IN),
                  win.lab.animate.shift(OUT * 0.45))
        self.say(self.win_caption)
        self.beat()

        self.play(trail.animate.set_stroke(width=7),
                  frame.animate.reorient(-40, 58, 0, center=(0.8, 0.2, 0.8), height=10.0), run_time=2)
        self.say("NX never fired. Every instruction that ran came from .text.")
        frame.add_ambient_rotation(3 * DEG)
        self.wait(4)
        frame.clear_updaters()
        self.beat(pause=1.5)


class RitRop(RopScene):
    trace_name = "rit-rop"
    chain_caption = "One gadget loads two values, then writes one into the other's address."
    win_caption = "flag_check holds the magic value, so win() prints the flag. FLAG{baby_rop}"


class Stack2_13(RopScene):
    trace_name = "stack2-13"
    subtitle = "The overflow is small, so stage the real chain and pivot onto it."
    chain_caption = "A short trigger loads the staged chain's address, then pivots esp onto it."
    win_caption = "The pivoted chain wrote the magic value and returned into win(). FLAG{stack_pivot}"


# --- ret2libc: call a function already in memory ----------------------------

class Stack2_11(FlatStack):
    trace_name = "stack2-11"

    def construct(self):
        tr = self.setup_trace()
        self.open_title("The stack is NX, so you can't run code there. Call one that already exists.")
        self.build_code_stack()
        self.say("Overwrite the return address with system, then build a fake call frame above it.")
        self.make_strip()
        self.feed()
        self.clear_input()

        # read back the three words that make the fake frame
        labels = [("system()", "libc"), ("fake return", "crash"), ('"/bin/sh"', "libc")]
        read = []
        for k, off in enumerate(range(tr.ret_off, tr.ret_off + 3 * tr.word, tr.word)):
            word = tr.ret_off + k * tr.word
            w = self.stack.at(off)
            value, anims = le_assemble(w, color=getattr(T, labels[k][1]))
            self.play(*anims, run_time=0.6)
            lab = mono(labels[k][0], 15, getattr(T, labels[k][1])).next_to(value, RIGHT, buff=0.2)
            self.play(FadeIn(lab, shift=LEFT * 0.12), w.boxes().animate.set_fill(getattr(T, labels[k][1]), 0.85),
                      run_time=0.35)
            read.append(VGroup(value, lab))
        self.say("system reads its return address and argument straight off the stack.")
        self.beat()
        self.play(FadeOut(VGroup(*read)))

        sysbox = target_box("system()", tr.symbols["system"], "libc", width=3.2).move_to(RIGHT * 3.4 + UP * 2.6)
        shbox = target_box('"/bin/sh"', tr.symbols["binsh"], "libc", width=3.2).move_to(RIGHT * 3.4 + DOWN * 1.2)
        self.play(FadeIn(sysbox))
        self.jump_to(sysbox, T.libc, win=True)
        self.say("Its argument is the address of /bin/sh, so it spawns a shell.")
        arg_slot = self.stack.at(tr.ret_off + 2 * tr.word)
        arrow = CurvedArrow(arg_slot.cells.get_right() + RIGHT * 0.05, shbox.get_left() + LEFT * 0.05,
                            angle=30 * DEG, color=T.libc, stroke_width=5)
        self.play(FadeIn(shbox), ShowCreation(arrow))
        self.play(Flash(shbox, color=T.win, flash_radius=1.1))
        self.say("You called system(\"/bin/sh\") without any code on the stack. FLAG{ret2libc}")
        self.beat(pause=2)


# --- SROP: one gadget sets every register (VRIG sizing note) ----------------

class Stack2_14(FlatStack):
    trace_name = "stack2-14"

    def construct(self):
        tr = self.setup_trace()
        self.open_title("sigreturn restores every register from a frame on the stack.")
        self.build_code_stack(n_words=tr.total // tr.word)
        self.say("Overwrite the return address with sigreturn, then lay a fake signal frame above it.")
        self.make_strip()
        self.feed()
        self.clear_input()

        # name the frame: sigreturn at ret, then the register slots
        sig_word = self.stack.at(tr.ret_off)
        value, anims = le_assemble(sig_word, color=T.gadget)
        self.play(*anims, run_time=0.6)
        lab = mono("sigreturn", 15, T.gadget).next_to(value, RIGHT, buff=0.2)
        self.play(FadeIn(lab, shift=LEFT * 0.12), sig_word.boxes().animate.set_fill(T.gadget, 0.85))
        self.say("One gadget pops a whole saved-register frame and jumps where its eip slot says.")
        self.beat()
        self.play(FadeOut(VGroup(value, lab)))

        # VRIG's own verdict, read from the trace
        srop = next(s for s in tr.steps if s["label"].startswith("SROP"))
        verdict = next((l["msg"] for l in srop["logs"] if l["cls"] == "error"), "")
        called = any("Calling sigreturn" in l["msg"] for l in srop["logs"])
        assert called and not tr.won()

        panel_lines = VGroup(
            mono("sigreturn reached", 20, T.win),
            mono(verdict, 18, T.crash),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        panel = SurroundingRectangle(panel_lines, buff=0.25).set_stroke(T.grid, 2).set_fill(T.background, 0.92)
        card = VGroup(panel, panel_lines).move_to(RIGHT * 3.0 + UP * 1.4)
        self.play(FadeIn(card, shift=UP * 0.1))
        self.say("sigreturn runs, but VRIG reserves less room than an x86 signal frame needs, so the win never registers.")
        self.beat()
        self.say("The technique is right. The simulator's frame is 44 bytes where the sigcontext wants 60.")
        self.beat(pause=2)


# --- format strings: printf reads and writes the stack ----------------------

class FmtScene(VrigScene):
    trace_name = ""

    def load(self):
        self.data = json.loads((TRACE_DIR / f"{self.trace_name}.json").read_text())
        assert self.data["solved"], "fmt exercise not solved, re-export it"
        return self.data

    def open(self, subtitle):
        d = self.data
        title = prose(d["title"], 44).to_edge(UP, buff=0.4)
        sub = prose(subtitle, 25, T.text_dim).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.6).to_corner(UL, buff=0.25))
        self.title = title

    def show_input(self):
        d = self.data
        txt = mono(d["input"], 26, T.attacker_bytes)
        box = SurroundingRectangle(txt, buff=0.18).set_stroke(T.attacker_bytes, 2).set_fill(T.cell_fill, 0.6)
        grp = VGroup(box, txt).to_corner(UL, buff=0.5).shift(DOWN * 1.0)
        lab = mono("your format string", 15, T.text_dim).next_to(grp, UP, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(lab), FadeIn(grp))
        self.fmt_text = txt
        return grp

    def build_slots(self, n):
        d = self.data
        rows = VGroup()
        for s in d["stack"][:n]:
            num = mono(f"slot {s['slot']}", 15, T.text_dim)
            cell = mono(h32(s["value"]), 20, T.text)
            box = SurroundingRectangle(cell, buff=0.12).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            name = mono(s["label"], 15, T.label)
            row = VGroup(num, VGroup(box, cell), name).arrange(RIGHT, buff=0.3)
            row.slot_meta = s
            row.cellbox = box
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        rows.to_edge(RIGHT, buff=0.8).shift(UP * 0.2)
        lab = mono("the stack printf walks", 16, T.text_dim).next_to(rows, UP, buff=0.25)
        self.play(FadeIn(rows, lag_ratio=0.05), FadeIn(lab))
        self.rows = rows
        return rows


class Logic07(FmtScene):
    trace_name = "logic-07"

    def construct(self):
        d = self.load()
        self.open("Your input is the format string, so %x reads whatever printf finds on the stack.")
        self.show_input()
        self.build_slots(8)

        secret_slot = d["secretSlot"]
        self.say("Each %x prints one stack slot and steps to the next.")
        # walk slot by slot up to the secret
        for s in d["stack"][:secret_slot]:
            row = self.rows[s["slot"] - 1]
            if s["slot"] == secret_slot:
                self.play(row.cellbox.animate.set_stroke(T.leak, 3).set_fill(T.leak, 0.25),
                          row[1][1].animate.set_color(T.leak), Indicate(row, color=T.leak))
            else:
                self.play(Indicate(row, color=T.highlight, scale_factor=1.03), run_time=0.4)
        self.say(f"The fourth %x prints the secret, {h32(d['secretValue'])}.")
        self.beat()
        self.say("Same trick leaks canaries, saved return addresses, and pointers. Secret leaked.")
        self.beat(pause=2)


class Logic08(FmtScene):
    trace_name = "logic-08"

    def construct(self):
        d = self.load()
        self.open("%n does not print. It writes the count of characters so far to a pointer on the stack.")
        self.show_input()
        self.build_slots(4)

        target = d["targetAddr"]
        self.say("The first four bytes of your input are the address of authorized, sitting in slot 4.")
        slot4 = self.rows[3]
        self.play(slot4.cellbox.animate.set_stroke(T.attacker_bytes, 3), Indicate(slot4, color=T.attacker_bytes))
        self.beat()

        self.say("Three %x step past the first slots, then %n writes to slot 4.")
        for i in range(3):
            self.play(Indicate(self.rows[i], color=T.highlight, scale_factor=1.03), run_time=0.4)

        tgt = target_box("authorized", target, "win", width=3.0).next_to(self.rows, DOWN, buff=0.5)
        self.play(FadeIn(tgt))
        arrow = CurvedArrow(slot4.cellbox.get_bottom() + DOWN * 0.05, tgt.get_top() + UP * 0.05,
                            angle=-30 * DEG, color=T.attacker_bytes, stroke_width=5)
        self.play(ShowCreation(arrow))
        self.play(tgt[0].animate.set_fill(T.win, 0.35), Flash(tgt, color=T.win, flash_radius=1.1))
        self.say("authorized goes from 0 to non-zero, so win() runs. FLAG{format_string_write}")
        self.beat(pause=2)
