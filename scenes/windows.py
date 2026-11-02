"""
Units 8 and 9: Windows stack and Windows heap. One scene per VRIG exercise,
all reading traces from tools/vrig-trace/windows-entry.ts.

    manimgl scenes/windows.py Win37 -w -l        # quick look
    manimgl scenes/windows.py Win43 -p           # presenter

Stack scenes share WinStack (frame, gets() writes, ret). Heap scenes share
WinHeap (chunks, ListHints, the call). Per-exercise classes add the beat that
exercise is about: SEH records, the /GS cookie, CFG's slot table, LFH.
"""
from manimlib import *

from vrig.mob.cpu import CodeListing, RegisterFile
from vrig.mob.memory import CELL, LIFT, PayloadStrip, StackView, le_assemble, mono, prose
from vrig.mob.space import arc3d, billboard
from vrig.mob.windows import (CfgStrip, HeapColumn, HeapTrace, LfhGrid, SehRecord, Slab, WinStackTrace,
                              ptr_arrow, side_tag, source_lines)
from vrig.scene import Vrig3DScene
from vrig.theme import T
from vrig.trace import h32


def find(lines: list[str], needle: str) -> int:
    return next(i for i, l in enumerate(lines) if needle in l)


def end_card(scene, title: str, msg: str):
    """Last beat: VRIG's own win title and message."""
    scene.unsay()
    keep = getattr(scene, "title", None)
    scene.play(*[FadeOut(m) for m in scene.mobjects if m is not keep and m is not scene.frame])
    head = prose(title, 40, T.win)
    body = prose("\n".join(textwrap_lines(msg, 58)), 24, T.text)
    card = VGroup(head, body).arrange(DOWN, buff=0.35)
    plate = BackgroundRectangle(card, buff=0.35).set_fill(T.background, 0.92).shift(IN * 0.01)
    grp = VGroup(plate, card).move_to(ORIGIN).fix_in_frame()
    scene.play(FadeIn(grp, shift=UP * 0.2))
    scene.beat(pause=3.5)


def textwrap_lines(s: str, w: int) -> list[str]:
    import textwrap
    return textwrap.wrap(s, w)


# ═══ stack ═══════════════════════════════════════════════════════════════

class WinStack(Vrig3DScene):
    trace_name = ""
    subtitle = ""
    code_size = 16

    def construct(self):
        tr = WinStackTrace.load(self.trace_name)
        assert tr.solved, f"{tr.id}: VRIG doesn't call this payload a win, re-export"
        self.tr = tr
        self.frame.reorient(0, 0)
        self.open()
        self.lay_out()
        self.before_overflow()
        self.overflow(self.tr.steps, self.tr.payload)
        self.after_overflow()
        self.ret_to_win()
        self.after_win()
        end_card(self, tr.win_title, tr.win_msg)

    # -- pieces --------------------------------------------------------------

    def open(self):
        title = prose(self.tr.title, 46).to_edge(UP, buff=0.4)
        sub = prose(self.subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.25)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.55).to_corner(UL, buff=0.25))
        title.fix_in_frame()  # survives the 3d acts
        self.title = title

    def regions(self) -> list[tuple[int, int, str, str]]:
        """(offset, n_words, name, role) for the bracket tags. Default: VRIG's own frame."""
        t = self.tr
        out = [(0, t.buf_size // t.word, f"buf[{t.buf_size}]", "buffer")]
        if t.canary_size:
            out.append((t.buf_size, 1, "/GS cookie", "canary"))
        out += [(t.ebp_off, 1, "saved ebp", "saved_fp"), (t.ret_off, 1, "return addr", "saved_ret")]
        return out

    def lay_out(self):
        tr = self.tr
        self.src, self.where = source_lines(tr.source)
        code = CodeListing(self.src, size=self.code_size).to_corner(UL, buff=0.5).shift(DOWN * 0.4)
        stack = StackView(tr).shift(RIGHT * 2.1 + UP * 0.35)
        tags = VGroup(*(stack.region_tag(off, name, role, n) for off, n, name, role in self.regions()))
        self.play(FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.25))
        self.code, self.stack, self.tags = code, stack, tags
        self.beat()

    def before_overflow(self):
        pass

    def after_overflow(self):
        pass

    def after_win(self):
        pass

    def overflow(self, steps, payload, fast=False, caption=True):
        tr, stack, code = self.tr, self.stack, self.code
        self.play(code.focus(find(self.src, "gets(")))
        if caption:
            self.say(f"gets() copies all {len(payload)} bytes. buf only holds {tr.buf_size}.")
        strip = PayloadStrip(payload, per_row=16)
        strip.set_width(min(strip.get_width(), 4.6))
        strip.next_to(code, DOWN, buff=0.35, aligned_edge=LEFT)
        lab = mono("input", 15, T.text_dim).next_to(strip, UP, buff=0.1, aligned_edge=LEFT)
        self.play(FadeIn(lab), FadeIn(strip, lag_ratio=0.02, run_time=0.9))

        w = tr.word
        for step in steps:
            if not step["label"].startswith("gets(): write"):
                continue
            off = step["hl"][0]
            data = step["memory"][off:off + w]
            src_cells = strip.cells[off:off + w]
            over = off >= tr.buf_size
            self.play(*[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, stack.at(off).cells)],
                      src_cells.animate.set_opacity(0.2),
                      run_time=0.25 if fast else (0.35 if not over else 0.55))
            self.play(*stack.write_word(off, data, "attacker_bytes", overflow=over), run_time=0.25)
            if caption and not fast:
                self.on_word(off)
        self.play(FadeOut(strip), FadeOut(lab))

    def on_word(self, off: int):
        tr = self.tr
        if off == tr.ebp_off:
            self.say("Past the end of buf. Saved ebp is next.", run_time=0.5)
        elif off == tr.ret_off:
            self.say("Then the return address.", run_time=0.5)
            self.beat(pause=0.4)

    def ret_to_win(self):
        tr, stack, code = self.tr, self.stack, self.code
        ret_step = next(s for s in tr.steps if s["label"].startswith("Return"))
        word = stack.at(tr.ret_off)
        value, anims = le_assemble(word, T.win)
        value.next_to(self.tags, RIGHT, buff=0.3).match_y(word)
        # not ret_step["srcLine"]: VRIG's findVulnClose reads "__stdcall" as the
        # function name on win-37 and points at win()'s brace instead
        start = find(self.src, "vuln() {")
        self.play(code.focus(next(i for i in range(start, len(self.src)) if self.src[i].strip() == "}")))
        self.play(*anims, run_time=0.7)
        name = mono("win()", 18, T.win).next_to(value, DOWN, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(name, shift=UP * 0.1), word.boxes().animate.set_fill(T.win, 0.85))
        got = int(ret_step["logs"][-1]["msg"].split("0x")[1][:8], 16)
        assert got == tr.symbols["win"] == word.value()
        self.say(f"ret pops {h32(got)} into eip. That's win().")
        win_line = find(self.src, "win()")
        self.play(code.focus(win_line))
        jump = next(s for s in tr.steps if s["win"])
        assert "win()" in jump["logs"][-1]["msg"]
        self.play(Flash(code.lines[win_line].get_left() + RIGHT * 0.2, color=T.win, flash_radius=0.4))
        self.ret_value = VGroup(value, name)
        self.beat()


