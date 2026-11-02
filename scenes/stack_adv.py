"""
Recap CTFs and the advanced input-hex lessons. Every one of these is, in
VRIG's sim, "overflow buf and land on win()". The advanced lessons say what
the real bug is in their text and then model it that way, so each video
shows the real structure first (vtable, link_map chain, FILE, kernel
boundary) and then runs VRIG's own trace.

    node tools/vrig-trace/dist/vrig-stack_adv.mjs traces
    manimgl scenes/stack_adv.py Ctf47 -w -l
"""
import sys
from pathlib import Path

from manimlib import *

sys.path.insert(0, str(Path(__file__).parent))
from unit3_stack_ii import CodeBlock  # noqa: E402

from vrig.mob.cpu import CodeListing, RegisterFile  # noqa: E402
from vrig.mob.memory import CELL, LIFT, ByteCell, PayloadStrip, le_assemble, mono, prose  # noqa: E402
from vrig.mob.space import arc3d, billboard  # noqa: E402
from vrig.mob.stack_adv import FrameView, StructView, pointer, protection_row  # noqa: E402
from vrig.scene import Vrig3DScene  # noqa: E402
from vrig.theme import T  # noqa: E402
from vrig.trace import StackTrace, h32  # noqa: E402

TILT = dict(theta_degrees=-24, phi_degrees=50, gamma_degrees=0, center=(0.9, 0.0, 0.6), height=9.2)


def first_sentence(msg: str) -> str:
    # winMsg runs a paragraph. The first sentence is the claim, rest is history
    cut = msg.find(". ")
    return msg if cut < 0 else msg[:cut + 1]


def on_floor(blk, at):
    """move_to() centers the whole block, billboard label included, which
    sinks the slab below z=0. Under a floor plane it then disappears."""
    blk.move_to(at)
    blk.shift(OUT * -blk.slab.get_z(IN))
    return blk


def box_label(text: str, role: str, size: int = 20) -> VGroup:
    t = mono(text, size, getattr(T, role))
    b = SurroundingRectangle(t, buff=0.14).set_stroke(getattr(T, role), 2)
    b.set_fill(T.background, 0.9).shift(-LIFT)
    return VGroup(b, t)


