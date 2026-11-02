"""
unit0-asm and unit7-x64: the asm-quiz exercises. Every frame plays back
VRIG's own X86Emulator (traces/<id>.json, from tools/vrig-trace/asm_x86-entry.ts)
one instruction at a time, poses VRIG's quiz questions where the run answers
them, and reveals the answer next to the register or word that proves it.

    manimgl scenes/asm_x86.py Asm06 -w -l
    manimgl scenes/asm_x86.py X64_32 -p
"""
from manimlib import *

from vrig.mob.asm_x86 import AsmListing, AsmTrace, FlagRow, QuizCard, RegFile, WordColumn, vhex
from vrig.mob.memory import mono, prose
from vrig.scene import VrigScene
from vrig.theme import T

PATCH_NOTE = ("VRIG lists two bytes for each long mov, so its emulator stops after line one. "
              "This video steps it one line at a time.")
TRUNC_NOTE = "VRIG's emulator keeps the low 32 bits of a register, so the top half reads zero."


class AsmWalkthrough(VrigScene):
    exercise = ""
    intro = ""
    notes: dict = {}          # step index -> caption, shown as that line is about to run. -1 is before step 0
    fast: range = range(0)    # steps that play quickly, like later loop passes
    initial_role = "attacker_bytes"
    stall_note = ""
    tags: dict = {}           # stack word offset from the final sp -> tag text, drawn at the end
    trunc_note = TRUNC_NOTE

    def construct(self):
        tr = AsmTrace.load(self.exercise)
        assert tr.raw["solved"], f"{tr.id}: a quiz answer disagrees with the emulator, re-export"
        self.tr = tr
        self.opening()
        self.layout()
        self.notes_done = set()
        if -1 in self.notes:
            self.say(self.notes[-1])
            self.beat()
        for i in range(len(tr.steps)):
            if tr.steps[i].get("error"):
                self.stall(i)
                break
            self.step(i)
        self.closing()

    # -- pieces ------------------------------------------------------------

    def opening(self):
        tr = self.tr
        unit = "x86" if not tr.x64 else "x86-64"
        title = prose(tr.title, 46).to_edge(UP, buff=0.5)
        sub = mono(f"{tr.id}   {unit}", 18, T.text_dim).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.say(self.intro)
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.5).to_corner(UL, buff=0.25))
        self.title = title

    def layout(self):
        tr = self.tr
        st0 = tr.state(-1)
        self.listing = AsmListing(tr)
        self.regs = RegFile(tr, tr.shown_regs(), st0["regs"], title="registers")
        self.flags = FlagRow(st0["flags"])
        mid = VGroup(self.regs, self.flags).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        cols = [self.listing, mid]

        self.stack = self.data = None
        col = VGroup()
        if tr.touches_stack():
            self.stack = WordColumn(tr, tr.stack_words(), title="stack")
            col.add(self.stack)
        if tr.data_words():
            self.data = WordColumn(tr, tr.data_words(), title="memory")
            col.add(self.data)
        if len(col):
            col.arrange(DOWN, buff=0.45, aligned_edge=RIGHT)
            cols.append(col)
        written = tr.written(-1)
        for colm in (self.stack, self.data):
            if colm is None:
                continue
            for a, slot in colm.slots.items():
                if a in written:
                    slot.box.set_fill(getattr(T, self.initial_role), 0.55)

        board = VGroup(*cols).arrange(RIGHT, buff=0.9, aligned_edge=UP)
        parts = list(cols)
        self.sp_mark = self.bp_mark = None
        if self.stack:
            self.sp_mark = self.stack.place(self.stack.marker(tr.sp, LEFT), st0["regs"][tr.sp])
            self.bp_mark = self.stack.place(self.stack.marker(tr.bp, RIGHT, "label"), st0["regs"][tr.bp])
            board.add(self.sp_mark, self.bp_mark)
            parts += [self.sp_mark, self.bp_mark]
            self.dim_free(st0["regs"][tr.sp], animate=False)
        # fill the space between the title and the caption band
        k = min(12.8 / board.get_width(), 5.5 / board.get_height(), 1.75)
        board.scale(k).move_to(UP * 0.3)
        for m in (self.regs, self.flags, self.stack, self.data):
            if m is not None:
                m.k = k
        self.k = k
        self.play(LaggedStart(*(FadeIn(p, shift=UP * 0.15) for p in parts), lag_ratio=0.15), run_time=1.6)
        self.play(self.listing.focus(0), run_time=0.4)

    def dim_free(self, sp: int, animate=True, skip=()) -> list[Animation]:
        """Words below sp are free space. Leave their bytes, fade them back."""
        anims = []
        for a, slot in self.stack.slots.items():
            o = 0.4 if a < sp else 1.0
            if getattr(slot, "_o", 1.0) == o or a in skip:
                continue
            slot._o = o
            if animate:
                anims.append(slot.val.animate.set_opacity(o))
            else:
                slot.val.set_opacity(o)
        return anims

    def slot_role(self, i: int, addr: int) -> str:
        s = self.tr.steps[i]
        ins = self.tr.ins[s["idx"]]
        if ins["mnemonic"] == "call":
            return "saved_ret"
        if ins["mnemonic"] == "push" and ins["operands"] in ("ebp", "rbp"):
            return "saved_fp"
        if self.stack and addr in self.stack.slots:
            return "local_var"
        return "buffer"

    def caption(self, i: int):
        if i in self.notes and i not in self.notes_done:
            self.notes_done.add(i)
            self.say(self.notes[i], run_time=0.5)
            return True
        return False

    def step(self, i: int):
        tr = self.tr
        s = tr.steps[i]
        before = tr.state(i - 1)
        quick = i in self.fast
        rt = 0.3 if quick else 0.7

        self.play(self.listing.focus(s["idx"]), run_time=0.15 if quick else 0.3)
        if s.get("patched") and not getattr(self, "_patched_said", False):
            self._patched_said = True
            self.say(PATCH_NOTE)
            self.beat()
        spoke = self.caption(i)
        if tr.x64 and self.trunc_note and not getattr(self, "_trunc_said", False) and self.truncates(i):
            self._trunc_said = True
            self.after_trunc = True

        anims = self.regs.update_to(s["regs"], quiet={tr.ip}) + self.flags.update_to(s["flags"])
        written = tr.written(i)
        sp = s["regs"][tr.sp]
        rewritten = set()
        for colm in (self.stack, self.data):
            if colm is None:
                continue
            for a in colm.slots:
                v = tr.word_at(i, a)
                now = (v, a in written)
                if now != colm.shown[a] and a in written:
                    # a write and a fade on the same Text fight, so the write carries the opacity
                    o = 0.4 if colm is self.stack and a < sp else 1.0
                    colm.slots[a]._o = o
                    anims += colm.write(a, v, self.slot_role(i, a), o)
                    rewritten.add(a)
        wrote = {m["addr"] for m in s.get("writes", [])}
        for a in {m["addr"] for m in s.get("reads", [])} - wrote:
            for colm in (self.stack, self.data):
                if colm is not None and a in colm.slots:
                    # pulse the text, not the box. the box may be mid-fill
                    anims.append(Indicate(colm.slots[a].val, color=T.highlight, scale_factor=1.15))
                    rewritten.add(a)  # dims on the next step instead
        if self.stack:
            bp = s["regs"][tr.bp]
            if sp != before["regs"][tr.sp]:
                anims.append(self.sp_mark.animate.move_to(self.stack.place(self.sp_mark.copy(), sp)))
            if bp != before["regs"][tr.bp]:
                # pop rbp in ret2csu loads a plain number, not a frame pointer
                on = self.stack.covers(bp)
                anims.append(self.bp_mark.animate.move_to(self.stack.place(self.bp_mark.copy(), bp)).set_opacity(1 if on else 0))
            anims += self.dim_free(sp, skip=rewritten)

        arrow = None
        nxt = tr.by_addr.get(tr.next_ip(i))
        if not s["halted"] and nxt is not None and not tr.fallthrough(i):
            # taken jump, call, or ret. patched fall-through isn't a jump
            if not (i + 1 < len(tr.steps) and tr.steps[i + 1].get("patched")):
                arrow = self.listing.jump_arrow(s["idx"], nxt)
                anims.append(ShowCreation(arrow))
        if anims:
            self.play(*anims, run_time=rt)
        else:
            self.wait(rt * 0.5)
        if getattr(self, "after_trunc", False):
            self.after_trunc = False
            self.say(self.trunc_note)
            self.beat()
        if arrow is not None:
            self.play(FadeOut(arrow), run_time=0.2 if quick else 0.4)
        if spoke:
            self.beat()
        else:
            self.wait(0.1 if quick else 0.35)
        self.on_step(i)
        for n, q in enumerate(tr.quiz):
            if q["probe"]["step"] == i:
                self.pose(n, q)

    def truncates(self, i: int) -> bool:
        ins = self.tr.ins[self.tr.steps[i]["idx"]]
        import re
        return any(int(h, 16) > 0xFFFFFFFF for h in re.findall(r"0x[0-9a-fA-F]+", ins["operands"]))

    def on_step(self, i: int):
        """Hook for per-exercise beats after step i."""

    def evidence(self, q: dict) -> tuple[str, Mobject | None]:
        p = q["probe"]
        tr = self.tr
        target = None
        if p.get("flag"):
            target = SurroundingRectangle(self.flags.cells[p["flag"]], buff=0.06)
        elif p.get("reg") and p["reg"] in self.regs.rows:
            target = self.regs.point(p["reg"])
        elif p.get("addr") is not None:
            for colm in (self.stack, self.data):
                if colm is not None and p["addr"] in colm.slots:
                    target = SurroundingRectangle(colm.slots[p["addr"]][:2], buff=0.06)
        if target is not None:
            target.set_stroke(T.win, 3)
        v = p["value"]
        if p["kind"] == "emulator":
            if p.get("flag"):
                return f"emulator: {p['flag']} = {v}", target
            if p.get("reg"):
                r = p["reg"]
                full = vhex(tr.regs(p["step"])[r], tr.width(r))
                if p["why"].startswith("low"):
                    # the answer is a slice of the register, say which
                    return f"emulator: {r} = {full}, {p['why']} = 0x{v:x}", target
                return f"emulator: {r} = {full}" + (f" = {v}" if q["format"] == "decimal" else ""), target
            return f"emulator: [{p['addr']:08x}] = {vhex(v, tr.hexw)}", target
        if p["kind"] == "derived":
            shown = str(v) if q["format"] == "decimal" else f"0x{v:x}"
            return f"from the run: {p['why']} = {shown}", target
        return f"from the run: {p['why']}", target

    def pose(self, n: int, q: dict):
        # as wide as the gap left of the registers, so the card never hides the evidence
        w = self.regs.get_left()[0] - self.listing.get_left()[0] - 0.05
        card = QuizCard(n + 1, q, width=w).align_to(self.listing, LEFT).align_to(self.listing, UP)
        card.shift(LEFT * 0.2 + UP * 0.1)
        # dim the lines only. animating the whole listing drags the focus bar to full opacity
        self.play(self.listing.lines.animate.set_opacity(0.12), self.listing.bar.animate.set_opacity(0),
                  FadeIn(card, shift=UP * 0.2), run_time=0.6)
        self.beat()
        text, target = self.evidence(q)
        ans, anims = card.reveal(text)
        if target is not None:
            anims.append(ShowCreation(target))
        self.play(*anims, run_time=0.8)
        self.beat(pause=1.4)
        out = [FadeOut(card), FadeOut(ans), self.listing.lines.animate.set_opacity(1),
               self.listing.bar.animate.set_fill(opacity=0.16)]
        if target is not None:
            out.append(FadeOut(target))
        self.play(*out, run_time=0.5)

    def stall(self, i: int):
        tr = self.tr
        s = tr.steps[i]
        self.play(self.listing.focus(s["idx"], "crash"), run_time=0.4)
        self.play(self.listing.body(s["idx"]).animate.set_color(T.crash),
                  Flash(self.listing.body(s["idx"]).get_right() + RIGHT * 0.2, color=T.crash, flash_radius=0.3))
        # under the whole listing, so it doesn't sit on top of the next line
        err = mono(s["error"], 16, T.crash).next_to(self.listing, DOWN, buff=0.25, aligned_edge=LEFT)
        self.play(FadeIn(err, shift=UP * 0.1))
        self.say(self.stall_note)
        self.beat()
        self.err = err
        self.after_stall(i)
        for n, q in enumerate(tr.quiz):
            if q["probe"]["step"] >= i:
                self.pose(n, q)

    def over_listing(self, card):
        """Park a card on the listing's column and dim the listing under it."""
        card.scale(self.k)
        card.align_to(self.listing, LEFT).align_to(self.listing, UP).shift(UP * 0.1)
        if card.get_right()[0] > self.regs.get_left()[0] - 0.05:
            card.set_width(self.regs.get_left()[0] - 0.05 - card.get_left()[0], about_edge=LEFT)
        self.play(self.listing.lines.animate.set_opacity(0.12), run_time=0.4)

    def after_stall(self, i: int):
        """Hook: show what the line that threw would have done, worked by hand."""

    def closing(self):
        tr = self.tr
        win = prose(tr.raw["winTitle"], 30, T.win).to_corner(UR, buff=0.3)
        self.play(FadeIn(win, shift=DOWN * 0.15))
        self.say(tr.raw["winMsg"])
        self.beat(pause=2.5)