class Win37(WinStack):
    trace_name = "win-37"
    subtitle = "WinAPI functions use stdcall. The callee cleans the stack."

    def before_overflow(self):
        # two ways to clean up after a call. concept card, no exercise numbers in it
        cd = VGroup(mono("cdecl", 18, T.label), mono("call f", 16), mono("add esp, N", 16, T.highlight),
                    mono("caller pops args", 14, T.text_dim)).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        sc = VGroup(mono("__stdcall", 18, T.label), mono("call f", 16), mono("f: ... ret N", 16, T.highlight),
                    mono("callee pops args", 14, T.text_dim)).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        cards = VGroup(cd, sc).arrange(RIGHT, buff=0.7)
        plate = SurroundingRectangle(cards, buff=0.3).set_stroke(T.grid, 1.5).set_fill(T.background, 0.95)
        plate.shift(IN * 0.01)
        card = VGroup(plate, cards).move_to(LEFT * 3.2 + DOWN * 0.2)
        self.play(FadeIn(card, shift=UP * 0.2))
        self.say("Only the cleanup moves. ret N pops the return address, then N more bytes of arguments.")
        self.beat()
        self.say("vuln() takes no arguments, so its frame is the same as before. buf, saved ebp, return address.")
        self.beat()
        self.play(FadeOut(card))


class Win38(WinStack):
    trace_name = "win-38"
    subtitle = "Same bug in a PE as in an ELF. The buffer is 20 bytes this time."

    def before_overflow(self):
        t = self.tr
        math = mono(f"{t.buf_size} buf  +  {t.ebp_off - t.buf_size} ebp  =  {t.ret_off} bytes of padding", 20,
                    T.highlight)
        math.next_to(self.stack, UP, buff=0.3)
        self.play(FadeIn(math, shift=DOWN * 0.1))
        self.say(f"A bigger buffer only moves the return address up. It now starts {t.ret_off} bytes in.")
        self.beat()
        self.play(FadeOut(math))


class Win39(WinStack):
    trace_name = "win-39"
    subtitle = "Exception handler records live on the stack, right in the overflow's path."
    code_size = 15

    def regions(self):
        t = self.tr
        seh = t.raw["sehRecord"]
        rest = (t.buf_size - seh["handlerOff"] - 4) // t.word
        return [(0, 2, "buf[8]", "buffer"), (seh["nsehOff"], 1, "nSEH", "saved_fp"),
                (seh["handlerOff"], 1, "handler", "saved_ret"),
                (seh["handlerOff"] + 4, rest, "rest of frame", "buffer"),
                (t.ebp_off, 1, "saved ebp", "saved_fp"), (t.ret_off, 1, "return addr", "saved_ret")]

    def before_overflow(self):
        tr, stack = self.tr, self.stack
        seh = tr.raw["sehRecord"]
        self.say("Each function with a handler pushes a record. Next points to the caller's record, Handler to code.")
        teb = mono("fs:[0]", 18, T.label).next_to(stack.at(seh["nsehOff"]).addr_label, LEFT, buff=0.6)
        a0 = ptr_arrow(teb.get_right(), stack.at(seh["nsehOff"]).addr_label.get_left(), "label")
        # the caller's records aren't in VRIG's frame, so they get names, not addresses
        outer = SehRecord("main's record", "next", "handler", w=1.6)
        final = SehRecord("ntdll's last record", "0xffffffff", "final", w=1.6)
        chain = VGroup(outer, final).arrange(UP, buff=0.7).move_to(LEFT * 3.6 + UP * 1.2)
        n_word = stack.at(seh["nsehOff"])
        a1 = ptr_arrow(n_word.addr_label.get_top(), outer.next.get_bottom(), "saved_fp", path_arc=30 * DEG)
        a2 = ptr_arrow(outer.next.get_top(), final.next.get_bottom(), "saved_fp")
        self.play(FadeOut(self.code), FadeIn(teb), GrowArrow(a0))
        self.play(GrowArrow(a1), FadeIn(outer, shift=DOWN * 0.1))
        self.play(GrowArrow(a2), FadeIn(final, shift=DOWN * 0.1))
        self.say("The dispatcher walks this list from fs:[0] when something faults.")
        self.beat()
        self.chain = VGroup(teb, a0, a1, a2, outer, final)
        self.play(FadeOut(self.chain), FadeIn(self.code))

    def on_word(self, off):
        seh = self.tr.raw["sehRecord"]
        if off == seh["nsehOff"]:
            self.say("Byte 8 lands on nSEH. The record gets overwritten on the way up.", run_time=0.5)
        elif off == seh["handlerOff"]:
            self.say("Handler goes next. Nothing faults here, so nobody reads it yet.", run_time=0.5)
        else:
            super().on_word(off)

    def after_overflow(self):
        tr = self.tr
        seh = tr.raw["sehRecord"]
        vals = VGroup()
        for off in (seh["nsehOff"], seh["handlerOff"]):
            v, anims = le_assemble(self.stack.at(off), T.attacker_bytes)
            v.next_to(self.tags, RIGHT, buff=0.3).match_y(self.stack.at(off))
            self.play(*anims, run_time=0.5)
            vals.add(v)
        junk = self.stack.at(seh["handlerOff"]).value()
        assert junk == self.stack.at(seh["nsehOff"]).value()
        self.say(f"nSEH and Handler both read {h32(junk)} now. A fault would send the dispatcher there.")
        self.beat()
        hint = tr.raw["descRetDistance"]
        bad = tr.attempts["descHint"]
        assert not bad["stepWin"] and not bad["check"]
        self.say(f"The hint says {hint} bytes to the return address. VRIG's frame has {tr.ret_off}, "
                 f"and {hint} bytes of padding leaves ret at {h32(bad['retAddr'])}.")
        self.beat()
        self.play(FadeOut(vals))


