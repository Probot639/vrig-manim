"""
unit13-arm and unit14-mips. Two kinds of scene.

ArchWalkthrough plays back VRIG's own ArmEmulator / MipsEmulator one
instruction at a time (traces/<id>.json from tools/vrig-trace/arch-entry.ts),
shows the register file, the ARM CPSR flags or the MIPS delay slot, and any
memory it touches, then poses each quiz question against what the emulator
actually computed.

ArchStack and ArchRop play the input-hex overflow and ROP exercises back
through VRIG's StackSim, the same StackTrace the x86 stack scenes use.

    manimgl scenes/arch.py Arm63 -w -l
    manimgl scenes/arch.py Mips74 -p

The ARM emulator reads pc as pc+8, so it fetches two instructions ahead of
where pc points and runs roughly every third line. The quiz answers assume
real ARM, so most of them disagree with the run. The walkthrough shows the
real run and says so on screen. It does not pretend the textbook answer came
out of VRIG.
"""
from manimlib import *

from vrig.mob.arch import ArchTrace, AsmListing, DelaySlot, FlagRow, QuizCard, RegFile, WordColumn, vhex
from vrig.mob.cpu import CodeListing
from vrig.mob.memory import PayloadStrip, StackView, le_assemble, mono, prose
from vrig.scene import VrigScene
from vrig.theme import T
from vrig.trace import StackTrace, h32

PC_BUG = ("Watch pc against the bar. VRIG's ARM core reads pc as pc plus eight, "
          "so it fetches two lines ahead and runs about every third instruction.")

BRANCH = {"arm": {"b", "bl", "bx"}, "mips": {"beq", "bne", "j", "jal", "jr"}}