# -- unit0-asm --------------------------------------------------------------

class Asm01(AsmWalkthrough):
    exercise = "asm-01"
    intro = "x86 has eight general-purpose registers, plus eip. Watch each one as the code runs."
    notes = {
        0: "mov with a number puts that number straight into the register.",
        4: "mov ebx, eax copies eax into ebx. eax keeps its value.",
        5: "xor of a register with itself is always zero.",
    }


class Asm02(AsmWalkthrough):
    exercise = "asm-02"
    intro = "mov copies data. Follow one value from an immediate into memory and back out."
    notes = {
        0: "An immediate is a constant stored inside the instruction.",
        2: "Square brackets mean memory. This stores eax at that address.",
        3: "Loading the same address gives ecx the value back.",
        5: "The next word up sits four bytes later.",
    }


class Asm03(AsmWalkthrough):
    exercise = "asm-03"
    intro = "The stack grows down. push moves esp down one word and writes there. pop reads and moves it back up."
    notes = {
        1: "push eax. esp drops by four and eax lands at the new top.",
        3: "ebx goes on top of it.",
        4: "pop takes the top word. The last value in is the first one out.",
        5: "Popped words stay in memory. Below esp they count as free space.",
        6: "push takes an immediate too.",
    }


class Asm04(AsmWalkthrough):
    exercise = "asm-04"
    intro = "Predict eax before each step. Every result lands back in the first operand."
    notes = {
        2: "add writes the sum back into eax.",
        3: "sub takes the immediate away.",
        4: "inc and dec add or subtract one.",
        8: "mul ecx multiplies eax by ecx. The high half of the product goes into edx.",
    }