class Win40(WinStack):
    trace_name = "win-40"
    subtitle = "Overflow inside __try, then make the exception work for you."
    code_size = 15

    def after_win(self):
        # the real technique. VRIG's sim stops at ret, so this part is the
        # mechanism, checked against VRIG's x86 emulator, with roles for labels
        tr = self.tr
        ppr = tr.raw["ppr"]
        assert ppr["landsOnRecord"] and ppr["jumpsPastHandler"]
        self.say("VRIG stops at the return address. A real SEH exploit never needs it.")
        self.beat()
        self.play(*map(FadeOut, [self.code, self.stack, self.tags, self.ret_value]))
        self.unsay()
        self.seh_dispatch(ppr)

    def seh_dispatch(self, ppr):
        frame = self.frame
        # the frame from the source comments: buf, then the record, then shellcode
        rows = [("buf", "padding", "attacker_bytes"), ("nSEH", "eb 06 90 90", "saved_fp"),
                ("Handler", "&pop pop ret", "saved_ret"), ("shellcode", "...", "attacker_bytes")]
        col = Group()
        for name, val, role in rows:
            col.add(Slab(val, role, width=2.4, depth=0.7, size=22, sub=name))
        col.arrange(UP, buff=0.45).move_to(LEFT * 2.6 + UP * 0.9)
        self.play(frame.animate.reorient(-20, 48, 0, center=(0.6, -0.2, 0.6), height=9.0), run_time=2)
        for s in col:
            s.stand(frame, 0.7)
        self.play(LaggedStart(*(FadeIn(s, shift=OUT * 0.4) for s in col), lag_ratio=0.15))
        self.say("Overwrite the record, not the return address. nSEH gets a short jump. Handler gets a pop pop ret.")
        self.beat()

        gadget = Slab("pop esi / pop edi / ret", "gadget", width=3.6, depth=0.9, size=24,
                      sub="module built without SafeSEH").move_to(RIGHT * 2.4 + UP * 2.6)
        gadget.stand(frame, 0.9)
        fault = mono("*(int*)0 = 0", 22, T.crash).to_corner(UR, buff=0.4).fix_in_frame()
        self.play(FadeIn(fault, shift=DOWN * 0.1), Flash(fault, color=T.crash))
        self.say("The null write faults. The dispatcher finds this record and calls its Handler.")
        jump1 = arc3d(col[2].top(), gadget.top(), lift=1.6, color=T.gadget)
        self.play(FadeIn(gadget, shift=OUT * 0.4), ShowCreation(jump1), run_time=1.2)
        self.beat()

        # the dispatcher's call frame, as the emulator ran it
        names = ["ret into ntdll", "ExceptionRecord", "EstablisherFrame", "ContextRecord"]
        cells = VGroup()
        for i, n in enumerate(names):
            box = Rectangle(3.0, 0.48).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1).shift(IN * 0.01)
            role = "saved_fp" if n == "EstablisherFrame" else "label"
            t = mono(f"esp+{4 * i:<2} {n}", 15, getattr(T, role)).move_to(box).shift(OUT * 0.01)
            cells.add(VGroup(box, t))
        cells.arrange(UP, buff=0.04).to_corner(DR, buff=0.5).shift(UP * 0.6).fix_in_frame()
        esp = mono("esp", 16, T.highlight).fix_in_frame()
        self.play(FadeIn(cells, lag_ratio=0.1))
        self.say("On entry, esp+8 holds EstablisherFrame. That's the address of nSEH.")
        esp.next_to(cells[0], LEFT, buff=0.15)
        self.play(FadeIn(esp))
        self.beat()

        tr = ppr["trace"]
        for k in range(2):
            d = tr[k]["esp"] - (tr[k - 1]["esp"] if k else ppr["esp0"])
            assert d == 4
            self.play(cells[k].animate.set_opacity(0.3), esp.animate.next_to(cells[k + 1], LEFT, buff=0.15),
                      run_time=0.5)
            self.say(f"{tr[k]['insn']} drops {d} bytes.", run_time=0.4)
        assert tr[2]["eip"] == ppr["recordAddr"]
        jump2 = arc3d(gadget.top(), col[1].top(), lift=1.6, color=T.highlight)
        self.play(cells[2][0].animate.set_stroke(T.highlight, 3), ShowCreation(jump2), run_time=1.2)
        self.say("ret pops EstablisherFrame into eip. Execution lands on nSEH, on the stack.")
        self.beat()
        assert tr[3]["eip"] == ppr["shellcode"]
        hop = arc3d(col[1].top(), col[3].top(), lift=0.9, color=T.attacker_bytes)
        self.play(ShowCreation(hop), col[3].body.animate.set_color(T.win), run_time=1.0)
        self.say("eb 06 jumps over the Handler field and into the shellcode.")
        self.beat()
        self.say("SafeSEH rejects handlers that aren't in a module's table. SEHOP checks the chain still ends at ntdll.")
        self.beat(pause=1.5)
        self.play(*map(FadeOut, [cells, esp, fault]))