class StackAdv(Vrig3DScene):
    trace_name = ""
    src_from = "void vuln"      # first source line kept in the listing
    src_extra = ("void win",)   # one-liners from elsewhere worth keeping
    frame_names: dict = {}
    recon = False               # CTF recap: symbol table + offset math up front
    takeaway = ""

    def construct(self):
        tr = StackTrace.load(self.trace_name)
        assert tr.raw["solved"], "trace payload doesn't solve it, re-export"
        self.tr, self.raw = tr, tr.raw
        self.frame.reorient(0, 0)
        self.tilted = False
        self.w = tr.word

        self.intro()
        if self.recon:
            self.recon_act()
        self.concept()
        self.code_act()
        self.frame_act()
        self.overflow_act()
        if tr.canary_size:
            self.canary_act()
        self.return_act()
        self.outro()

    # -- small helpers ----------------------------------------------------

    def step(self, label_start: str) -> dict:
        return self.tr.steps[self.tr.step_index(label_start)]

    def clear(self, keep=()):
        mobs = [m for m in self.mobjects if m not in keep and m is not self.cap and m is not self.title]
        if mobs:
            self.play(*map(FadeOut, mobs), run_time=0.6)

    def sym_name(self, v: int) -> str:
        if v == self.raw["origRet"]:
            return "main+0x25"
        for name, addr in self.tr.symbols.items():
            if addr == v:
                return f"{name}()"
        return "?"

    # -- intro --------------------------------------------------------------

    def intro(self):
        raw = self.raw
        title = prose(raw["title"], 46).to_edge(UP, buff=0.9)
        if title.get_width() > 12.5:
            title.set_width(12.5)
        unit = mono(raw["unit"] + "  /  " + raw["exercise"], 20, T.text_dim).next_to(title, DOWN, buff=0.25)
        prots = protection_row(raw["protections"]).next_to(unit, DOWN, buff=0.6)
        if prots.get_width() > 12.5:
            prots.set_width(12.5)
        self.play(Write(title), FadeIn(unit, shift=UP * 0.2))
        self.play(LaggedStartMap(FadeIn, prots, shift=UP * 0.15, lag_ratio=0.15))
        self.intro_caption()
        self.beat()
        small = title.copy().scale(0.55).to_corner(UL, buff=0.3)
        self.play(Transform(title, small), FadeOut(unit), FadeOut(prots))
        self.title = title

    def intro_caption(self):
        pass

    # -- CTF recon: where is win, how far is ret ----------------------------

    def recon_act(self):
        tr = self.tr
        syms = StructView("symbols", [("", n, h32(a)) for n, a in tr.symbols.items()], width=3.8)
        syms.move_to(LEFT * 3.6 + UP * 0.3)
        self.play(FadeIn(syms, lag_ratio=0.05))
        self.say(self.recon_caption or "Step one is the symbol table. No ASLR, so win() sits where it says.")
        win = syms.row("win")
        self.play(win[0].animate.set_fill(T.win, 0.35), win[3].animate.set_color(T.win))
        self.beat()

        rows = [("buf", tr.buf_size, "buffer")]
        if tr.canary_size:
            rows.append(("canary", tr.canary_size, "canary"))
        rows.append(("saved ebp", tr.raw["layout"]["ebpSize"], "saved_fp"))
        math = VGroup()
        for name, n, role in rows:
            row = VGroup(mono(name, 22, getattr(T, role)), mono(f"{n} bytes", 22, T.text))
            row[0].move_to(ORIGIN, aligned_edge=LEFT)
            row[1].set_x(2.2, LEFT).match_y(row[0])
            math.add(row)
        rule = Line(LEFT, RIGHT).set_width(3.6).set_stroke(T.grid, 2)
        total = VGroup(mono("ret at  +", 22, T.saved_ret), mono(f"{tr.ret_off}", 22, T.highlight)).arrange(RIGHT, buff=0.1)
        math.add(rule, total)
        math.arrange(DOWN, aligned_edge=LEFT, buff=0.22).move_to(RIGHT * 2.8 + UP * 0.4)
        self.play(LaggedStartMap(FadeIn, math[:-2], shift=RIGHT * 0.2, lag_ratio=0.3))
        self.play(ShowCreation(rule), FadeIn(total, shift=UP * 0.1))
        self.say(f"Count up from buf. The return address starts {tr.ret_off} bytes in.")
        self.beat()
        self.clear()

    recon_caption = ""

    # -- per-lesson concept act. default is nothing --------------------------

    def concept(self):
        pass

    # -- source + frame -----------------------------------------------------

    def pick_source(self) -> list[tuple[int, str]]:
        src = self.tr.source
        keep = []
        for i, l in enumerate(src):
            if any(l.startswith(p) for p in self.src_extra) and l.rstrip().endswith("}"):
                keep.append((i, l))
        if keep:
            keep.append((-1, ""))
        start = next(i for i, l in enumerate(src) if l.startswith(self.src_from))
        for i in range(start, len(src)):
            keep.append((i, src[i]))
            if src[i].strip() == "}":
                break
        return keep

    def code_act(self):
        picked = self.pick_source()
        self.src_rows = {orig: k for k, (orig, _) in enumerate(picked)}
        code = CodeListing([l for _, l in picked], size=18)
        code.to_corner(UL, buff=0.5).shift(DOWN * 0.5)
        if code.get_width() > 6.0:
            code.set_width(6.0, about_edge=UL)
        self.code = code
        self.play(FadeIn(code, shift=RIGHT * 0.3))

    def focus(self, pattern: str, **kw):
        for orig, k in self.src_rows.items():
            if orig >= 0 and pattern in self.tr.source[orig]:
                self.play(self.code.focus(k), **kw)
                return
        raise KeyError(pattern)

    def focus_close(self, **kw):
        # vuln's closing brace, the last bare "}" in the listing
        k = max(k for orig, k in self.src_rows.items() if orig >= 0 and self.tr.source[orig].strip() == "}")
        self.play(self.code.focus(k), **kw)

    def make_view(self) -> FrameView:
        return FrameView(self.tr, self.tr.step_index("Make room"))

    def place_view(self, view):
        view.move_to(RIGHT * 2.6 + UP * 0.2)
        # short frames read better a size up. remember it, 3d undoes it
        self.view_scale = min(1.3, 5.6 / view.get_height())
        view.scale(self.view_scale)

    def frame_act(self):
        tr = self.tr
        view = self.make_view()
        self.place_view(view)
        tags = view.frame_tags(self.frame_names)
        self.view = view
        w = self.w

        ret_w = view.at(tr.ret_off)
        ebp_w = view.at(tr.ebp_off)
        low = VGroup(*(view.at(o) for o in range(max(view.start, 0), tr.ebp_off, w)))
        if view.fold is not None:
            low.add(view.fold)
        self.say(self.frame_caption or f"vuln() gets called. The return address {h32(tr.raw['origRet'])} goes on the stack first.")
        self.play(FadeIn(ret_w, shift=DOWN * 0.2), FadeIn(tags[-1]))
        self.play(FadeIn(ebp_w, shift=DOWN * 0.2), FadeIn(tags[-2]))
        self.play(FadeIn(low, lag_ratio=0.08, shift=DOWN * 0.1), FadeIn(tags[:-2]))
        self.beat()

    frame_caption = ""

    # -- gets() -------------------------------------------------------------

    def overflow_act(self):
        tr, view = self.tr, self.view
        w = self.w
        self.focus(self.write_pattern)
        self.say(self.overflow_caption)

        strip = PayloadStrip(tr.payload).next_to(self.code, DOWN, buff=0.4, aligned_edge=LEFT)
        if tr.canary_size:
            for c in strip.cells[tr.buf_size:tr.ebp_off]:
                c.paint("canary")
        strip_lab = mono("payload", 16, T.text_dim).next_to(strip, UP, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(strip_lab), FadeIn(strip, lag_ratio=0.02, run_time=1.0))
        self.strip = VGroup(strip_lab, strip)
        self.beat()

        for st in tr.steps:
            if "(): write" not in st["label"]:
                continue
            off = st["hl"][0]
            data = st["memory"][off:off + w]
            src_cells = strip.cells[off:off + w]
            role = "canary" if tr.buf_size <= off < tr.ebp_off else "attacker_bytes"
            if off < view.start:
                self.play(src_cells.animate.set_opacity(0.2), *view.write_word(off, data, role), run_time=0.15)
                continue
            self.play(
                *[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, view.at(off).cells)],
                src_cells.animate.set_opacity(0.2),
                run_time=0.35 if off < tr.buf_size else 0.6,
            )
            over = tr.buf_size <= off
            self.play(*view.write_word(off, data, role, overflow=over), run_time=0.25)
            self.after_write(off)
        self.beat()

    write_pattern = "gets(buf"
    overflow_caption = "gets() copies until newline. It never checks the size."

    def after_write(self, off: int):
        tr = self.tr
        if off == tr.buf_size and tr.canary_size:
            self.say("The canary slot gets the leaked value back, byte for byte.", run_time=0.5)
        elif off == tr.ebp_off:
            self.say("Past buf. Saved ebp takes filler.", run_time=0.5)
        elif off == tr.ret_off:
            self.say(f"Then the return address. It now holds {h32(tr.word_at(tr.ret_off))}.", run_time=0.5)

    # -- canary -------------------------------------------------------------

    def canary_act(self):
        tr, view = self.tr, self.view
        st = self.step("Check the tripwire")
        ok = "intact" in st["logs"][0]["msg"]
        assert ok and tr.raw["canaryIntact"]
        word = view.at(tr.buf_size)
        now = tr.word_at(tr.buf_size, tr.step_index("Check the tripwire"))
        check = mono(f"{h32(now)} == {h32(tr.raw['canaryValue'])}", 20, T.mitigation)
        check.next_to(view, UP, buff=0.25).align_to(view, RIGHT)
        self.play(Indicate(word.cells, color=T.canary, scale_factor=1.06), FadeIn(check, shift=DOWN * 0.1))
        self.say("Before ret, the epilogue compares the canary. Same value, so no abort.")
        self.beat()
        self.play(FadeOut(check))

    # -- ret ----------------------------------------------------------------

    def read_ret(self):
        tr, view = self.tr, self.view
        st = self.step("Return")
        target = tr.raw["retAfter"]
        assert hex(target)[2:] in st["logs"][0]["msg"].lower()
        word = view.at(tr.ret_off)
        value, anims = le_assemble(word)
        # above the slot: to the right there's the tag and then the frame edge
        value.next_to(word, UP, buff=0.3).align_to(word, LEFT)
        self.play(*anims, run_time=0.7)
        name = self.sym_name(target)
        role = "win" if name == "win()" else "label"
        m = mono(name, 18, getattr(T, role)).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(m, shift=LEFT * 0.15))
        return VGroup(value, m)

    def return_act(self):
        tr = self.tr
        if self.ret_pattern:
            self.focus(self.ret_pattern)
        else:
            self.focus_close()
        meaning = self.read_ret()
        self.say(self.ret_caption or "ret pops that word into eip. Read backwards, it's win().")
        self.beat()
        self.play(FadeOut(meaning), FadeOut(self.code), FadeOut(self.strip), FadeOut(self.title))
        self.unsay()
        self.jump3d()

    ret_pattern = ""
    ret_caption = ""

    def jump3d(self, target_name="win()"):
        tr, view, frame = self.tr, self.view, self.frame
        view.tags.set_opacity(0)
        self.play(view.animate.scale(1 / self.view_scale).move_to(LEFT * 3.0 + UP * 0.1))
        self.play(view.tags.animate.set_opacity(1), run_time=0.4)
        self.play(frame.animate.reorient(**TILT), run_time=2.2)
        self.tilted = True

        win_addr = tr.symbols["win"]
        main_blk = CodeBlock("main+0x25", tr.raw["origRet"], "text_section", frame)
        win_blk = CodeBlock("win()", win_addr, "text_section", frame)
        on_floor(main_blk, RIGHT * 3.6 + DOWN * 0.7)
        on_floor(win_blk, RIGHT * 3.6 + UP * 1.1)
        grp = Group(main_blk, win_blk)
        text_lab = billboard(mono(".text  r-x", 20, T.text_dim).next_to(grp, DOWN, buff=0.35), frame)
        self.play(LaggedStart(*(FadeIn(b, shift=OUT * 0.5) for b in grp), lag_ratio=0.3), FadeIn(text_lab))

        regs = RegisterFile(names=("eip", "esp")).to_corner(UR, buff=0.35).fix_in_frame()
        self.play(FadeIn(regs))
        self.say("Normally ret lands back in main. This time the slot says otherwise.")
        self.beat()

        ghost = arc3d(view.at(tr.ret_off).cells.get_right(), main_blk.top(), color=T.text_dim, width=3)
        ghost.set_stroke(opacity=0.5)
        self.play(ShowCreation(ghost), run_time=0.8)
        self.play(FadeOut(ghost), run_time=0.4)

        jump = arc3d(view.at(tr.ret_off).cells.get_right(), win_blk.top(), color=T.win)
        esp_after = tr.addr(tr.ret_off + self.w)
        self.play(ShowCreation(jump), *regs.set("eip", tr.raw["retAfter"], role="win"),
                  *regs.set("esp", esp_after, role="label"), run_time=1.2)
        self.play(win_blk.slab.animate.set_color(T.win).stretch(2.4, 2, about_edge=IN),
                  win_blk.lab.animate.shift(OUT * 0.45))
        last = tr.steps[-1]["logs"][-1]["msg"].lstrip("→ ").split(" —")[0]
        self.say(f"{last}, says VRIG.")
        self.beat()
        self.jumped = Group(main_blk, win_blk, text_lab, jump, regs)

    # -- end ----------------------------------------------------------------

    def outro(self):
        raw = self.raw
        head = prose(raw["winTitle"], 34, T.win).to_edge(UP, buff=0.35).fix_in_frame()
        plate = BackgroundRectangle(head, buff=0.15).set_fill(T.background, 0.85).fix_in_frame()
        self.play(FadeIn(plate), Write(head))
        self.say(first_sentence(raw["winMsg"]), width=80, size=24)
        self.beat()
        if self.takeaway:
            self.say(self.takeaway)
        if self.tilted:
            self.frame.add_ambient_rotation(3 * DEG)
            self.wait(3)
            self.frame.clear_updaters()
        else:
            self.wait(1.5)
        self.beat(pause=1.5)