class Asm05(AsmWalkthrough):
    exercise = "asm-05"
    intro = "cmp subtracts and throws the result away. Only the flags keep it."
    notes = {
        2: "Five minus five is zero, so ZF turns on.",
        4: "Five minus ten has to borrow. CF and SF turn on.",
        5: "Ten minus five is positive, so the flags clear.",
        7: "test ANDs its operands. Zero AND zero is zero, so ZF comes back on.",
    }


class Asm06(AsmWalkthrough):
    exercise = "asm-06"
    intro = "A loop in four instructions. jl sends eip back up until the counter reaches six."
    notes = {
        2: "The loop body adds the counter to a running sum in ebx.",
        5: "SF and OF differ, so jl jumps back to the top.",
        21: "Six minus six sets ZF and clears SF. jl falls through.",
        23: "ebx is fifteen, so je skips the failure path.",
    }
    fast = range(6, 21)


class Asm07(AsmWalkthrough):
    exercise = "asm-07"
    intro = "call pushes the address of the next instruction, then jumps. ret pops it back into eip."
    notes = {
        1: "The argument goes on the stack first.",
        2: "call pushes the return address and jumps to double.",
        5: "esp points at the return address, so the argument sits one word up at esp+4.",
        7: "ret pops the return address into eip. Execution lands right after the call.",
        3: "The caller removes the argument with add esp, 4.",
    }

    def construct(self):
        # step 3 runs after ret here, so key that caption to the real order
        tr = AsmTrace.load(self.exercise)
        order = [tr.ins[s["idx"]]["text"] for s in tr.steps]
        self.notes = {
            1: self.notes[1], 2: self.notes[2],
            order.index("mov eax, [esp+4]"): self.notes[5],
            order.index("ret"): self.notes[7],
            order.index("add esp, 4"): self.notes[3],
        }
        super().construct()