class Win41(WinStack):
    trace_name = "win-41"
    subtitle = "/GS puts a cookie between buf and the saved registers."

    def before_overflow(self):
        tr, stack = self.tr, self.stack
        cw = stack.at(tr.buf_size)
        value, anims = le_assemble(cw, T.canary)
        value.next_to(self.tags, RIGHT, buff=0.3).match_y(cw)
        self.play(*anims)
        assert cw.value() == tr.canary
        self.say(f"The cookie is {h32(tr.canary)} this run. The epilogue checks it before ret.")
        self.beat()
        self.cookie_val = value

        # first try: no idea about the cookie
        naive = tr.attempts["noCookie"]
        assert naive["canaryFailed"] and not naive["stepWin"]
        self.say("First try: plain padding, straight through the cookie.")
        self.overflow(naive["steps"], naive["payload"], fast=True, caption=False)
        check = next(s for s in naive["steps"] if s["canaryFailed"])
        self.play(Indicate(cw.cells, color=T.crash), cw.boxes().animate.set_fill(T.crash, 0.85))
        assert "stack smashing detected" in check["logs"][0]["msg"]
        self.say("Cookie mismatch. The program aborts and ret never runs.")
        self.beat()

        # put the frame back the way VRIG resets it, then do it properly
        fresh = StackView(tr)
        fresh.words.move_to(stack.words)
        self.play(*[Transform(a, b) for a, b in zip(stack.words, fresh.words)])
        self.say("Leak the cookie, then write it back into its own slot.")
        self.beat()

    def on_word(self, off):
        if off == self.tr.buf_size:
            self.say(f"Bytes 16 to 19 carry the leaked cookie, so the check sees {h32(self.tr.canary)}.", run_time=0.5)
            self.beat(pause=0.3)
        else:
            super().on_word(off)

    def after_overflow(self):
        ok = next(s for s in self.tr.steps if s["label"].startswith("Check the tripwire"))
        assert ok["logs"][0]["cls"] == "success"
        cw = self.stack.at(self.tr.buf_size)
        self.play(cw.boxes().animate.set_fill(T.canary, 0.85), Indicate(cw.cells, color=T.win))
        self.say("Cookie intact. The check passes and ret goes ahead.")
        self.beat()
        self.play(FadeOut(self.cookie_val))


class Win42(WinStack):
    trace_name = "win-42"
    subtitle = "Control Flow Guard checks indirect calls. Returns are a different edge."

    def after_win(self):
        tr, frame = self.tr, self.frame
        cfg = tr.raw["cfg"]
        self.play(*map(FadeOut, [self.code, self.tags, self.ret_value]))
        self.play(self.stack.animate.shift(LEFT * 6.4 + DOWN * 1.0))
        self.unsay()
        strip = CfgStrip(cfg["slots"], tile=0.32).move_to(RIGHT * 2.4 + UP * 2.2)
        self.play(frame.animate.reorient(-10, 45, 0, center=(0.6, 0.8, 0.3), height=10.0), run_time=2)
        self.play(FadeIn(strip, lag_ratio=0.03))
        slots = cfg["slots"]
        labels = Group()
        for i, s in enumerate(slots):
            if s["fn"]:
                lab = billboard(mono(f"{s['fn']}()", 16, T.mitigation).move_to(strip.top(i) + OUT * 0.35 + DOWN * 0.1), frame)
                labels.add(lab)
        lo = billboard(mono(h32(slots[0]["addr"]), 14, T.text_dim).next_to(strip.tiles[0], DOWN, buff=0.15), frame)
        hi = billboard(mono(h32(slots[-1]["addr"]), 14, T.text_dim).next_to(strip.tiles[-1], DOWN, buff=0.15), frame)
        self.play(FadeIn(labels), FadeIn(lo), FadeIn(hi))
        self.say(f"CFG keeps one entry per 16 bytes of .text. Only slots where a function starts are valid call targets.")
        self.beat()

        probe = cfg["probe"]
        assert not probe["valid"] and probe["addr"] == tr.orig_ret
        call = mono(f"call [eax]   eax = {h32(probe['addr'])}", 20, T.label).to_corner(UR, buff=0.4).fix_in_frame()
        self.play(FadeIn(call))
        hit = arc3d(strip.top(0) + LEFT * 1.2 + OUT * 0.6, strip.top(probe["slot"]), lift=1.4, color=T.crash)
        self.play(ShowCreation(hit), run_time=1.0)
        self.play(strip.tiles[probe["slot"]].animate.set_fill(T.crash, 0.9),
                  Flash(strip.top(probe["slot"]), color=T.crash, flash_radius=0.4))
        self.say(f"An indirect call to {h32(probe['addr'])}, mid-main, hits an empty slot. CFG kills the process.")
        self.beat()

        ret_word = self.stack.at(tr.ret_off)
        jump = arc3d(ret_word.cells.get_right(), strip.top(cfg["retSlot"]) + OUT * 0.1, lift=3.0, color=T.win)
        self.play(FadeOut(call), FadeOut(hit), ShowCreation(jump), run_time=1.4)
        self.say("ret never asks. It pops whatever the stack says, and the overflow wrote win().")
        self.beat()
        self.say("Backward edges need something else, like CET's shadow stack.")
        frame.add_ambient_rotation(2 * DEG)
        self.wait(3)
        frame.clear_updaters()
        self.beat()