# ===========================================================================
# unit10: recap CTFs, the whole chain end to end
# ===========================================================================

class Ctf47(StackAdv):
    trace_name = "ctf-47"
    recon = True
    takeaway = "Find win() and count to ret. Write the address little-endian and the chain is done."

    def intro_caption(self):
        self.say("A sixteen byte buffer with no protections. Nothing ever calls win().")


class Ctf49(StackAdv):
    trace_name = "ctf-49"
    recon = True
    src_extra = ()
    takeaway = "A bigger buffer only changes the padding. The chain stays the same."

    def pick_source(self):
        # win() here is three lines, keep it whole
        src = self.tr.source
        a = next(i for i, l in enumerate(src) if l.startswith("void win"))
        b = next(i for i, l in enumerate(src) if l.startswith("void vuln"))
        rows = [(i, src[i]) for i in range(a, a + 3)] + [(-1, "")]
        end = next(i for i in range(b, len(src)) if src[i].strip() == "}")
        return rows + [(i, src[i]) for i in range(b, end + 1)]

    def intro_caption(self):
        self.say("Twenty four bytes of buffer this time, and still nothing in the way.")


class Ctf50(StackAdv):
    trace_name = "ctf-50"
    recon = True
    write_pattern = "gets(buf)"
    overflow_caption = "Stage two. gets(buf) takes padding, the canary, filler, and win()."
    takeaway = "Leak first, then overflow. The canary only works while it stays secret."

    def intro_caption(self):
        self.say("A canary sits between buf and the return address. Two stages get past it.")

    def frame_act(self):
        super().frame_act()
        tr, view = self.tr, self.view
        self.focus("printf(fmt)")
        self.say("Stage one. printf(fmt) treats your input as a format string, and %p walks up the stack.")
        word = view.at(tr.buf_size)
        leak = box_label(h32(tr.raw["canaryValue"]), "leak", 22)
        out_lab = mono("stdout", 16, T.text_dim)
        out = VGroup(out_lab, leak).arrange(RIGHT, buff=0.3).next_to(view, UP, buff=0.3).align_to(view, RIGHT)
        self.play(Indicate(word.cells, color=T.leak, scale_factor=1.06))
        self.play(TransformFromCopy(word.cells, leak), FadeIn(out_lab))
        self.say(f"Out comes the canary, {h32(tr.raw['canaryValue'])}. Its low byte is zero, like a terminator.")
        self.beat()
        self.play(FadeOut(out))