class ArchWalkthrough(VrigScene):
    exercise = ""
    intro = ""
    notes: dict = {}          # step index -> caption shown as that step runs
    fast: range = range(0)
    closing_note = ""         # extra line at the end, e.g. the ARM bug summary

    def construct(self):
        self.tr = ArchTrace.load(self.exercise)
        self.opening()
        self.layout()
        self.said_skew = False
        for i in range(len(self.tr.steps)):
            self.step(i)
        self.quiz_round()
        self.closing()

    # -- framing -----------------------------------------------------------

    def opening(self):
        tr = self.tr
        title = prose(tr.title, 46).to_edge(UP, buff=0.5)
        sub = mono(f"{tr.id}   {tr.arch.upper()}", 18, T.text_dim).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.say(self.intro)
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.5).to_corner(UL, buff=0.25))
        self.title = title

    def layout(self):
        tr = self.tr
        self.listing = AsmListing(tr)
        st0 = tr.state(-1)
        self.regs = RegFile(tr, tr.shown_regs(), st0["regs"])
        if tr.is_arm:
            self.aux = FlagRow(st0["flags"])
        else:
            self.aux = DelaySlot()
        mid = VGroup(self.regs, self.aux).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
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

        board = VGroup(*cols).arrange(RIGHT, buff=0.9, aligned_edge=UP)
        k = min(12.6 / board.get_width(), 5.4 / board.get_height(), 1.7)
        board.scale(k).move_to(UP * 0.35)
        for m in (self.regs, self.aux, self.stack, self.data):
            if m is not None:
                m.k = k
        self.k = k
        self.pc = self.listing.pc_marker()
        self.listing.place_left(self.pc, tr.steps[0]["pcBefore"])
        self.play(LaggedStart(*(FadeIn(p, shift=UP * 0.15) for p in cols), lag_ratio=0.15), run_time=1.4)
        self.play(FadeIn(self.pc), self.listing.focus(tr.steps[0]["fetched"]), run_time=0.4)
        if tr.raw["pcFetchBug"]:
            self.say(PC_BUG)
            self.beat()

    # -- one instruction ---------------------------------------------------

    def step(self, i: int):
        tr = self.tr
        s = tr.steps[i]
        quick = i in self.fast
        rt = 0.3 if quick else 0.7

        role = "crash" if s["skipped"] else "highlight"
        self.play(self.listing.focus(s["fetched"], role),
                  self.pc.animate.move_to(self.listing.place_left(self.pc.copy(), s["pcBefore"])),
                  run_time=0.2 if quick else 0.4)

        if tr.is_arm and s["fetchSkew"] and not self.said_skew:
            self.said_skew = True
            skew = mono("pc + 8", 15, T.pointer).next_to(self.pc, LEFT, buff=0.15)
            self.play(FadeIn(skew, shift=RIGHT * 0.1))
            self.beat(pause=0.4)
            self.play(FadeOut(skew))

        cap = self.notes.get(i)
        if cap:
            self.say(cap, run_time=0.5)

        anims = self.regs.update_to(s["regs"], quiet={"r15", "pc"})
        if tr.is_arm:
            anims += self.aux.update_to(s["flags"])
        else:
            anims += self.aux.update_to(s["inDelaySlot"], s["branchPending"])

        live = tr.live_words(i)
        for colm in (self.stack, self.data):
            if colm is None:
                continue
            for a in colm.slots:
                v = tr.word_at(i, a)
                now = (v, a in live)
                if now != colm.shown[a] and a in live:
                    anims += colm.write(a, v, "local_var")
        for a in {m["addr"] & ~3 for m in s["reads"]}:
            for colm in (self.stack, self.data):
                if colm is not None and (a & 0xFFFFFFFF) in colm.slots:
                    anims.append(Indicate(colm.slots[a & 0xFFFFFFFF].val, color=T.highlight, scale_factor=1.15))

        arrow = None
        if s["mnemonic"].lower() in BRANCH[tr.arch]:
            tgt = s["branchTarget"] if not tr.is_arm else (tr.steps[i + 1]["fetched"] if i + 1 < len(tr.steps) else None)
            if tgt is not None and tgt in tr.by_addr and tgt != s["fetched"]:
                arrow = self.listing.jump_arrow(s["fetched"], tgt)
                anims.append(ShowCreation(arrow))

        if anims:
            self.play(*anims, run_time=rt)
        else:
            self.wait(rt * 0.5)
        if cap:
            self.beat()
        else:
            self.wait(0.1 if quick else 0.3)
        if arrow is not None:
            self.play(FadeOut(arrow), run_time=0.3)

    # -- quiz --------------------------------------------------------------

    def quiz_round(self):
        tr = self.tr
        w = self.regs.get_left()[0] - self.listing.get_left()[0] - 0.05
        self.play(self.listing.lines.animate.set_opacity(0.12), self.listing.bar.animate.set_opacity(0),
                  self.pc.animate.set_opacity(0), run_time=0.5)
        for n, q in enumerate(tr.quiz):
            card = QuizCard(n + 1, q, width=max(w, 4.6)).align_to(self.listing, LEFT).align_to(self.listing, UP)
            card.shift(LEFT * 0.2 + UP * 0.1)
            self.play(FadeIn(card, shift=UP * 0.2), run_time=0.5)
            self.beat()
            rows, anims = card.reveal()
            self.play(*anims, run_time=0.7)
            self.beat(pause=1.3)
            self.play(FadeOut(card), FadeOut(rows), run_time=0.4)

    def closing(self):
        tr = self.tr
        if tr.raw["solved"]:
            head = prose(tr.raw["winTitle"], 30, T.win).to_corner(UR, buff=0.3)
            self.play(FadeIn(head, shift=DOWN * 0.15))
            self.say(tr.raw["winMsg"])
        else:
            head = prose("Emulator run recorded", 28, T.crash).to_corner(UR, buff=0.3)
            self.play(FadeIn(head, shift=DOWN * 0.15))
            self.say(self.closing_note or PC_BUG)
        self.beat(pause=2.4)


# =============================================================================
# unit13-arm  (asm-quiz)
# =============================================================================


class Arm63(ArchWalkthrough):
    exercise = "arm-63"
    intro = "ARM has sixteen registers. r0 through r12 for general use, then sp, lr, and pc."
    closing_note = ("The lesson wants r0 is ten, r3 is twenty, and r4 is the stack pointer. "
                    "VRIG skipped the lines that set them, so the run holds none of those.")
    notes = {
        0: "pc points at line one, but the fetch already landed on r2 equals thirty.",
        1: "One step on, pc reaches line four, yet the fetch is at mov r4, sp.",
    }


class Arm64(ArchWalkthrough):
    exercise = "arm-64"
    intro = "ARM takes three operands, and the barrel shifter can shift the last one for free."
    closing_note = ("Real ARM gives r0 is ten, r5 is twenty-eight, and r3 is five. "
                    "The pc plus eight fetch ran different lines, so the run disagrees.")
    notes = {
        0: "The first fetch is already two lines past pc, at the add.",
    }


class Arm65(ArchWalkthrough):
    exercise = "arm-65"
    intro = "ARM is load and store. Only ldr and str touch memory, and arithmetic stays in registers."
    closing_note = ("The data at 0x20000 holds the three seeded words. The fetch bug meant "
                    "VRIG ran past most of the loads, so the quiz values never landed in the registers.")
    notes = {
        0: "The seeded words sit on the right. pc is at line one, the fetch is two ahead.",
    }