# ═══ heap ════════════════════════════════════════════════════════════════

class WinHeap(Vrig3DScene):
    """
    Chunks as 8-byte rows: one _HEAP_ENTRY row, then data rows. ListHints and
    the function pointer sit beside them. Every byte comes from a timeline
    snapshot in the trace.
    """
    trace_name = ""
    subtitle = ""
    fptr_name = "u->action"
    code_size = 15
    span_end = 24          # how much of the heap to draw, in bytes
    names = {}             # heap offset -> what the source calls that chunk

    def construct(self):
        tr = HeapTrace.load(self.trace_name)
        assert tr.solved, f"{tr.id}: VRIG doesn't call this a win, re-export"
        self.tr = tr
        self.frame.reorient(0, 0)
        self.open()
        self.lay_out()
        self.walk()
        self.write_payload()
        self.call()
        self.lfh_act()
        end_card(self, tr.win_title, tr.win_msg)

    def open(self):
        title = prose(self.tr.title, 46).to_edge(UP, buff=0.4)
        sub = prose(self.subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.25)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.55).to_corner(UL, buff=0.25))
        title.fix_in_frame()  # survives the 3d acts
        self.title = title

    def lay_out(self):
        tr = self.tr
        s0 = tr.timeline[0]
        self.src, self.where = source_lines(tr.source)
        code = CodeListing(self.src, size=self.code_size).to_corner(UL, buff=0.5).shift(DOWN * 0.4)
        col = HeapColumn(tr, s0, 0, self.span_end).move_to(RIGHT * 2.4 + UP * 0.2)
        self.code, self.col = code, col
        tags = VGroup()
        for c in s0["chunks"]:
            if c["addr"] >= self.span_end:
                continue
            tags.add(side_tag(col.rows_for(c["addr"], 8), "_HEAP_ENTRY", "chunk_header", size=14))
            tags.add(side_tag(col.rows_for(c["dataStart"], c["dataSize"]), self.names.get(c["addr"], "data"),
                              "chunk_user", size=14))
            self.play_paint(c)
        self.tags = tags
        self.play(FadeIn(code, shift=RIGHT * 0.3), FadeIn(col, lag_ratio=0.03))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.2))
        self.fptr = self.fptr_box(s0)
        self.play(FadeIn(self.fptr))
        self.beat()
        self.explain_header(s0)

    def play_paint(self, c):
        col = self.col
        for o in range(c["addr"], c["addr"] + 8):
            col.cell(o).paint("chunk_header")
        for o in range(c["dataStart"], c["dataStart"] + c["dataSize"]):
            col.cell(o).paint("chunk_user" if c["allocated"] else "freed_chunk")

    def fptr_box(self, snap) -> VGroup:
        name, ptr = next(iter(snap["funcPtrs"].items()))
        cur = ptr["current"]
        sym = next((k for k, v in self.tr.symbols.items() if v == cur), "?")
        t = VGroup(mono(self.fptr_name, 17, T.label), mono(f"{h32(cur)}  {sym}()", 17, T.text))
        t.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
        box = SurroundingRectangle(t, buff=0.18).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.95).shift(IN * 0.01)
        g = VGroup(box, t)
        g.next_to(self.col, UP, buff=0.35).align_to(self.col, RIGHT)
        return g

    def set_fptr(self, snap, role="win") -> list[Animation]:
        new = self.fptr_box(snap)
        new[1][1].set_color(getattr(T, role))
        return [Transform(self.fptr, new)]

    def explain_header(self, s0):
        tr = self.tr
        c = s0["chunks"][0]
        d = c["decoded"]
        assert c["headerOk"]
        self.say(f"Every chunk starts with an 8-byte _HEAP_ENTRY. It's XOR-encoded with a per-heap key, "
                 f"{h32(tr.key)} this run.")
        self.play(Indicate(self.col.rows_for(c["addr"], 8), color=T.highlight, scale_factor=1.03))
        self.beat()
        dec = mono(f"Size {d['sizeUnits']} x 8 = {d['sizeUnits'] * 8} bytes   Flags {d['flags']:#04x} busy", 16,
                   T.highlight)
        dec.next_to(self.col, DOWN, buff=0.3).align_to(self.col, RIGHT)
        assert d["sizeUnits"] * 8 == c["size"]
        self.play(FadeIn(dec, shift=UP * 0.1))
        self.say("Decoded, it gives the size in 8-byte units and the busy flag.")
        self.beat()
        self.play(FadeOut(dec))

    # free list panel
    def hints_panel(self, snap) -> VGroup:
        hints = snap["freeLists"]["listHints"]
        rows = VGroup()
        for k, lst in sorted(hints.items(), key=lambda kv: int(kv[0])):
            entries = "  ".join(h32(self.tr.addr(a)) for a in lst) or "empty"
            rows.add(mono(f"ListHints[{k}]  {entries}", 15, T.unsorted if lst else T.text_dim))
        if not rows:
            rows.add(mono("ListHints  empty", 15, T.text_dim))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
        box = SurroundingRectangle(rows, buff=0.15).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.95).shift(IN * 0.01)
        g = VGroup(box, rows)
        g.next_to(self.col, DOWN, buff=0.3).align_to(self.col, RIGHT)
        return g

    def show_hints(self, snap):
        new = self.hints_panel(snap)
        if getattr(self, "hints", None) is None:
            self.hints = new
            self.play(FadeIn(new, shift=UP * 0.1))
        else:
            self.play(FadeOut(self.hints), FadeIn(new))
            self.hints = new

    def to_snap(self, snap, off=0, n=None, role=None):
        n = self.span_end if n is None else n
        anims = self.col.morph(snap, off, n)
        if anims:
            self.play(*anims, run_time=0.6)

    def walk(self):
        """Guided steps that actually do something (free, malloc)."""
        tr = self.tr
        prev = tr.timeline[0]
        for snap in tr.timeline[1:]:
            if snap["label"] == "submit":
                break
            if snap.get("doFree"):
                self.on_free(prev, snap)
            elif snap.get("doMalloc"):
                self.on_malloc(prev, snap)
            prev = snap

    def on_free(self, prev, snap):
        pass

    def on_malloc(self, prev, snap):
        pass

    def write_payload(self):
        pass

    def call(self):
        pass

    def lfh_act(self):
        pass

    # shared beats ---------------------------------------------------------

    def free_beat(self, snap, line: str, caption: str):
        c = snap["chunks"][0]
        self.play(self.code.focus(find(self.src, line)))
        self.play(self.col.paint(c["dataStart"], c["dataSize"], "freed_chunk"))
        self.to_snap(snap)
        self.show_hints(snap)
        self.say(caption)
        self.beat()

    def flink_labels(self, snap, c) -> VGroup:
        fl = mono(f"Flink {h32(c['flink'])}", 14, T.unsorted)
        bl = mono(f"Blink {h32(c['blink'])}", 14, T.unsorted)
        g = VGroup(fl, bl).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
        g.next_to(self.col.row(c["dataStart"]).addr_label, LEFT, buff=0.3)
        return g

    def stream_bytes(self, payload, dest_off: int, label="input"):
        strip = PayloadStrip(payload, per_row=16)
        strip.set_width(min(strip.get_width(), 4.6))
        strip.next_to(self.code, DOWN, buff=0.35, aligned_edge=LEFT)
        lab = mono(label, 15, T.text_dim).next_to(strip, UP, buff=0.1, aligned_edge=LEFT)
        self.play(FadeIn(lab), FadeIn(strip, lag_ratio=0.02))
        final = self.tr.snap("submit")
        for k in range(0, len(payload), 4):
            src = strip.cells[k:k + 4]
            dst = self.col.span(dest_off + k, min(4, len(payload) - k))
            self.play(*[TransformFromCopy(s, d, path_arc=-20 * DEG) for s, d in zip(src, dst)],
                      src.animate.set_opacity(0.2), run_time=0.4)
            self.play(*self.col.morph(final, dest_off + k, len(dst)),
                      VGroup(*(c.box for c in dst)).animate.set_fill(T.attacker_bytes, 0.85), run_time=0.25)
            self.on_chunk_write(dest_off + k)
        self.play(FadeOut(strip), FadeOut(lab))

    def on_chunk_write(self, off):
        pass

    def call_beat(self, line: str, fptr_off: int):
        tr = self.tr
        final = tr.snap("submit")
        assert any("win()" in l["msg"] for l in final["logs"])
        self.play(self.code.focus(find(self.src, line)))
        word = self.col.row(fptr_off - fptr_off % 8)
        cells = self.col.span(fptr_off, 4)
        val = int.from_bytes(bytes(c.value for c in cells), "little")
        assert val == tr.symbols["win"]
        self.play(*self.set_fptr(final), Indicate(cells, color=T.win))
        self.say(f"The call reads {h32(val)} from the old object and jumps to win().")
        win_line = find(self.src, "win()")
        self.play(self.code.focus(win_line))
        self.play(Flash(self.code.lines[win_line].get_left() + RIGHT * 0.2, color=T.win, flash_radius=0.4))
        self.beat()

    # LFH -----------------------------------------------------------------

    def lfh_grid_act(self, lf: dict, caption_pick: str, show_spray=True):
        frame = self.frame
        self.play(*map(FadeOut, [m for m in self.mobjects if m not in (self.cap, self.title, self.frame)]))
        self.unsay()
        grid = LfhGrid(lf["nSlots"], cell=0.8).move_to(RIGHT * 0.8 + UP * 0.6)
        self.play(frame.animate.reorient(-12, 50, 0, center=(0.0, 0.2, 0.3), height=8.6), run_time=2)
        head = mono(f"UserBlocks for {lf['chunkBytes']}-byte chunks  ({lf['version']})", 22, T.label)
        head.to_corner(UR, buff=0.4).fix_in_frame()
        self.play(FadeIn(grid, lag_ratio=0.02), FadeIn(head))
        self.say(f"After {lf['threshold']} allocations of one size, the LFH takes over that size. "
                 f"It carves a subsegment of {lf['nSlots']} equal slots.")
        self.beat()
        self.say(caption_pick)
        for a in lf["lfhAllocs"]:
            self.play(grid.raise_slot(a["slot"]), Indicate(grid.tiles[a["slot"]], color=T.highlight), run_time=0.35)
        order = mono("picked  " + " ".join(str(a["slot"]) for a in lf["lfhAllocs"]), 18, T.highlight)
        order.next_to(head, DOWN, buff=0.2).align_to(head, RIGHT).fix_in_frame()
        self.play(FadeIn(order))
        self.beat()

        ru = lf["reuse"]
        v = ru["victimSlot"]
        self.play(grid.up[v].animate.set_color(T.crash))
        self.play(grid.drop_slot(v))
        self.say(f"Free the object in slot {v}, then allocate the same size again.")
        self.play(grid.raise_slot(ru["gotSlot"], "attacker_bytes"), run_time=0.6)
        rate = lf["reuseRate"]
        same = ru["gotSlot"] == v
        msg = (f"It came back in slot {ru['gotSlot']}. " if not same else f"Slot {v} again. ") + \
              f"Over {rate['trials']} runs, VRIG's heap handed back the freed slot {rate['hits']} times."
        self.say(msg)
        self.beat()
        self.grid, self.lfh_head, self.lfh_order = grid, head, order
        if show_spray:
            self.spray(grid, lf)

    def spray(self, grid, lf):
        sp = lf["spray"]
        assert sp["full"] and sp["reused"]
        self.say("Attackers take the dice away. Spray until every slot is busy, then free the one you want.")
        free = [i for i in range(lf["nSlots"]) if i not in grid.up]
        self.play(*[grid.raise_slot(i) for i in free], run_time=1.0)
        v = sp["victimSlot"]
        self.play(grid.up[v].animate.set_color(T.crash))
        self.play(grid.drop_slot(v))
        self.play(grid.raise_slot(v, "attacker_bytes"), Flash(grid.top(v), color=T.attacker_bytes))
        self.say(f"Only slot {v} is free, so the next allocation has to land there.")
        self.beat()
        self.frame.add_ambient_rotation(2 * DEG)
        self.wait(2.5)
        self.frame.clear_updaters()