class Asm08(AsmWalkthrough):
    exercise = "asm-08"
    intro = "Three ways to name a memory address, and one instruction that only computes it."
    notes = {
        1: "[eax] is the word at the address in eax.",
        2: "[eax+4] adds a displacement. That's array[1].",
        5: "[eax+ebx*4] scales the index by the element size.",
        6: "lea does the same math and keeps the address. Nothing is read.",
        7: "[ebp-4] reads the stack. Nothing was ever written there, so esi gets zero.",
    }


class Asm09(AsmWalkthrough):
    exercise = "asm-09"
    intro = "Every function opens with the same three lines and closes with leave."
    notes = {
        0: "push ebp saves the caller's frame pointer.",
        1: "ebp now marks this frame. Locals live below it.",
        2: "sub esp makes room for the locals.",
        3: "x goes at ebp-4.",
        4: "y goes at ebp-8.",
        7: "leave puts esp back on ebp and pops the old ebp.",
    }


class Asm10(AsmWalkthrough):
    exercise = "asm-10"
    intro = "cdecl pushes arguments right to left, and the caller cleans them up."
    notes = {
        2: "The second argument goes on first.",
        4: "call pushes the return address on top of the arguments.",
        5: "add_nums builds its own frame.",
        7: "Past saved ebp and the return address, the first argument sits at ebp+8.",
        8: "The second one is at ebp+12.",
        10: "ret goes back to main with the sum in eax.",
        11: "add esp, 8 drops both arguments. That's the caller cleaning up.",
    }