class Arm66(ArchWalkthrough):
    exercise = "arm-66"
    intro = "ARM's signature trick is the condition suffix. moveq runs only when the zero flag is set."
    closing_note = ("Conditional execution needs the cmp to set the flags first. The fetch bug "
                    "skipped every cmp, so the flags stayed clear and the wrong moves ran.")
    notes = {
        0: "No cmp ran, so the flags are clear. That is already the bug biting.",
        1: "moveq checks the zero flag. It is clear, so this one is skipped.",
    }


class Arm67(ArchWalkthrough):
    exercise = "arm-67"
    intro = "ARM passes arguments in r0 through r3. bl saves the return address in lr, and bx lr goes back."
    closing_note = ("bl did save lr correctly, so that answer matches. The fetch bug then jumped "
                    "past the function body, so the add and the saved result never happened.")
    notes = {
        0: "bl stores the next address in lr, then branches. lr is the return address.",
    }


class Arm68(ArchWalkthrough):
    exercise = "arm-68"
    intro = "An ARM frame pushes fp and lr, then drops sp for locals. The saved lr is the overflow target."
    closing_note = ("The push and the two stores never ran, so sp and the frame are wrong. "
                    "On real ARM sp drops by eight at the push, then sixteen more, for twenty-four bytes.")
    notes = {
        0: "sub sp runs here, but the push that should come first was skipped.",
    }


# =============================================================================
# unit14-mips  (asm-quiz)
# =============================================================================


class Mips71(ArchWalkthrough):
    exercise = "mips-71"
    intro = "MIPS has no mov. You load a constant with addiu from $zero, and $zero never changes."
    notes = {
        3: "This writes forty-two to $zero. The write is dropped, $zero stays zero.",
        4: "or with $zero reads $zero back. Still zero, so $t3 is zero.",
        5: "or with $zero also copies a register. $t4 gets $t0.",
    }


class Mips72(ArchWalkthrough):
    exercise = "mips-72"
    intro = "MIPS arithmetic takes three registers. Shifts stand in for multiply and divide by powers of two."
    notes = {
        2: "sll by two is a multiply by four. Fifteen becomes sixty.",
        3: "srl by one is an integer divide by two. Seven becomes three.",
        4: "and keeps the bits both operands share.",
    }


class Mips73(ArchWalkthrough):
    exercise = "mips-73"
    intro = "MIPS is big-endian, so byte zero of a word is the top byte. lb loads one byte and sign extends it."
    notes = {
        0: "lw pulls the whole word. The seeded value on the right lands in $t0.",
        2: "lb reads byte zero, the top byte 0xDE, then sign extends it to a full word.",
        4: "The stored word round-trips. $t4 reads back ninety-nine.",
    }


class Mips74(ArchWalkthrough):
    exercise = "mips-74"
    intro = "The branch delay slot is the one idea to hold onto. The line after a branch always runs."
    notes = {
        3: "beq is taken, so a jump is pending. But the next line runs first.",
        4: "This is the delay slot. It sets $t2 to one before the branch lands.",
        5: "Now the branch takes effect and skips the line in between.",
    }


class Mips75(ArchWalkthrough):
    exercise = "mips-75"
    intro = "MIPS keeps the return address in $ra. jal sets it to pc plus eight, past the delay slot."
    notes = {
        2: "jal saves $ra and queues the jump. $ra is the line after the delay slot.",
        3: "The delay slot runs. Here it is a nop.",
        5: "jr $ra queues the return. Its own delay slot runs next.",
        7: "Back in main, $t0 takes the result out of $v0.",
    }


class Mips76(ArchWalkthrough):
    exercise = "mips-76"
    intro = "A MIPS frame saves $ra on the stack by hand, because no call instruction pushes it."
    notes = {
        0: "The prologue drops sp by twenty-four.",
        1: "sw stores $ra twenty bytes up the frame. That saved copy is the overflow target.",
        2: "The old frame pointer goes four bytes below it.",
        7: "The epilogue restores sp, then reloads $ra before the function returns.",
    }


# =============================================================================
# input-hex: stack overflow and ROP
# =============================================================================