class Ctf52(StackAdv):
    trace_name = "ctf-52"
    recon = True
    takeaway = "On real Windows you would aim at the SEH handler. VRIG grades the return address."

    def pick_source(self):
        src = self.tr.source
        rows = [(i, l) for i, l in enumerate(src) if l.startswith("void win")] + [(-1, "")]
        b = next(i for i, l in enumerate(src) if l.startswith("void vuln"))
        end = next(i for i in range(b, len(src)) if src[i].strip() == "}")
        return rows + [(i, src[i]) for i in range(b, end + 1) if "//" not in src[i][:4]]

    def intro_caption(self):
        self.say("A Windows-style frame with an SEH record. VRIG still grades the return address.")

    def return_act(self):
        self.focus("*(int*)0")
        self.say("On real Windows this null write faults first, and the SEH handler runs before ret.")
        self.beat()
        self.say("VRIG's sim has no SEH record and no fault. It goes straight to ret.")
        self.beat()
        super().return_act()


# ===========================================================================
# unit15: canaries
# ===========================================================================

class Mit81(StackAdv):
    trace_name = "mit-81"
    takeaway = "A leaked canary is just four more bytes of padding."

    def intro_caption(self):
        self.say("The compiler parks a secret word between buf and the return address.")

    def concept(self):
        cards = VGroup()
        kinds = [
            ("terminator", "00 0d 0a ff", "string copies stop on it"),
            ("random", "from /dev/urandom", "picked at startup"),
            ("XOR", "random ^ frame ptr", "tied to this frame"),
        ]
        for name, val, why in kinds:
            c = VGroup(mono(name, 22, T.canary), mono(val, 18, T.text), mono(why, 15, T.text_dim))
            c.arrange(DOWN, buff=0.18)
            box = SurroundingRectangle(c, buff=0.25).set_stroke(T.canary, 1.5)
            box.set_width(3.7, stretch=True)
            cards.add(VGroup(box, c))
        cards.arrange(RIGHT, buff=0.4).move_to(UP * 0.4)
        self.play(LaggedStartMap(FadeIn, cards, shift=UP * 0.2, lag_ratio=0.3))
        self.say("Three kinds of canary. Each one breaks if you know its value.")
        self.beat()
        self.clear()

    def frame_act(self):
        super().frame_act()
        tr, view = self.tr, self.view
        self.focus("Leaked canary")
        word = view.at(tr.buf_size)
        leak = box_label(f"Leaked canary: {h32(tr.raw['canaryValue'])}", "leak", 20)
        leak.next_to(view, UP, buff=0.3).align_to(view, RIGHT)
        self.play(Indicate(word.cells, color=T.leak, scale_factor=1.06))
        self.play(TransformFromCopy(word.cells, leak))
        self.say("The program prints it for you. VRIG's canary has a zero low byte, so it doubles as a terminator.")
        self.beat()
        self.play(FadeOut(leak))


# ===========================================================================
# unit16: the real structure first, then VRIG's model of it
# ===========================================================================

class ModelNote:
    """Shared bridge line between the concept act and VRIG's trace."""

    def bridge(self, text="VRIG models this hijack as a return-address overwrite. Here is its trace."):
        self.say(text)
        self.beat()
        self.clear()


class Adv88(ModelNote, StackAdv):
    trace_name = "adv-88"
    src_extra = ("void win",)
    frame_names = {}
    takeaway = "Whoever controls the vptr picks which function a virtual call runs."

    def intro_caption(self):
        self.say("A virtual call reads a pointer from the object, then a pointer from the table.")

    def concept(self):
        tr = self.tr
        win, base = tr.symbols["win"], tr.base
        obj = StructView("obj  (Base)", [("+0", "vptr", "&Base_vtable"), ("+4", "name[8]", "...")],
                         width=4.0).move_to(LEFT * 4.3 + UP * 0.6)
        vt = StructView("Base_vtable", [("[0]", "action", "Base::action")], width=3.6).move_to(RIGHT * 0.9 + UP * 1.9)
        fake = StructView(f"fake vtable @ {h32(base)} (buf)", [("[0]", "action", h32(win))], role="attacker_bytes",
                          width=3.6).move_to(RIGHT * 0.9 + DOWN * 1.0)
        normal = box_label('puts("normal")', "label", 18).next_to(vt, RIGHT, buff=0.8)
        winb = box_label(f"win()  {h32(win)}", "win", 18).next_to(fake, RIGHT, buff=0.8)
        call = mono("obj->action()", 22, T.highlight).move_to(LEFT * 4.3 + DOWN * 1.6)

        self.play(FadeIn(obj), FadeIn(vt), FadeIn(call))
        a1 = pointer(obj.row("vptr"), vt.row("action"))
        a2 = Arrow(vt.row("action").get_right(), normal.get_left(), buff=0.1).set_color(T.pointer)
        self.play(GrowArrow(a1), FadeIn(normal))
        self.play(GrowArrow(a2))
        self.say("obj->action() loads vptr, then slot zero of the vtable, then calls it.")
        self.beat()

        self.play(FadeIn(fake, shift=UP * 0.2), FadeIn(winb))
        self.say(f"The overflow plants a fake vtable at {h32(base)} and points vptr at it.")
        self.play(*obj.set("vptr", h32(base)))
        a1b = pointer(obj.row("vptr"), fake.row("action"), role="attacker_bytes", bend=0.5)
        a3 = Arrow(fake.row("action").get_right(), winb.get_left(), buff=0.1).set_color(T.win)
        self.play(ReplacementTransform(a1, a1b), a2.animate.set_opacity(0.25), normal.animate.set_opacity(0.3))
        self.play(GrowArrow(a3), Indicate(call, color=T.win))
        self.say("Same two loads, same call instruction. It ends in win().")
        self.beat()
        self.bridge(f"VRIG models the hijack as a return-address overwrite. The fake vtable still goes in buf[0..3].")

    def after_write(self, off):
        if off == 0:
            self.say(f"buf[0..3] is the fake vtable slot, {h32(self.tr.symbols['win'])}.", run_time=0.5)
        else:
            super().after_write(off)