class Win43(WinHeap):
    trace_name = "win-43"
    subtitle = "Free an object, allocate the same size, and you get its memory back."
    names = {0: "User"}

    def on_free(self, prev, snap):
        c = snap["chunks"][0]
        assert snap["freeLists"]["listHints"]["3"] == [c["addr"]]
        self.free_beat(snap, "HeapFree", "HeapFree puts the chunk on ListHints for its size. Flink and Blink overwrite "
                                         "the first 8 bytes, but u still points here.")
        self.links = self.flink_labels(snap, c)
        self.play(FadeIn(self.links))
        self.beat()

    def on_malloc(self, prev, snap):
        c = snap["chunks"][0]
        assert snap["names"]["Note"] == snap["names"]["User"]
        self.play(self.code.focus(find(self.src, "char *note")))
        self.play(self.col.paint(c["dataStart"], c["dataSize"], "chunk_user"), FadeOut(self.links))
        self.show_hints(snap)
        note = mono("note == u", 17, T.highlight).next_to(self.col, LEFT, buff=0.5).shift(DOWN * 0.3)
        self.play(FadeIn(note, shift=RIGHT * 0.1))
        self.say(f"Same size asks the same list. HeapAlloc returns {h32(self.tr.addr(c['addr']))} again.")
        self.beat()
        self.note = note
        self.say("LFH isn't on for this size yet. VRIG's heap serves it from the back-end list.")
        self.beat()

    def write_payload(self):
        tr = self.tr
        self.play(self.code.focus(find(self.src, "read(")))
        self.say("read() fills the note. Its first 4 bytes are where u->action used to be.")
        c = tr.snap("submit")["chunks"][0]
        self.stream_bytes(tr.payload, c["dataStart"])

    def call(self):
        self.call_beat("u->action()", self.tr.snap("submit")["chunks"][0]["dataStart"])

    def lfh_act(self):
        lf = self.tr.lfh
        self.lfh_grid_act(lf, "On Windows 8 and later, each allocation starts its scan at a random slot.")