class ArchStack(VrigScene):
    """
    arm-69 and mips-77: a 16-byte buffer, saved fp or $ra above it, then the
    return slot. The payload fills the buffer, steps over the saved register,
    and lands win() in the return slot. VRIG's StackSim is little-endian for
    all of them, so the bytes go in low-first whatever the lesson says about
    endianness.
    """
    exercise = ""
    slot_name = "saved lr"     # what sits between buf and the return slot
    intro = ""
    reach_note = ""
    endian_note = ""

    def construct(self):
        tr = StackTrace.load(self.exercise)
        assert tr.won(), f"{tr.id}: VRIG does not accept this payload, re-export"
        self.tr = tr
        self.opening()
        self.overflow()
        self.read_back()

    def opening(self):
        tr = self.tr
        title = prose(tr.title, 44).to_edge(UP, buff=0.4)
        self.play(Write(title))
        self.say(self.intro)
        self.beat()
        self.play(title.animate.scale(0.6).to_corner(UL, buff=0.25))
        self.title = title

    def overflow(self):
        tr = self.tr
        src = [l for l in tr.source if not l.startswith("#include")]
        code = CodeListing(src, size=16).to_corner(UL, buff=0.5).shift(DOWN * 0.5)
        if code.get_height() > 5.6:
            code.set_height(5.6)
        stack = StackView(tr, n_words=tr.total // tr.word).shift(RIGHT * 2.0 + UP * 0.1)
        tags = VGroup(
            stack.region_tag(0, f"buf[{tr.buf_size}]", "buffer", tr.buf_size // tr.word),
            stack.region_tag(tr.ebp_off, self.slot_name, "saved_fp"),
            stack.region_tag(tr.ret_off, "return addr", "saved_ret"),
        )
        self.play(FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.3))
        self.beat()

        gets_line = next(i for i, l in enumerate(src) if "gets(" in l)
        self.play(code.focus(gets_line))
        strip = PayloadStrip(tr.payload).next_to(code, DOWN, buff=0.4, aligned_edge=LEFT)
        strip_lab = mono("input", 16, T.text_dim).next_to(strip, UP, buff=0.1, aligned_edge=LEFT)
        self.say("gets() copies the input word by word, in the order you typed it.")
        self.play(FadeIn(strip_lab), FadeIn(strip, lag_ratio=0.02, run_time=1.1))

        w = tr.word
        for step in tr.steps:
            if not step["label"].startswith("gets(): write"):
                continue
            off = step["hl"][0]
            data = step["memory"][off:off + w]
            self.play(
                *[TransformFromCopy(sc, c, path_arc=-20 * DEG)
                  for sc, c in zip(strip.cells[off:off + w], stack.at(off).cells)],
                strip.cells[off:off + w].animate.set_opacity(0.2),
                run_time=0.35 if off < tr.buf_size else 0.6,
            )
            over = tr.buf_size <= off <= tr.ret_off
            self.play(*stack.write_word(off, data, "attacker_bytes", overflow=over), run_time=0.25)
            if off == tr.ret_off:
                self.say(self.reach_note)
                self.beat()
                break

        self.play(FadeOut(strip), FadeOut(strip_lab), FadeOut(tags))
        self.stack, self.code = stack, code

    def read_back(self):
        tr = self.tr
        word = self.stack.at(tr.ret_off)
        value, anims = le_assemble(word)
        self.say(self.endian_note)
        self.play(*anims, run_time=0.8)
        target = tr.word_at(tr.ret_off)
        name = next((f"{n}()" for n, a in tr.symbols.items() if a == target), h32(target))
        lab = mono(name, 16, T.win).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.win, 0.85))
        self.beat()
        win = prose(tr.raw["winTitle"], 26, T.win).to_corner(UR, buff=0.3)
        self.play(FadeIn(win, shift=DOWN * 0.15))
        self.say(tr.raw["winMsg"])
        self.beat(pause=2.2)


class Arm69(ArchStack):
    exercise = "arm-69"
    slot_name = "saved fp"
    intro = "On ARM the saved lr on the stack is the return target, the same role as x86's saved return address."
    reach_note = "Past the buffer and the saved fp, the input reaches the slot that holds the return address."
    endian_note = "Read the slot back low byte first, and it is the address of win()."


class Mips77(ArchStack):
    exercise = "mips-77"
    slot_name = "saved $fp"
    intro = "On MIPS the saved $ra lives on the stack, so an overflow overwrites it just like x86's return address."
    reach_note = "Past the buffer and the saved frame pointer, the input reaches the saved return address."
    endian_note = ("The lesson says MIPS is big-endian, but VRIG's StackSim stores every slot little-endian, "
                   "so win() goes in low byte first.")