class Adv89(ModelNote, StackAdv):
    trace_name = "adv-89"
    takeaway = "Type confusion turns plain data into a code pointer without writing out of bounds."

    def intro_caption(self):
        self.say("A cast that trusts the wrong layout turns one object into another type.")

    def concept(self):
        tr = self.tr
        win = tr.symbols["win"]
        # name[4..8] typed by the user. Same four bytes win() is made of.
        name_hi = [(win >> (8 * i)) & 0xff for i in range(4)]
        words = [("&vtable", None), ("41 41 41 41", None), (" ".join(f"{b:02x}" for b in name_hi), "attacker_bytes"),
                 ("...", None)]
        cells = VGroup()
        for txt, role in words:
            r = Rectangle(2.7, 0.7).set_stroke(T.grid, 1.5).set_fill(getattr(T, role or "cell_fill"), 0.35 if role else 1)
            cells.add(VGroup(r, mono(txt, 21, T.text).move_to(r).shift(LIFT)))
        cells.arrange(RIGHT, buff=0.05).move_to(UP * 0.5)
        offs = VGroup(*(mono(f"+{4 * i}", 15, T.text_dim).next_to(c, DOWN, buff=0.1) for i, c in enumerate(cells)))
        base_l = VGroup(*(mono(n, 18, T.local_var).next_to(c, UP, buff=0.2)
                          for n, c in zip(["vptr", "name[0..3]", "name[4..7]", "role"], cells)))
        admin_l = VGroup(*(mono(n, 18, T.arg).next_to(c, UP, buff=0.2)
                           for n, c in zip(["vptr", "level", "callback", "data"], cells)))
        bt = mono("Base *b", 22, T.local_var).next_to(base_l, UP, buff=0.35)
        at = mono("Admin *a = (Admin*)b", 22, T.arg).next_to(admin_l, UP, buff=0.35)

        self.play(FadeIn(cells, lag_ratio=0.1), FadeIn(offs), FadeIn(base_l), FadeIn(bt))
        self.say("As a Base, offset eight is just the back half of name. The user fills it.")
        self.play(Indicate(cells[2], color=T.attacker_bytes))
        self.beat()
        self.play(FadeOut(base_l, shift=UP * 0.2), FadeOut(bt), FadeIn(admin_l, shift=UP * 0.2), FadeIn(at))
        self.say("Cast it to Admin and the same four bytes are callback.")
        val = mono(h32(win), 22, T.win).next_to(cells[2], DOWN, buff=0.7)
        self.play(TransformFromCopy(cells[2][1], val, path_arc=-40 * DEG))
        winb = box_label("win()", "win", 20).next_to(val, RIGHT, buff=0.8)
        self.play(GrowArrow(Arrow(val.get_right(), winb.get_left(), buff=0.1).set_color(T.win)), FadeIn(winb))
        self.say("a->callback() reads them little-endian and jumps to win().")
        self.beat()
        self.bridge()