class Win44(WinHeap):
    trace_name = "win-44"
    subtitle = "Two neighbors on the heap. Write past the first into the second."
    fptr_name = "b->handler"
    span_end = 48
    names = {0: "a", 24: "b"}

    def lay_out(self):
        super().lay_out()
        self.say("The source puts handler after data[12]. VRIG's sim reads it from the first word of B's data.")
        self.beat()

    def write_payload(self):
        tr = self.tr
        self.play(self.code.focus(find(self.src, "read(")))
        self.say(f"read() takes 32 bytes into a 16-byte chunk. This payload is {len(tr.payload)}.")
        self.beat(pause=0.3)
        a = tr.snap("setup")["chunks"][0]
        self.stream_bytes(tr.payload, a["dataStart"])

    def on_chunk_write(self, off):
        b = self.tr.snap("setup")["chunks"][1]
        if off == b["addr"]:
            self.say("Past A's data. The next 8 bytes are B's _HEAP_ENTRY.", run_time=0.4)
        elif off == b["dataStart"]:
            self.say("Then B's data, starting with the handler.", run_time=0.4)

    def call(self):
        tr = self.tr
        b = tr.snap("submit")["chunks"][1]
        assert not b["headerOk"]
        self.play(self.col.paint(b["addr"], 8, "crash"))
        self.say("B's header checksum is broken now. It would fail the next time the heap validates B.")
        self.beat()
        self.call_beat("b->handler()", b["dataStart"])
        self.say("The call comes first, so nothing checks in time.")
        self.beat()

    def lfh_act(self):
        lf = self.tr.lfh
        self.lfh_grid_act(lf, "That's why the desc says spray. With LFH on, A and B don't sit side by side on purpose.")