# -- unit7-x64 --------------------------------------------------------------

class X64_29(AsmWalkthrough):
    exercise = "x64-29"
    intro = "The same stack frame on x64. A stack word is eight bytes now."
    notes = {
        0: "push rbp moves rsp down by eight.",
        2: "sub rsp, 32 reserves four words for locals.",
        3: "qword means an eight-byte store.",
        6: "add can read its second operand straight from memory.",
        7: "leave tears the frame down.",
    }


class X64_30(AsmWalkthrough):
    exercise = "x64-30"
    intro = "System V passes the first six integer arguments in registers. None of these go on the stack."
    notes = {
        2: "Each argument has a fixed register. The third goes in edx.",
        4: "The first goes in edi.",
        5: "call still pushes a return address. The arguments stay in registers.",
        8: "add3 reads its arguments straight out of registers.",
        13: "VRIG keeps edi apart from rdi. On real hardware a write to edi also zeroes the top of rdi.",
    }


class X64_31(AsmWalkthrough):
    exercise = "x64-31"
    intro = "On x64 the first argument travels in rdi. A ROP chain needs a pop rdi gadget to set it."
    trunc_note = ("VRIG parses this 64-bit immediate as a double and keeps the low 32 bits, "
                  "so the padding shows up as 0x41414000.")
    notes = {
        1: "Padding fills the buffer.",
        3: "One more word covers saved rbp.",
        5: "The return address now points at the pop rdi gadget.",
        7: "pop rdi will load this word, the address of /bin/sh.",
        9: "That gadget's own ret then lands in system().",
    }
    initial_role = "attacker_bytes"

    def slot_role(self, i, addr):
        return "attacker_bytes"

    def closing(self):
        # read the finished payload from rsp upward
        tr, st = self.tr, self.stack
        sp = tr.regs(len(tr.steps) - 1)[tr.sp]
        meaning = [("system()", "libc"), ('"/bin/sh"', "arg"), ("pop rdi; ret", "gadget"),
                   ("saved rbp", "saved_fp"), ("buf", "buffer"), ("buf", "buffer")]
        tags = VGroup()
        for k, (name, role) in enumerate(meaning):
            a = sp + k * tr.word
            slot = st.slots[a]
            tags.add(mono(name, 14, getattr(T, role)).next_to(slot.box, RIGHT, buff=0.2))
        self.play(FadeOut(self.bp_mark), LaggedStartMap(FadeIn, tags, shift=LEFT * 0.1, lag_ratio=0.15))
        self.say("Read it from rsp up. ret jumps to pop rdi, which loads /bin/sh, and its own ret lands in system().")
        self.beat()
        super().closing()