class Adv92(ModelNote, StackAdv):
    trace_name = "adv-92"
    write_pattern = "read(0, buf"
    overflow_caption = "read() takes up to 256 bytes into a 16 byte buffer."
    takeaway = "ret2dlresolve needs no libc leak. The linker finds system() for you."

    def intro_caption(self):
        self.say("Lazy binding resolves a function the first time it's called. You can forge the lookup.")

    def concept(self):
        lm = StructView("link_map->l_info", [("", "DT_JMPREL", "JMPREL"), ("", "DT_SYMTAB", "SYMTAB"),
                                             ("", "DT_STRTAB", "STRTAB")], width=3.0)
        lm.move_to(LEFT * 5.1 + UP * 1.2)
        res = mono("_dl_runtime_resolve(link_map, reloc_index)", 17, T.highlight).move_to(UP * 3.05 + LEFT * 1.0)

        jm = StructView("JMPREL  Elf32_Rel[]", [("[0]", "gets", "r_info"), ("[1]", "puts", "r_info")], width=3.0)
        sy = StructView("SYMTAB  Elf32_Sym[]", [("[1]", "gets", "st_name"), ("[2]", "puts", "st_name")], width=3.0)
        st = StructView("STRTAB", [("", '"gets\\0puts\\0"', "")], width=3.0)
        tables = VGroup(jm, sy, st).arrange(DOWN, buff=0.45).move_to(LEFT * 1.1 + DOWN * 0.15)

        fk = StructView("forged, in your input", [("", "Elf32_Rel", "r_info = j<<8|7"),
                                                  ("", "Elf32_Sym", "st_name = k"),
                                                  ("", "string", '"system\\0"')],
                        role="attacker_bytes", width=3.4).move_to(RIGHT * 4.6 + UP * 0.6)

        self.play(FadeIn(res), FadeIn(lm))
        lm_arrows = VGroup(*(pointer(lm.row(n), t.title, bend=-0.3) for n, t in
                             zip(["DT_JMPREL", "DT_SYMTAB", "DT_STRTAB"], [jm, sy, st])))
        self.play(FadeIn(tables, lag_ratio=0.2), LaggedStartMap(GrowArrow, lm_arrows, lag_ratio=0.2))
        self.say("The resolver gets link_map and a reloc index. link_map says where the three tables live.")
        self.beat()

        f1 = mono("JMPREL + reloc_index", 17, T.attacker_bytes)
        f2 = mono("SYMTAB + (r_info>>8)*16", 17, T.attacker_bytes)
        f3 = mono("STRTAB + st_name", 17, T.attacker_bytes)
        legit = VGroup(
            Arrow(jm.row("gets").get_right(), sy.row("gets").get_right(), path_arc=-1.2, buff=0.05),
            Arrow(sy.row("gets").get_right(), st.row('"gets\\0puts\\0"').get_right(), path_arc=-1.2, buff=0.05),
        ).set_color(T.pointer)
        self.play(lm_arrows.animate.set_opacity(0.25), Indicate(jm.row("gets")))
        self.play(ShowCreation(legit[0]))
        self.play(ShowCreation(legit[1]))
        self.say("Index picks an Elf32_Rel. r_info >> 8 picks a symbol. st_name picks a string.")
        self.beat()

        self.play(FadeIn(fk, shift=LEFT * 0.2), legit.animate.set_opacity(0.2))
        forged = VGroup(
            Arrow(jm.body.get_right(), fk.row("Elf32_Rel").get_left(), path_arc=-0.3, buff=0.08),
            Arrow(sy.body.get_right(), fk.row("Elf32_Sym").get_left(), path_arc=0.2, buff=0.08),
            Arrow(st.body.get_right(), fk.row("string").get_left(), path_arc=0.4, buff=0.08),
        ).set_color(T.attacker_bytes)
        # the address math, listed under the forged block instead of on the
        # arrows, where it collided with everything
        fs = VGroup(f1, f2, f3).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        fs.next_to(fk, DOWN, buff=0.35).align_to(fk, LEFT)
        for arr, f in zip(forged, fs):
            self.play(ShowCreation(arr), FadeIn(f, shift=RIGHT * 0.1), run_time=0.8)
        self.say("A huge index runs off the end of JMPREL into your bytes. Each forged field reaches the next.")
        self.beat()
        got = box_label("GOT slot = system", "attacker_bytes", 18).next_to(fs, DOWN, buff=0.3).align_to(fk, LEFT)
        self.play(FadeIn(got, shift=UP * 0.1))
        self.say("The resolver writes system into the GOT slot from r_offset and calls it.")
        self.beat()
        self.bridge()


class Adv93(ModelNote, StackAdv):
    trace_name = "adv-93"
    write_pattern = "gets(buf"
    takeaway = "Any I/O call on a corrupted FILE is an indirect call you control."

    def intro_caption(self):
        self.say("Every FILE carries a pointer to a table of I/O functions.")

    def concept(self):
        tr = self.tr
        rows = []
        for l in tr.source:
            # pull the field list straight out of VRIG's struct listing
            if "// +0x" in l:
                left, off = l.split("//")
                name = left.strip().rstrip(";").split()[-1].lstrip("*")
                rows.append((off.strip().split()[0], name, ""))
        vt_i = next(i for i, r in enumerate(rows) if r[1] == "__vtable")
        rows.insert(vt_i, ("", "...", ""))
        rows[-1] = (rows[-1][0], "__vtable", "&_IO_file_jumps")
        fp = StructView("_IO_FILE *fp", rows, width=4.6, size=15).move_to(LEFT * 4.2 + DOWN * 0.1)
        if fp.get_height() > 5.8:
            fp.set_height(5.8)
        jumps = StructView("_IO_file_jumps", [("", "__finish", "real"), ("", "__overflow", "real"),
                                              ("", "__underflow", "real")], width=3.4).move_to(RIGHT * 1.3 + UP * 1.6)
        fake = StructView("fake vtable", [("", "__finish", h32(tr.symbols["win"])), ("", "__overflow", "..."),
                                          ("", "__underflow", "...")],
                          role="attacker_bytes", width=3.4).move_to(RIGHT * 1.3 + DOWN * 1.5)
        self.play(FadeIn(fp, lag_ratio=0.03))
        a = pointer(fp.row("__vtable"), jumps.row("__finish"), bend=0.6)
        self.play(FadeIn(jumps), GrowArrow(a))
        self.say("__vtable sits at +0x94. fclose(fp) calls fp->__vtable->__finish(fp).")
        self.beat()
        self.play(FadeIn(fake, shift=UP * 0.2))
        self.play(*fp.set("__vtable", "&fake"))
        b = pointer(fp.row("__vtable"), fake.row("__finish"), role="attacker_bytes", bend=-0.3)
        winb = box_label("win()", "win", 20).next_to(fake.row("__finish"), RIGHT, buff=0.7)
        self.play(ReplacementTransform(a, b), jumps.animate.set_opacity(0.3))
        self.play(GrowArrow(Arrow(fake.row("__finish").get_right(), winb.get_left(), buff=0.08).set_color(T.win)),
                  FadeIn(winb))
        self.say("Corrupt __vtable and fclose() calls whatever your fake table holds.")
        self.beat()
        gate = box_label("IO_validate_vtable\n  glibc 2.24+", "mitigation", 17).move_to(RIGHT * 5.0 + UP * 0.15)
        self.play(FadeIn(gate, shift=UP * 0.1))
        self.say("Newer glibc checks that vtables live in __libc_IO_vtables. _IO_str_jumps lives there and gets you past.")
        self.beat()
        self.bridge()