class Win45(WinHeap):
    trace_name = "win-45"
    subtitle = "Free the same chunk twice and the list hands it out twice."
    fptr_name = "handler"
    names = {0: "a"}

    def on_free(self, prev, snap):
        c = snap["chunks"][0]
        lst = snap["freeLists"]["listHints"]["3"]
        if not snap["doubleFree"]:
            self.free_beat(snap, "HeapFree(h, 0, a)", "First free. A goes on ListHints.")
            return
        assert lst == [c["addr"], c["addr"]] and c["flink"] == c["dataStart"]
        lines = [i for i, l in enumerate(self.src) if "HeapFree(h, 0, a)" in l]
        self.play(self.code.focus(lines[-1]))
        self.to_snap(snap)
        self.show_hints(snap)
        links = self.flink_labels(snap, c)
        self.play(FadeIn(links))
        # Flink points back into A's own data
        loop = ptr_arrow(links[0].get_top(), self.col.cell(c["dataStart"]).get_top(), "unsorted",
                         path_arc=-110 * DEG)
        self.play(ShowCreation(loop))
        self.say(f"Second free of A. It's on the list twice, and its Flink is {h32(c['flink'])}, "
                 f"A's own data offset. The list points at itself.")
        self.beat()
        self.say("VRIG's version frees A, then A. The B in the source never gets freed.")
        self.beat()
        self.links, self.loop = links, loop

    def on_malloc(self, prev, snap):
        c = snap["chunks"][0]
        assert snap["names"]["B"] == snap["names"]["A"]
        self.play(self.code.focus(find(self.src, "Obj *c")))
        self.play(self.col.paint(c["dataStart"], c["dataSize"], "chunk_user"), FadeOut(self.loop))
        self.show_hints(snap)
        self.say("One allocation takes A. A is still on the list, so A can come back again.")
        self.beat()

    def write_payload(self):
        tr = self.tr
        self.play(self.code.focus(find(self.src, "read(")), FadeOut(self.links))
        self.say(f"Write A's Flink while A is live. Point it at the function pointer table, {h32(tr.raw['funcPtrAddr'])}.")
        c = tr.snap("submit")["chunks"][0]
        self.stream_bytes(tr.payload, c["dataStart"])

    def call(self):
        tr = self.tr
        final = tr.snap("submit")
        msgs = [l["msg"] for l in final["logs"]]
        self.show_hints(final)
        table = mono(f"{h32(tr.raw['funcPtrAddr'])}  function pointer table", 17, T.win)
        table.next_to(self.fptr, LEFT, buff=0.6)
        c = final["chunks"][0]
        arr = ptr_arrow(self.col.row(c["dataStart"]).cells.get_left(), table.get_bottom(), "win", path_arc=-40 * DEG)
        self.play(FadeIn(table), GrowArrow(arr))
        assert any("returned the function pointer table" in m for m in msgs)
        self.say("Two more allocations. The second one follows the Flink and lands on the table, where win() gets written.")
        self.beat()
        # Indicate on the same mobject in the same play() would undo the Transform
        self.play(*self.set_fptr(final))
        self.play(Indicate(self.fptr, color=T.win))
        assert final["funcPtrs"]["handler"]["current"] == tr.symbols["win"]
        win_line = find(self.src, "win()")
        self.play(self.code.focus(win_line))
        self.say("a->action() runs win().")
        self.beat()
        bad = tr.attempts["descHint"]
        assert not bad["completed"]
        self.say(f"The desc says to write win(). VRIG wants the table address, and {bad['payloadHex']} fails.")
        self.beat()


class Win46(WinHeap):
    trace_name = "win-46"
    subtitle = "A private heap from HeapCreate, with the same use-after-free."
    fptr_name = "obj->callback"
    names = {0: "Handler"}

    def on_free(self, prev, snap):
        c = snap["chunks"][0]
        self.free_beat(snap, "HeapFree", "HeapFree puts obj on ListHints. obj still points at it.")
        self.links = self.flink_labels(snap, c)
        self.play(FadeIn(self.links))
        self.beat(pause=0.4)

    def on_malloc(self, prev, snap):
        c = snap["chunks"][0]
        assert snap["names"]["Note"] == snap["names"]["User"]
        self.play(self.code.focus(find(self.src, "char *note")))
        self.play(self.col.paint(c["dataStart"], c["dataSize"], "chunk_user"), FadeOut(self.links))
        self.show_hints(snap)
        self.say(f"Same size, same list. The note gets {h32(self.tr.addr(c['addr']))}, which is obj.")
        self.beat()

    def write_payload(self):
        tr = self.tr
        self.play(self.code.focus(find(self.src, "read(")))
        self.say("The note's first 4 bytes are obj->callback.")
        c = tr.snap("submit")["chunks"][0]
        self.stream_bytes(tr.payload, c["dataStart"])

    def call(self):
        self.call_beat("obj->callback()", self.tr.snap("submit")["chunks"][0]["dataStart"])

    def lfh_act(self):
        lf7, lf10 = self.tr.lfh["win7"], self.tr.lfh["win10"]
        assert lf7["reuseRate"]["hits"] == lf7["reuseRate"]["trials"]
        self.say("A HEAP_NO_SERIALIZE heap never gets the LFH, so nothing shuffles where obj comes back.")
        self.beat()
        self.lfh_grid_act(lf7, "Even where Windows 7 does use the LFH, it picks first-fit. Slot 0, then 1, then 2.",
                          show_spray=False)
        r = lf10["reuseRate"]
        self.say(f"The same test on Windows 10 got the freed slot back {r['hits']} times out of {r['trials']}.")
        self.beat()