class X64_32(AsmWalkthrough):
    exercise = "x64-32"
    intro = "__libc_csu_init ends in two gadgets. Together they load three argument registers and call through a pointer."
    notes = {
        -1: "The overflow already left six values and a return address on the stack.",
        0: "gadget2 pops six registers in a row.",
        6: "Its ret jumps to gadget1.",
        7: "gadget1 copies r13 into rdx, the third argument.",
        8: "r14 goes into rsi, the second.",
    }
    stall_note = "VRIG's emulator has no r15d register, so it throws on this line and stops."

    def after_stall(self, i):
        tr = self.tr
        st = tr.raw["stall"]
        lines = VGroup(
            mono("worked by hand from the stopped state", 14, T.text_dim),
            mono(f"edi = low half of r15 = {vhex(st['edi'], 8)}", 16, T.text),
            mono(f"call [r12+rbx*8]  reads {st['slot']:08x}", 16, T.text),
            mono(f"  -> jumps to {vhex(st['target'], 16)}", 16, T.win),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        box = SurroundingRectangle(lines, buff=0.2).set_stroke(T.grid, 1.5).set_fill(T.background, 0.95)
        card = VGroup(box, lines)
        self.over_listing(card)
        self.play(FadeIn(card, shift=UP * 0.1))
        if st["slot"] in self.data.slots:
            self.play(Indicate(self.data.slots[st["slot"]].box, color=T.win))
        self.say(f"Done by hand, the function gets {st['edi']:#x}, {st['rsi']:#x}, and {st['rdx']:#x} as its three arguments.")
        self.beat()
        self.play(FadeOut(card), self.listing.lines.animate.set_opacity(1))


class X64_33(AsmWalkthrough):
    exercise = "x64-33"
    intro = "A one-gadget is a single libc address that runs execve of /bin/sh. Find libc's base, then add the offset."
    notes = {
        2: "Leak minus known offset gives the libc base. The two match here, so the base is zero.",
        4: "Next comes the one-gadget offset.",
        6: "rdx holds the one-gadget address, ready to go over the return address.",
    }


class X64_34(AsmWalkthrough):
    exercise = "x64-34"
    intro = "A forking server gives every child the same canary. Guess it one byte at a time."
    notes = {
        1: "The canary's lowest byte is always zero. String functions stop there.",
        3: "A wrong guess crashes the child. The parent forks a new one with the same canary.",
        4: "A right guess survives, so move on to the next byte.",
        7: "Seven bytes at 256 guesses each gives the whole canary.",
    }


class X64_35(AsmWalkthrough):
    exercise = "x64-35"
    intro = "PIE moves the whole binary, but offsets inside it stay fixed. One leak gives the base."
    notes = {
        1: "Masking off the low 12 bits rounds down to the page start, the PIE base.",
        4: "Base plus win()'s offset gives its real address.",
        6: "The saved return address already shares every byte with win() but the last two.",
    }
    stall_note = "VRIG's emulator has no ax register, so this line throws."

    def after_stall(self, i):
        tr = self.tr
        st = tr.raw["stall"]
        w = 16
        before, after = vhex(st["before"], w), vhex(st["after"], w)
        a = mono(before, 20, T.text)
        b = mono(after, 20, T.win)
        # the last four hex digits are the two bytes mov ax replaces
        b[-4:].set_color(T.attacker_bytes)
        win = mono(f"win()  {vhex(st['win'], w)}", 20, T.win)
        lines = VGroup(mono("worked by hand: rax with ax replaced", 14, T.text_dim), a, b, win)
        lines.arrange(DOWN, aligned_edge=RIGHT, buff=0.14)
        lines[0].align_to(lines, LEFT)
        box = SurroundingRectangle(lines, buff=0.2).set_stroke(T.grid, 1.5).set_fill(T.background, 0.95)
        card = VGroup(box, lines)
        self.over_listing(card)
        self.play(FadeIn(box), FadeIn(lines[0]), FadeIn(a))
        self.play(TransformFromCopy(a, b))
        self.play(FadeIn(win, shift=UP * 0.1))
        assert st["matches"]
        self.say("Done by hand, swapping only the low two bytes lands exactly on win().")
        self.beat()
        self.play(FadeOut(card), self.listing.lines.animate.set_opacity(1))


class X64_36(AsmWalkthrough):
    exercise = "x64-36"
    intro = "This chain needs two leaks before it can aim anywhere."
    notes = {
        1: "Leak minus offset gives the PIE base.",
        3: "The GOT sits at a fixed offset from that base. lea points rax at the puts entry.",
        4: "Reading that slot leaks where puts lives in libc.",
        6: "Leak minus the puts offset gives libc's base.",
        9: "Add the one-gadget offset to get the shell address.",
    }