class ArchRop(VrigScene):
    """
    arm-70 and mips-78: ROP on NX stacks. The intended chain writes the magic
    value through the flag pointer, then returns into win().

    VRIG reuses its x86 ROP interpreter here. That interpreter only reads
    "pop <reg>", "mov [ebx], eax", and "xchg eax, esp", so it cannot run an
    ARM "pop {r0, pc}" or a MIPS "lw $a0, 0($sp)". The chain desyncs, the flag
    never gets written, and ropWin never fires. The video shows the intended
    chain, then VRIG's real log and the honest result: no win.
    """
    exercise = ""
    intro = ""
    chain: list = []          # (gadget text, what it is meant to do)
    bug_note = ""

    def construct(self):
        tr = StackTrace.load(self.exercise)
        assert not tr.won(), f"{tr.id}: VRIG now accepts this, the ROP bug may be fixed, revisit"
        self.tr = tr
        self.opening()
        self.plan()
        self.real_run()

    def opening(self):
        tr = self.tr
        title = prose(tr.title, 44).to_edge(UP, buff=0.4)
        self.play(Write(title))
        self.say(self.intro)
        self.beat()
        self.play(title.animate.scale(0.6).to_corner(UL, buff=0.25))
        self.title = title

    def plan(self):
        tr = self.tr
        self.say("Here is the chain the lesson wants, gadget by gadget.")
        rows = VGroup()
        for i, (g, note) in enumerate(self.chain):
            n = mono(f"{i + 1}", 18, T.gadget)
            gad = mono(g, 16, T.gadget)
            desc = prose(note, 16, T.text_dim)
            body = VGroup(gad, desc).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
            rows.add(VGroup(n, body).arrange(RIGHT, buff=0.35, aligned_edge=UP))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.3).move_to(UP * 0.2)
        if rows.get_height() > 5.0:
            rows.set_height(5.0)
        self.play(LaggedStartMap(FadeIn, rows, shift=UP * 0.15, lag_ratio=0.25), run_time=1.6)
        self.beat()
        magic = mono(f"flag at {h32(tr.flag_addr)} must hold {h32(tr.magic)}", 18, T.highlight)
        magic.next_to(rows, DOWN, buff=0.45)
        self.play(FadeIn(magic, shift=UP * 0.1))
        self.beat()
        self.plan_rows = rows
        self.magic = magic

    def real_run(self):
        tr = self.tr
        self.play(FadeOut(self.plan_rows), FadeOut(self.magic))
        self.say("Now VRIG runs the chain through its own engine. Watch the log.")
        step = tr.steps[tr.step_index("ROP chain")]
        lines = VGroup()
        for log in step["logs"]:
            role = {"success": "win", "error": "crash", "action": "label"}.get(log["cls"], "text")
            lines.add(mono(log["msg"], 15, getattr(T, role)))
        lines.arrange(DOWN, aligned_edge=LEFT, buff=0.1).move_to(UP * 0.1)
        if lines.get_width() > 12.4:
            lines.set_width(12.4)
        if lines.get_height() > 5.4:
            lines.set_height(5.4)
        self.play(LaggedStartMap(FadeIn, lines, shift=RIGHT * 0.1, lag_ratio=0.25), run_time=2.0)
        self.beat()
        head = prose("No win recorded", 28, T.crash).to_corner(UR, buff=0.3)
        self.play(FadeIn(head, shift=DOWN * 0.15), Indicate(lines[-1], color=T.crash, scale_factor=1.05))
        self.say(self.bug_note)
        self.beat(pause=2.4)


class Arm70(ArchRop):
    exercise = "arm-70"
    intro = "ARM ROP chains gadgets that end in pop pc or bx lr. The goal is to write the magic value, then reach win()."
    chain = [
        ("pop {r0, pc}", "load r0 with the magic value, then return"),
        ("pop {r1, pc}", "load r1 with the flag address, then return"),
        ("str r0, [r1]; pop {pc}", "store r0 at the flag address, then return into win()"),
    ]
    bug_note = ("VRIG's ROP engine is the x86 one. It cannot read pop into a register pair or an ARM store, "
                "so the chain slips, the flag stays zero, and the win never registers.")


class Mips78(ArchRop):
    exercise = "mips-78"
    intro = "MIPS ROP chains gadgets that end in jr $ra. A split cache makes injected code unreliable, so ROP is the way in."
    chain = [
        ("lw $a0, 0($sp); ...; jr $ra", "load $a0 with the magic value, then return"),
        ("lw $a1, 0($sp); ...; jr $ra", "load $a1 with the flag address, then return"),
        ("sw $a0, 0($a1); ...; jr $ra", "store $a0 at the flag address, then return into win()"),
    ]
    bug_note = ("VRIG's ROP engine is the x86 one. A MIPS load from the stack reads as nothing, so the first "
                "gadget does no work, the chain breaks on the next word, and the win never registers.")