class Adv94(ModelNote, StackAdv):
    trace_name = "adv-94"
    takeaway = "FSOP turns one pointer write into a call when the process aborts."

    def intro_caption(self):
        self.say("glibc keeps every open FILE on one linked list, and flushes them all on abort.")

    def concept(self):
        tr = self.tr
        head = box_label("_IO_list_all", "pointer", 20).move_to(LEFT * 5.5 + UP * 2.0)
        files = VGroup(*(box_label(n, "label", 18) for n in ("stderr", "stdout", "stdin")))
        files.arrange(RIGHT, buff=1.1).move_to(RIGHT * 1.0 + UP * 2.0)
        chain = VGroup(Arrow(head.get_right(), files[0].get_left(), buff=0.1),
                       *(Arrow(a.get_right(), b.get_left(), buff=0.1) for a, b in zip(files, files[1:])))
        chain.set_color(T.pointer)
        chain_lab = mono("_chain", 15, T.text_dim).next_to(chain[1], UP, buff=0.08)
        self.play(FadeIn(head), LaggedStartMap(FadeIn, files, lag_ratio=0.2), LaggedStartMap(GrowArrow, chain),
                  FadeIn(chain_lab))
        self.say("_IO_list_all points at the first FILE. Each FILE's _chain points at the next.")
        self.beat()

        fake = StructView("fake FILE", [("", "_flags", "0x0"), ("", "_IO_write_base", "0x0"),
                                        ("", "_IO_write_ptr", "0x1"), ("", "_mode", "0x0"),
                                        ("", "__vtable", "&fake_vtable")],
                          role="attacker_bytes", width=4.2, size=17).move_to(LEFT * 3.4 + DOWN * 0.5)
        fvt = StructView("fake_vtable", [("", "__overflow", h32(tr.symbols["win"]))], role="attacker_bytes",
                         width=3.6, size=17).move_to(RIGHT * 2.2 + UP * 0.3)
        self.play(FadeIn(fake, shift=UP * 0.2), FadeIn(fvt, shift=UP * 0.2))
        vp = pointer(fake.row("__vtable"), fvt.row("__overflow"), role="attacker_bytes", bend=0.4)
        self.play(GrowArrow(vp))
        self.say("An unsorted bin attack overwrites _IO_list_all with the address of a fake FILE.")
        redirect = Arrow(head.get_bottom(), fake.title.get_top(), buff=0.1, path_arc=0.4).set_color(T.attacker_bytes)
        self.play(chain[0].animate.set_opacity(0.2), files.animate.set_opacity(0.3), chain[1:].animate.set_opacity(0.2),
                  GrowArrow(redirect))
        self.beat()

        self.say("A bad malloc aborts. _IO_flush_all_lockp walks the list from the fake FILE.")
        marker = SurroundingRectangle(fake, buff=0.1).set_stroke(T.highlight, 3)
        self.play(ShowCreation(marker))
        checks = VGroup(mono("_mode <= 0", 18, T.mitigation), mono("write_ptr > write_base", 18, T.mitigation))
        checks.arrange(DOWN, aligned_edge=LEFT, buff=0.15).next_to(fvt, DOWN, buff=0.7).align_to(fvt, LEFT)
        for c, row in zip(checks, ("_mode", "_IO_write_ptr")):
            self.play(Indicate(fake.row(row)[2], color=T.mitigation), FadeIn(c, shift=RIGHT * 0.1), run_time=0.7)
        winb = box_label("win()", "win", 20).next_to(fvt, RIGHT, buff=0.6)
        self.play(GrowArrow(Arrow(fvt.row("__overflow").get_right(), winb.get_left(), buff=0.08).set_color(T.win)),
                  FadeIn(winb))
        self.say("Both checks pass, so it calls __overflow through the fake vtable. That's win().")
        self.beat()
        self.bridge()


# ===========================================================================
# unit17: data-only
# ===========================================================================

class Adv2_101(StackAdv):
    trace_name = "adv2-101"
    frame_names = {"saved_fp": "isAdmin", "saved_fp_role": "local_var"}
    takeaway = "Control-flow defenses guard code pointers. isAdmin is plain data."

    def intro_caption(self):
        self.say("VRIG lists every control-flow defense as on. The target here isn't control flow.")

    def make_view(self):
        view = super().make_view()
        # StackSim seeds this slot with a saved ebp. The source says isAdmin
        # lives here and starts at 0, so show 0 until the overflow writes it.
        for c in view.at(self.tr.ebp_off).cells:
            c.label.become(c.relabel(0))
        return view

    def frame_act(self):
        self.frame_caption = "isAdmin sits right above buf, at offset 16. It starts at zero."
        super().frame_act()

    def after_write(self, off):
        if off == self.tr.ebp_off:
            self.say(f"Byte sixteen lands in isAdmin. Now it's {self.tr.word_at(off)}.", run_time=0.5)

    def return_act(self):
        tr, view = self.tr, self.view
        self.focus("if (isAdmin)")
        val, anims = le_assemble(view.at(tr.ebp_off))
        val.next_to(view.tags[-2], RIGHT, buff=0.3)
        self.play(*anims)
        self.say("if (isAdmin) sees a nonzero value and calls win().")
        self.focus("win();")
        self.beat()
        self.play(FadeOut(val))
        self.focus_close()
        meaning = self.read_ret()
        ret_log = tr.steps[-1]["logs"][-1]["msg"].lstrip("→ ").split(" —")[0]
        self.say(f"The return address never changed. VRIG reports a {ret_log.lower()}.")
        self.beat()
        guards = protection_row([p for p in tr.raw["protections"] if p["status"] == "active"], size=17)
        guards.next_to(self.strip, DOWN, buff=0.5).align_to(self.strip, LEFT)
        self.play(LaggedStartMap(FadeIn, guards, shift=UP * 0.1, lag_ratio=0.2))
        self.say("None of these defenses watch an int on the stack, so none of them fire.")
        self.beat()
        chk = box_label(f"check  inputLen {tr.raw['inputLen']} > bufSize {tr.buf_size}", "win", 20)
        chk.next_to(guards, DOWN, buff=0.4).align_to(self.strip, LEFT)
        assert tr.raw["check"]["result"]
        self.play(FadeIn(chk, shift=DOWN * 0.1))
        self.say("VRIG's check only asks that the input spill past buf. It does.")
        self.beat()
        self.play(FadeOut(meaning), FadeOut(chk), FadeOut(guards))


# ===========================================================================
# unit18: kernel stack overflow, ret2usr across the boundary
# ===========================================================================

class Kern104(StackAdv):
    trace_name = "kern-104"
    src_from = "static long vuln_ioctl"
    src_extra = ()
    write_pattern = "copy_from_user"
    takeaway = "Without SMEP, ring 0 runs user pages. One overwrite crosses the boundary."

    def intro_caption(self):
        self.say("Same bug as userland, inside an ioctl handler. The prize is root.")

    def ksym(self, name: str) -> int:
        line = next(l for l in self.tr.source if f"// {name}:" in l)
        return int(line.split("0x")[1].split()[0], 16)

    def pick_source(self):
        src = self.tr.source
        a = next(i for i, l in enumerate(src) if l.startswith(self.src_from))
        end = next(i for i in range(a, len(src)) if src[i].strip() == "}")
        return [(i, src[i]) for i in range(a, end + 1) if "//" not in src[i]]

    def make_view(self):
        # 64 byte kbuf: keep the top row of it, fold the rest
        return FrameView(self.tr, self.tr.step_index("Make room"), start=self.tr.buf_size - self.w,
                         show_addr=False, offset_labels=True)

    def frame_act(self):
        self.frame_names = {"buffer": "kbuf[64]"}
        self.frame_caption = "Above kbuf sit saved ebp and the return address into the syscall path."
        super().frame_act()

    def overflow_act(self):
        self.overflow_caption = f"copy_from_user copies 256 bytes into 64. VRIG's frame takes {len(self.tr.payload)}."
        super().overflow_act()

    def return_act(self):
        tr, view, frame = self.tr, self.view, self.frame
        self.focus("return 0")
        meaning = self.read_ret()
        self.say(f"ret will pop {h32(tr.raw['retAfter'])}. That is win(), and it lives in user space.")
        self.beat()
        self.play(FadeOut(meaning), FadeOut(self.code), FadeOut(self.strip), FadeOut(self.title))
        self.unsay()

        # floor: user half low, kernel half high, split at 0xc0000000
        view.tags.set_opacity(0)
        self.play(view.animate.scale(1 / self.view_scale).move_to(LEFT * 3.2 + UP * 1.9))
        kern = Rectangle(12.0, 3.8).set_stroke(T.kernel_space, 2).set_fill(T.kernel_space, 0.12).move_to(UP * 1.9)
        user = Rectangle(12.0, 3.8).set_stroke(T.user_space, 2).set_fill(T.user_space, 0.18).move_to(DOWN * 1.9)
        for r in (kern, user):
            r.shift(IN * 0.02)
        split = DashedLine(LEFT * 6.0, RIGHT * 6.0).set_stroke(T.text_dim, 2)
        self.play(FadeIn(kern), FadeIn(user), ShowCreation(split), view.tags.animate.set_opacity(1))
        self.play(frame.animate.reorient(-6, 40, 0, center=(0.3, -0.7, 0.0), height=10.6), run_time=2.2)
        self.tilted = True

        kl = billboard(mono("kernel  ring 0", 22, T.kernel_space).move_to(LEFT * 4.3 + UP * 0.45), frame)
        ul = billboard(mono("user  ring 3", 22, T.user_space).move_to(LEFT * 4.3 + DOWN * 0.45), frame)
        sl = billboard(mono("0xc0000000", 18, T.text_dim).move_to(RIGHT * 4.8 + UP * 0.25), frame)

        prep, commit = self.ksym("prepare_kernel_cred"), self.ksym("commit_creds")
        # slabs in their own region's color vanish into the floor
        win_blk = on_floor(CodeBlock("win()", tr.symbols["win"], "text_section", frame), RIGHT * 0.8 + DOWN * 2.0)
        prep_blk = on_floor(CodeBlock("prepare_kernel_cred", prep, "text_section", frame, width=3.4), RIGHT * 2.9 + UP * 2.8)
        com_blk = on_floor(CodeBlock("commit_creds", commit, "text_section", frame, width=3.4), RIGHT * 2.9 + UP * 1.1)
        self.play(FadeIn(kl), FadeIn(ul), FadeIn(sl), FadeIn(win_blk, shift=OUT * 0.4),
                  FadeIn(prep_blk, shift=OUT * 0.4), FadeIn(com_blk, shift=OUT * 0.4))
        self.say("Kernel above the line, user below. The overwritten slot points down.")
        self.beat()

        down = arc3d(view.at(tr.ret_off).cells.get_right(), win_blk.top(), lift=2.6, color=T.attacker_bytes)
        self.play(ShowCreation(down), run_time=1.4)
        self.play(win_blk.slab.animate.set_color(T.win))
        self.say("SMEP is off, so the CPU runs that user page with ring 0 privileges.")
        self.beat()

        up1 = arc3d(win_blk.top(), prep_blk.top(), lift=1.6, color=T.win)
        up2 = arc3d(prep_blk.top(), com_blk.top(), lift=0.9, color=T.win)
        self.play(ShowCreation(up1), run_time=1.0)
        self.play(ShowCreation(up2), run_time=0.8)
        root = billboard(box_label("uid=0", "win", 26).move_to(RIGHT * 5.4 + UP * 1.1 + OUT * 0.6), frame)
        self.play(FadeIn(root, scale=1.3), com_blk.slab.animate.set_color(T.win))
        self.say("In a real exploit that user code calls commit_creds(prepare_kernel_cred(0)) and returns as root.")
        self.beat()

        alt = tr.raw["alt"]
        assert not alt["stepWin"]
        self.say(f"Aim straight at commit_creds, {h32(alt['target'])}, and VRIG calls it a crash. Its check wants win().")
        self.beat()


# ---------------------------------------------------------------------------
# one class per exercise id, for the render loop
SCENES = {
    "ctf-47": Ctf47, "ctf-49": Ctf49, "ctf-50": Ctf50, "ctf-52": Ctf52, "mit-81": Mit81,
    "adv-88": Adv88, "adv-89": Adv89, "adv-92": Adv92, "adv-93": Adv93, "adv-94": Adv94,
    "adv2-101": Adv2_101, "kern-104": Kern104,
}
