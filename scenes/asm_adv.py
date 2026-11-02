"""
Units 15 to 20, the advanced asm-quiz exercises. Each scene walks VRIG's own
X86Emulator trace (traces/<id>.json, from tools/vrig-trace/asm_adv-entry.ts)
and then shows the idea the quiz is about.

    manimgl scenes/asm_adv.py Mit79 -w -l
    manimgl scenes/asm_adv.py Adv2_97 -p
"""
import random

from manimlib import *

from vrig.mob.asm_adv import AsmListing, AsmTrace, Flags, MemBox, QuizBoard, hx, para, pointer, regs_for
from vrig.mob.memory import CELL, GAP, LIFT, ByteCell, mono, prose
from vrig.mob.space import arc3d, billboard
from vrig.scene import Vrig3DScene, VrigScene
from vrig.theme import T


class AsmAdv:
    trace_name = ""
    quiz_labels: list[str] = []

    def load(self) -> AsmTrace:
        tr = AsmTrace.load(self.trace_name)
        assert tr["solved"], f"{tr.id}: VRIG doesn't accept these answers, re-export"
        self.tr = tr
        return tr

    # -- open / close ------------------------------------------------------

    def heading(self, sub: str, hud: bool = False):
        tr = self.tr
        title = prose(tr.title, 46).move_to(UP * 0.4)
        s = prose(sub, 26, T.text_dim).next_to(title, DOWN, buff=0.3)
        prot = VGroup(*(mono(p["name"], 16, T.mitigation) for p in tr["protections"]))
        if len(prot):
            prot.arrange(RIGHT, buff=0.4).next_to(s, DOWN, buff=0.45)
        for m in (title, s, prot):
            m.fix_in_frame()
        self.play(Write(title), FadeIn(s, shift=UP * 0.2), FadeIn(prot, lag_ratio=0.2))
        self.beat()
        self.play(FadeOut(s), FadeOut(prot), title.animate.scale(0.5).to_corner(UL, buff=0.25))
        self.title_mob = title
        return title

    def clear_stage(self, *keep, run_time=0.8):
        keep = set(keep) | {self.cap, self.title_mob, self.frame}
        gone = [m for m in self.mobjects if m not in keep]
        if gone:
            self.play(*map(FadeOut, gone), run_time=run_time)

    def quiz(self, caption: str):
        tr = self.tr
        self.clear_stage()
        board = QuizBoard(tr, self.quiz_labels).move_to(UP * 0.3).fix_in_frame()
        for c in board.cards:
            c.ans.set_opacity(0)
        self.play(LaggedStart(*(FadeIn(VGroup(c.q, c.label), shift=RIGHT * 0.2) for c in board.cards),
                              lag_ratio=0.25))
        self.say(caption)
        for c in board.cards:
            c.ans.set_opacity(1)
            self.play(FadeIn(c.ans, scale=1.3), run_time=0.5)
        self.beat()
        self.board = board

    def outro(self, caption: str | None = None):
        tr = self.tr
        self.clear_stage()
        head = prose(tr.win_title, 40, T.win).move_to(UP * 1.0)
        body = para(tr.first_sentence(), 58, 26, T.text).next_to(head, DOWN, buff=0.45)
        VGroup(head, body).fix_in_frame()
        self.play(FadeIn(head, shift=UP * 0.2), FadeIn(body, shift=UP * 0.2))
        if caption:
            self.say(caption)
        self.beat(pause=2.0)

    # -- the emulator walk -------------------------------------------------

    def walk_setup(self, instrs, reg_names, size=20, show_bytes=True, init=None, addr_w=None, width=8,
                   corner=UL, hud=False):
        tr = self.tr
        lst = AsmListing(instrs, size=size, addr_w=addr_w or tr.addr_w, show_bytes=show_bytes)
        lst.to_corner(corner, buff=0.4).shift(DOWN * 0.45)
        init = init if init is not None else tr["run"]["init"]["regs"]
        regs = regs_for(reg_names, init, width=width)
        regs.to_corner(UR, buff=0.35).shift(DOWN * 0.4)
        if hud:
            lst.fix_in_frame()
            regs.fix_in_frame()
        return lst, regs

    def walk(self, steps, lst, regs, init_regs=None, rt=0.5, role="highlight", on=None, flags=None,
             override=None, focus_color=None):
        """
        One play() per instruction: bar moves, changed registers update.
        Diffs come from consecutive register snapshots rather than the
        emulator's diff list, so a step that threw still shows what it did.
        """
        ip = self.tr.ip
        prev = dict(init_regs if init_regs is not None else self.tr["run"]["init"]["regs"])
        sticky = {}  # overridden registers keep their value until the emulator writes them again
        raw_prev = dict(prev)
        for s in steps:
            ins = s.get("instr")
            if ins is None:
                continue
            now = dict(s["regs"])
            for r in [r for r in sticky if now.get(r) != raw_prev.get(r)]:
                sticky.pop(r)
            raw_prev = dict(s["regs"])
            if override:
                sticky.update(override(s) or {})
            now.update(sticky)
            anims = [lst.focus(ins["addr"], focus_color)]
            for r, v in now.items():
                if r in regs.rows and prev.get(r) != v:
                    if r == ip:
                        anims.append(regs.set(r, v, "label")[0])
                    else:
                        anims += regs.set(r, v, role)
            if flags is not None and "flags" in s:
                anims += flags.show(s["flags"])
            self.play(*anims, run_time=rt)
            prev = now
            if on:
                on(s)
        return prev


# ======================================================================
# unit 15: mitigations
# ======================================================================

class Mit79(AsmAdv, VrigScene):
    trace_name = "mit-79"
    quiz_labels = [
        "Guesses to cover 12 bits of entropy",
        "Possible bases with 28 bits",
        ".text base in both runs, no PIE",
    ]

    def construct(self):
        tr = self.load()
        self.heading("Same binary, two runs, different addresses.")
        lst, regs = self.walk_setup(tr.instructions, ("eip", "eax", "ebx", "ecx", "edx"))
        self.play(FadeIn(lst), FadeIn(regs))

        # Run 1 / Run 2 table from the exercise's source comments
        rows = VGroup()
        cells = {}
        head = VGroup(mono("region", 20, T.text_dim), mono("run 1", 20, T.text_dim), mono("run 2", 20, T.text_dim))
        for r in tr["runs"]:
            name = mono(r["name"], 24, T.label)
            a = mono(hx(r["run1"]), 24, T.text)
            b = mono(hx(r["run2"]), 24, T.text)
            cells[r["name"]] = (name, a, b, r)
        grid = VGroup(head, *(VGroup(*cells[n][:3]) for n in cells))
        for row in grid:
            row[0].set_x(0.9, LEFT)
            row[1].set_x(2.6, LEFT)
            row[2].set_x(4.8, LEFT)
        grid.arrange(DOWN, buff=0.22, aligned_edge=LEFT).move_to(DOWN * 1.05)
        for row in grid:
            row[0].set_x(-3.2, LEFT)
            row[1].set_x(-1.0, LEFT)
            row[2].set_x(1.9, LEFT)
        for n in cells:
            cells[n][1].set_opacity(0)
            cells[n][2].set_opacity(0)
        self.play(FadeIn(head), *(FadeIn(cells[n][0]) for n in cells))
        self.say("Run 1. Each mov loads where a region landed this time.")

        order = {".text": "eax", ".data": "ebx", "stack": "ecx", "heap": "edx"}

        def land(s):
            for name, reg in order.items():
                if s["instr"]["operands"].startswith(reg):
                    a = cells[name][1]
                    a.set_opacity(1)
                    self.play(TransformFromCopy(regs.rows[reg][1], a), run_time=0.5)

        self.walk(tr.steps, lst, regs, on=land, rt=0.45)
        libc = cells["libc"][1]
        libc.set_opacity(1)
        self.play(FadeIn(libc))
        self.beat()

        self.say("Run 2. Reload the same binary and read the table again.")
        anims = []
        for n, (name, a, b, r) in cells.items():
            b.set_opacity(1)
            moved = r["run1"] != r["run2"]
            if moved:
                # light up only the hex digits that changed
                s1, s2 = hx(r["run1"]), hx(r["run2"])
                for k, (c1, c2) in enumerate(zip(s1, s2)):
                    if c1 != c2:
                        b[k].set_color(T.attacker_bytes)
            anims.append(FadeIn(b, shift=DOWN * 0.3))
        self.play(LaggedStart(*anims, lag_ratio=0.15), run_time=1.6)
        fixed = VGroup(*(VGroup(cells[n][0], cells[n][2]) for n in cells if cells[n][3]["run1"] == cells[n][3]["run2"]))
        boxes = VGroup(*(SurroundingRectangle(f, buff=0.08).set_stroke(T.mitigation, 2) for f in fixed))
        note = mono("no PIE, never moves", 18, T.mitigation).next_to(boxes, RIGHT, buff=0.3)
        self.play(ShowCreation(boxes), FadeIn(note))
        self.say("Stack, heap, and libc moved. .text and .data stayed put because this binary isn't PIE.")
        self.beat()

        # brute force: 12 bits is a 64 x 64 board with one right answer
        self.clear_stage()
        n = 64
        side = 4.6
        board = Square(side).set_stroke(T.grid, 1.5)
        lines = VGroup(*(Line(board.get_corner(DL) + RIGHT * side * i / n, board.get_corner(UL) + RIGHT * side * i / n)
                         for i in range(1, n)),
                       *(Line(board.get_corner(DL) + UP * side * i / n, board.get_corner(DR) + UP * side * i / n)
                         for i in range(1, n))).set_stroke(T.grid, 0.4)
        bf = VGroup(board, lines).move_to(LEFT * 2.6 + DOWN * 0.1)
        rng = random.Random(79)
        hit = rng.randrange(n * n)
        cell = side / n
        target = Square(cell).set_fill(T.win, 1).set_stroke(width=0)
        target.move_to(board.get_corner(UL) + (RIGHT * (hit % n + 0.5) + DOWN * (hit // n + 0.5)) * cell)
        count = tr.quiz[0]["answer"]
        lab = mono(f"2^12 = {count} bases", 26, T.text).next_to(bf, RIGHT, buff=0.8).shift(UP * 1.2)
        self.play(ShowCreation(board), FadeIn(lines, lag_ratio=0.01), run_time=1.2)
        self.play(FadeIn(lab))
        self.say("Twelve bits of entropy means 4096 possible bases. Without a leak you guess.")

        # sweep the guesses row by row until the hidden one turns up
        tried = Rectangle(side, 0.001).set_fill(T.crash, 0.35).set_stroke(width=0)
        tried.move_to(board.get_top(), aligned_edge=UP)
        full_rows = hit // n
        self.add(tried)
        self.play(tried.animate.stretch_to_fit_height(max(cell * full_rows, 0.001), about_edge=UP), run_time=2.0)
        tail = Rectangle(cell * (hit % n), cell).set_fill(T.crash, 0.35).set_stroke(width=0)
        tail.move_to(board.get_corner(UL) + DOWN * cell * full_rows, aligned_edge=UL)
        self.play(GrowFromEdge(tail, LEFT), run_time=0.6)
        self.play(FadeIn(target, scale=3), Flash(target, color=T.win))
        ring = Circle(radius=0.22).set_stroke(T.win, 3).move_to(target)
        tries = mono("one right guess", 22, T.win).next_to(lab, DOWN, buff=0.4, aligned_edge=LEFT)
        self.play(ShowCreation(ring), FadeIn(tries))
        self.say("Every wrong guess is a crash. On a forking server that's cheap, so 4096 is nothing.")
        self.beat()

        big = tr.quiz[1]["answer"]
        lab2 = mono(f"2^28 = {big:,}", 26, T.text).next_to(tries, DOWN, buff=0.7, aligned_edge=LEFT)
        ratio = mono(f"= {big // count:,} boards like this", 20, T.text_dim).next_to(lab2, DOWN, buff=0.2,
                                                                                     aligned_edge=LEFT)
        self.play(FadeOut(ring), VGroup(bf, tried, tail, target).animate.scale(0.08).move_to(LEFT * 5.6 + UP * 2.4), run_time=1.5)
        self.play(FadeIn(lab2), FadeIn(ratio))
        self.say("Libraries get 28 bits. That board shrinks to a speck next to the real search space.")
        self.beat()

        self.quiz("All three answers check out in VRIG's quiz grader.")
        self.outro()


class Mit83(AsmAdv, VrigScene):
    trace_name = "mit-83"
    quiz_labels = [
        "rax after lea rax, [rip + 0xff5]",
        "Still correct after a reload at 0x7fff00000000? (1 = yes)",
        "Does the absolute mov rcx still work? (1 = yes)",
    ]

    def construct(self):
        tr = self.load()
        self.heading("Code that works no matter where it's loaded.")
        lea = {l["addr"]: l for l in tr["lea"]["run1"]}

        def real_lea(s):
            # VRIG's emulator adds the current rip and masks to 32 bits, see
            # tests. Show what the CPU actually computes.
            l = lea.get(s["instr"]["addr"])
            return {l["reg"]: l["value"]} if l else None

        lst, regs = self.walk_setup(tr.instructions, ("rip", "rsp", "rbp", "rax", "rbx", "rcx"), size=20,
                                    show_bytes=False, addr_w=12, width=12)
        self.play(FadeIn(lst), FadeIn(regs))

        # the loaded image: three pages starting at the base
        base1, base2 = tr["bases"]
        img, pages = self.image(base1)
        img.move_to(RIGHT * 1.6 + DOWN * 1.55)
        abs_tick = self.abs_marker(tr["absolute"]).move_to(LEFT * 4.6 + DOWN * 1.9)
        self.play(FadeIn(img))
        self.say("PIE means the whole binary loads at a random base. Here it's 0x555555554000.")
        self.beat()

        math = VGroup()

        def on(s):
            a = s["instr"]["addr"]
            if a in lea:
                l = lea[a]
                eq = mono(f"{hx(l['next'], 12)} + {hx(l['disp'], 3)} = {hx(l['value'], 12)}", 18, T.text)
                eq.next_to(img, UP, buff=0.55 + 0.42 * len(math)).set_x(img.get_x())
                k = (l["value"] - base1) // 0x1000
                arr = pointer(pages[0].get_bottom(), pages[k].get_bottom(), T.leak, angle=1.1)
                self.play(FadeIn(eq, shift=UP * 0.1), ShowCreation(arr), run_time=0.8)
                math.add(VGroup(eq, arr))
                if len(math) == 1:
                    self.say("rip points at the next instruction. Add the offset and you land on a page in the image.")
                    self.beat()
            elif s["instr"]["operands"].startswith("rcx"):
                self.play(FadeIn(abs_tick))
                self.say("mov rcx bakes in a fixed number. Nothing about it depends on where the code is.")
                self.beat()

        self.walk(tr.steps, lst, regs, override=real_lea, on=on, rt=0.5)

        # reload somewhere else: rip-relative arrows ride along, rcx doesn't
        self.say("Now reload at the base from question two. The whole image moves together.")
        img2, pages2 = self.image(base2)
        img2.move_to(img).shift(RIGHT * 2.0)
        new_math = VGroup()
        for i, l in enumerate(tr["lea"]["run2"]):
            eq = mono(f"{hx(l['next'], 12)} + {hx(l['disp'], 3)} = {hx(l['value'], 12)}", 18, T.text)
            eq.next_to(img2, UP, buff=0.55 + 0.42 * i).set_x(img2.get_x())
            k = (l["value"] - base2) // 0x1000
            new_math.add(VGroup(eq, pointer(pages2[0].get_bottom(), pages2[k].get_bottom(), T.leak, angle=1.1)))
        self.play(Transform(img, img2), Transform(math, new_math), run_time=1.6)
        cross = Cross(abs_tick[0], stroke_width=4).set_stroke(T.crash)
        self.play(ShowCreation(cross))
        self.say("Same offsets, so lea still finds its data. The hardcoded address points where the binary isn't.")
        self.beat()

        self.quiz("VRIG's grader accepts all three.")
        self.outro()

    def image(self, base):
        pages = VGroup()
        for i, name in enumerate((".text", "data", "data")):
            r = Rectangle(1.55, 0.7).set_stroke(T.grid, 1.5)
            r.set_fill(T.text_section if i == 0 else T.local_var, 0.75)
            t = mono(f"{name} +0x{i:x}000", 13, T.text).move_to(r).shift(LIFT)
            pages.add(VGroup(r, t))
        pages.arrange(RIGHT, buff=0.04)
        lab = mono(f"base {hx(base, 12)}", 16, T.text_dim).next_to(pages, UP, buff=0.12).align_to(pages, LEFT)
        return VGroup(pages, lab), VGroup(*(p[0] for p in pages))

    def abs_marker(self, v):
        dot = Dot(radius=0.09).set_fill(T.saved_ret, 1)
        lab = mono(f"rcx = {hx(v)}", 16, T.saved_ret).next_to(dot, DOWN, buff=0.15)
        return VGroup(dot, lab)


class Mit86(AsmAdv, Vrig3DScene):
    trace_name = "mit-86"
    quiz_labels = [
        "Stops shellcode on the stack (1 = NX)",
        "Catches a linear overflow of the return address (2 = Canary)",
        "Still works with everything on (3 = data-only and logic bugs)",
        "TLS offset of the canary on x86-64",
    ]
    # which wall each attack runs into. None means it gets through.
    attacks = [
        ("shellcode on the stack", "NX"),
        ("linear overflow", "Canary"),
        ("ROP chain", "ASLR"),
        ("GOT overwrite", "RELRO"),
        ("data-only attack", None),
    ]

    def construct(self):
        tr = self.load()
        self.frame.reorient(0, 0)
        self.heading("Every mitigation at once, and what's left.")

        lst, regs = self.walk_setup(tr.instructions, ("rip", "rsp", "rbp", "rax"), size=20, show_bytes=False,
                                    addr_w=12, width=12)
        cs = VGroup(*(VGroup(mono(c["name"], 18, T.label), mono(c["value"], 18, T.mitigation)) for c in tr["checksec"]))
        for row in cs:
            row[1].next_to(row[0], RIGHT, buff=0.3).set_x(row[0].get_x() + 1.2, LEFT)
        cs.arrange(DOWN, aligned_edge=LEFT, buff=0.14).move_to(RIGHT * 3.6 + DOWN * 0.95)
        for row in cs:
            row[1].set_x(cs.get_left()[0] + 1.25, LEFT)
        cs_title = mono("checksec", 18, T.text_dim).next_to(cs, UP, buff=0.2, aligned_edge=LEFT)
        self.play(FadeIn(lst), FadeIn(regs), FadeIn(cs_title), FadeIn(cs, lag_ratio=0.1))
        self.say("The prologue of a fully hardened function. Watch where each mitigation shows up.")
        self.beat()

        steps = tr.steps
        ok = [s for s in steps if "error" not in s]
        bad = next(s for s in steps if "error" in s)

        def on(s):
            m = s["instr"]["mnemonic"]
            if m == "endbr64":
                self.say("endbr64 marks a legal indirect branch target. That's CET's IBT half.")
                self.beat()

        self.walk(ok, lst, regs, on=on, rt=0.55)

        # VRIG's emulator can't parse fs:0x28 and stops here. Draw the load.
        self.play(lst.focus(bad["instr"]["addr"]))
        tls = MemBox("fs: thread control block", 0, [("+0x00", "..."), ("+0x28", "canary")], role="cell_fill",
                     show_addr=False, size=16, width=1.9)
        tls.box(1).set_fill(T.canary, 0.85)
        tls.cells[1].val.set_color(T.background)
        tls.move_to(LEFT * 3.6 + DOWN * 1.2)
        self.play(FadeOut(VGroup(cs, cs_title)), FadeIn(tls))
        rax_txt = regs.rows["rax"][1]
        tag = mono("canary".rjust(12), 20, T.canary).move_to(rax_txt, aligned_edge=LEFT)
        self.play(TransformFromCopy(tls.cells[1].val, tag), FadeOut(rax_txt), run_time=0.9)
        self.say("mov rax, fs:0x28 reads the canary out of thread local storage, 0x28 bytes in.")
        self.beat()

        # [rbp-8], from the rbp VRIG's emulator computed
        rbp = bad["regs"]["rbp"]
        slot = MemBox("stack", rbp - 8, [("[rbp-8]", "canary"), ("saved rbp", rbp and "saved"), ("ret", "ret addr")],
                      size=16, width=1.9)
        slot.move_to(RIGHT * 2.4 + DOWN * 1.1)
        slot.box(1).set_fill(T.saved_fp, 0.85)
        slot.box(2).set_fill(T.saved_ret, 0.85)
        slot.cells[0].val.set_opacity(0)
        self.play(FadeIn(slot))
        store = next(i for i in tr.instructions if i["operands"].startswith("[rbp-8]"))
        self.play(lst.focus(store["addr"]))
        self.play(TransformFromCopy(tag, slot.cells[0].val.set_opacity(1).set_color(T.canary)),
                  slot.box(0).animate.set_fill(T.canary, 0.3))
        self.say("The canary sits between the locals and the saved registers. A linear overflow has to crush it first.")
        self.beat()
        clr = next(i for i in tr.instructions if i["mnemonic"] == "xor")
        zero = mono("0".rjust(12, "0"), 20, T.highlight).move_to(tag, aligned_edge=LEFT)
        self.play(lst.focus(clr["addr"]), FadeTransform(tag, zero))
        self.say("Then xor clears rax so the canary doesn't linger in a register.")
        self.beat()

        self.walls()
        self.quiz("All four answers match VRIG's key.")
        self.frame.to_default_state()
        self.outro()

    def walls(self):
        tr, frame = self.tr, self.frame
        self.clear_stage()
        self.play(frame.animate.reorient(-28, 62, 0, center=(0.4, 0, 0.6), height=10), run_time=2)
        names = [b["name"] for b in tr["blocks"]]
        walls = {}
        xs = np.linspace(-2.6, 3.4, len(names))
        grp = Group()
        for x, n in zip(xs, names):
            w = Prism(0.14, 5.4, 1.7, color=T.mitigation, opacity=0.35).move_to([x, 0, 0.85])
            lab = billboard(mono(n, 22, T.mitigation).move_to([x, 2.9, 2.0]), frame)
            walls[n] = (w, lab)
            grp.add(w, lab)
        goal = Prism(1.2, 1.0, 0.5, color=T.win, opacity=0.9).move_to([5.3, -2.0, 0.25])
        goal_lab = billboard(mono("is_admin = 1", 20, T.text).move_to([5.3, -2.0, 1.0]), frame)
        self.play(LaggedStart(*(FadeIn(m, shift=OUT * 0.4) for m in grp), lag_ratio=0.08))
        self.say("Line the mitigations up as walls. Send each attack class at them.")
        self.beat()

        lanes = np.linspace(2.0, -2.0, len(self.attacks))
        for (what, stop), y in zip(self.attacks, lanes):
            start = np.array([-5.6, y, 0.1])
            src = billboard(mono(what, 18, T.attacker_bytes).move_to(start + OUT * 0.45 + LEFT * 0.2), frame)
            self.play(FadeIn(src), run_time=0.4)
            if stop:
                w, _ = walls[stop]
                end = np.array([w.get_x() - 0.1, y, 0.9])
                path = arc3d(start, end, lift=1.4, color=T.attacker_bytes, width=4)
                self.play(ShowCreation(path), run_time=0.9)
                self.play(w.animate.set_color(T.crash).set_opacity(0.7), Flash(end, color=T.crash), run_time=0.5)
                self.play(w.animate.set_color(T.mitigation).set_opacity(0.35), run_time=0.3)
            else:
                end = goal.get_top() + OUT * 0.05
                path = arc3d(start, end, lift=2.6, color=T.win, width=5)
                self.say("A data-only attack never touches a code pointer, a return address, or the GOT. No wall checks data.")
                self.play(FadeIn(goal), FadeIn(goal_lab))
                self.play(ShowCreation(path), run_time=1.6)
                self.play(Flash(end, color=T.win, flash_radius=0.6))
                self.beat()
        self.play(frame.animate.reorient(-34, 60, 0, center=(0.2, -0.8, 0.6), height=11.5), run_time=2)
        self.beat()
        self.play(frame.animate.reorient(0, 0, 0, center=ORIGIN, height=8), run_time=1.5)


# ======================================================================
# unit 16 / 17: advanced code reuse
# ======================================================================

class Adv91(AsmAdv, VrigScene):
    trace_name = "adv-91"
    quiz_labels = [
        "eax after loading obj1's vptr",
        "edx after mov edx, [eax]",
        "esi, the vfgadget from obj2's vtable",
    ]

    def construct(self):
        tr = self.load()
        self.heading("Chaining virtual calls the program already makes.")
        lst, regs = self.walk_setup(tr.instructions, ("eip", "ecx", "eax", "edx", "ebx", "esi"), size=17)
        regs.next_to(lst, DOWN, buff=0.35, aligned_edge=LEFT)

        mem = {m["addr"]: m["value"] for m in tr["initialMemory"]}
        o1 = MemBox("obj1 @ 0x0804c000", 0x0804c000, [("vptr", mem[0x0804c000])], role="local_var", size=15, width=1.7, show_addr=False)
        o2 = MemBox("obj2 @ 0x0804c010", 0x0804c010, [("vptr", mem[0x0804c010])], role="local_var", size=15, width=1.7, show_addr=False)
        v1 = MemBox("vtable1 @ 0x08049000", 0x08049000, [("[0]", mem[0x08049000]), ("[1]", mem[0x08049004])],
                    role="gadget", size=15, width=1.7, show_addr=False)
        v2 = MemBox("vtable2 @ 0x08049010", 0x08049010, [("[0]", mem[0x08049010]), ("[1]", mem[0x08049014])],
                    role="gadget", size=15, width=1.7, show_addr=False)
        # method names come from the exercise's source comment
        names = {0x08048100: "speak", 0x08048200: "act", 0x08048300: "gadget1", 0x08048400: "gadget2"}
        fns = VGroup(*(VGroup(mono(n, 16, T.text), mono(hx(a), 13, T.text_dim)).arrange(DOWN, buff=0.05)
                       for a, n in names.items()))
        fn_box = {}
        for (a, _), f in zip(names.items(), fns):
            bg = SurroundingRectangle(f, buff=0.1).set_stroke(T.text_section, 2).set_fill(T.text_section, 0.35)
            f.add_to_back(bg)
            fn_box[a] = f
        fns.arrange(DOWN, buff=0.25)

        o1.move_to(RIGHT * 0.9 + UP * 1.6)
        o2.move_to(RIGHT * 0.9 + DOWN * 1.2)
        v1.move_to(RIGHT * 3.7 + UP * 1.4)
        v2.move_to(RIGHT * 3.7 + DOWN * 1.4)
        fns.move_to(RIGHT * 6.3 + DOWN * 0.1)
        for b in (o1, o2, v1, v2):
            b.cells.shift(RIGHT * 0.3)
            b.title.shift(RIGHT * 0.3)
        self.play(FadeIn(lst), FadeIn(regs))
        self.play(LaggedStart(FadeIn(o1), FadeIn(o2), FadeIn(v1), FadeIn(v2), FadeIn(fns), lag_ratio=0.15))
        self.say("Two C++ objects. The first word of each is a vptr into a table of method addresses.")
        self.beat()

        where = {}
        for b in (o1, o2, v1, v2):
            for i in range(len(b.cells)):
                where[b.base + 4 * i] = (b, i)
        arrows = VGroup()

        def on(s):
            for rd in s.get("memReads", []):
                b, i = where[rd["addr"]]
                tgt = rd["value"]
                if tgt in fn_box:
                    end = fn_box[tgt].get_left()
                else:
                    tb, _ = where[tgt]
                    end = tb.cells[0].get_left()
                a = Arrow(b.box(i).get_right(), end, buff=0.08, stroke_width=3).set_color(T.pointer)
                self.play(Indicate(b.box(i), color=T.highlight, scale_factor=1.08), GrowArrow(a), run_time=0.6)
                arrows.add(a)
            ins = s["instr"]
            if ins["addr"] == 0x08048005:
                self.say("mov eax, [ecx] follows the vptr. eax now holds the vtable's address.")
                self.beat()
            elif ins["addr"] == 0x08048007:
                self.say("Index the vtable and you have a method. This is every virtual call in C++.")
                self.beat()
            elif ins["addr"] == 0x08048013:
                self.say("obj2's table, slot one. COOP calls this a vfgadget.")
                self.beat()

        self.walk(tr.steps, lst, regs, on=on, rt=0.55)

        # COOP: forge objects whose vptrs point into real vtables
        self.clear_stage()
        self.say("COOP forges objects. Each fake vptr points into a real vtable, so each call is one the program could make.")
        fakes = VGroup()
        targets = [(0x08049010, 0, "gadget1"), (0x08049010, 1, "gadget2"), (0x08049000, 1, "act")]
        for k, (vt, slot, _) in enumerate(targets):
            fakes.add(MemBox(f"fake obj {k}", 0, [("vptr", vt + 4 * slot)], role="attacker_bytes",
                             show_addr=False, size=16, width=1.8))
        fakes.arrange(RIGHT, buff=0.9).move_to(UP * 1.8)
        loop = mono("for (obj : list) obj->vfunc();", 20, T.text).move_to(UP * 3.0)
        cfi = VGroup(*(mono("CFI: real vtable entry?", 15, T.mitigation) for _ in targets))
        tabs = VGroup()
        for f, (vt, slot, name) in zip(fakes, targets):
            t = MemBox(name, 0, [("in .text", hx({"gadget1": 0x08048300, "gadget2": 0x08048400, "act": 0x08048200}[name]))],
                       role="text_section", show_addr=False, size=15, width=1.8)
            t.next_to(f, DOWN, buff=1.6)
            tabs.add(t)
        for c, t in zip(cfi, tabs):
            c.next_to(t, DOWN, buff=0.25)
        self.play(FadeIn(loop), LaggedStart(*map(FadeIn, fakes), lag_ratio=0.2))
        for f, t, c in zip(fakes, tabs, cfi):
            a = Arrow(f.get_bottom(), t.get_top(), buff=0.1).set_color(T.attacker_bytes)
            self.play(GrowArrow(a), FadeIn(t), run_time=0.6)
            chk = mono("yes", 15, T.win).next_to(c, RIGHT, buff=0.15)
            self.play(FadeIn(c), FadeIn(chk), run_time=0.4)
        self.say("Coarse CFI only asks whether the target is a legitimate virtual method. It always is.")
        self.beat()

        self.quiz("The emulator's eax, edx, and esi are the three answers VRIG accepts.")
        self.outro()


class Adv2_95(AsmAdv, Vrig3DScene):
    trace_name = "adv2-95"
    quiz_labels = [
        "First instruction byte when you jump to xor + 1",
        "NOPs in a row from there",
        "Permission flags on a typical JIT page (R + W + X)",
    ]

    def construct(self):
        tr = self.load()
        frame = self.frame
        frame.reorient(0, 0)
        self.heading("Constants in JavaScript become bytes in an executable page.")

        js = VGroup(*(mono(l, 20, T.attacker_bytes) for l in tr["source"][2:4])).arrange(DOWN, aligned_edge=LEFT)
        lst, regs = self.walk_setup(tr.instructions, ("eip", "eax"))
        js.next_to(lst, DOWN, buff=0.7, aligned_edge=LEFT)
        js_lab = mono("JavaScript the attacker wrote", 16, T.text_dim).next_to(js, UP, buff=0.15, aligned_edge=LEFT)
        self.play(FadeIn(js_lab), FadeIn(js))
        self.play(FadeIn(lst), FadeIn(regs))
        self.say("The JIT turns each XOR into xor eax, imm32. The constant goes into the code as raw bytes.")
        self.walk(tr.steps, lst, regs, rt=0.6)
        self.say("Run the way the JIT meant, eax just flips back and forth. Harmless.")
        self.beat()

        # -- the page as bytes, read two ways --------------------------------
        self.clear_stage()
        page, base = tr["page"], tr["pageBase"]
        w = CELL + GAP
        cells = VGroup(*(ByteCell(b) for b in page)).arrange(RIGHT, buff=GAP).move_to(ORIGIN)
        x0 = cells[0].get_x()
        ins_offs = [i["addr"] - base for i in tr.instructions]
        for i in tr.instructions:
            off = i["addr"] - base
            cells[off].paint("text_section")
            for k in range(1, len(i["bytes"])):
                if i["mnemonic"] in ("xor", "mov"):
                    cells[off + k].paint("attacker_bytes")
        self.play(FadeIn(cells, lag_ratio=0.03))
        self.say("Same page as bytes. Opcodes in brown, the attacker's constants in gold.")
        self.beat()

        self.play(frame.animate.reorient(0, 38, 0, center=(0, -0.2, 0.3), height=7.0), run_time=2)
        rwx = billboard(mono("JIT page  rwx", 22, T.crash).move_to(cells.get_left() + RIGHT * 1.0 + UP * 2.1 + OUT * 0.6), frame)
        self.play(FadeIn(rwx))

        def bar(off, n, y, role, text, size=15):
            width = n * w - GAP
            slab = Prism(width, 0.5, 0.16, color=getattr(T, role), opacity=0.9)
            slab.move_to([x0 - CELL / 2 + off * w + width / 2, y, 0.08])
            lab = billboard(mono(text, size, T.text).move_to(slab.get_center() + OUT * 0.42), frame)
            return Group(slab, lab)

        aligned = Group(*(bar(i["addr"] - base, len(i["bytes"]), 1.05, "text_section",
                              f"{i['mnemonic']} {i['operands']}".strip(), 14) for i in tr.instructions))
        self.play(LaggedStart(*(FadeIn(a, shift=OUT * 0.3) for a in aligned), lag_ratio=0.15))
        self.say("Decode from the start of each instruction and you get what the JIT emitted.")
        self.beat()

        entry = tr["entry"] - base
        jump = arc3d(cells[entry].get_center() + DOWN * 2.0 + LEFT * 1.0, cells[entry].get_center() + DOWN * 0.3 + OUT * 0.05,
                     lift=1.2, color=T.crash)
        tag = billboard(mono(f"jmp {hx(tr['entry'])}", 18, T.crash).move_to(cells[entry].get_center() + DOWN * 2.0 + LEFT * 2.4 + OUT * 0.1), frame)
        self.play(ShowCreation(jump), FadeIn(tag))
        self.say("Now jump one byte into the first xor. The CPU decodes whatever it finds there.")
        self.beat()

        unaligned = Group()
        for d in tr["unaligned"]:
            role = "attacker_bytes" if d["text"] == "nop" else "gadget"
            txt = d["text"] if d["len"] == 1 else d["text"].replace(", ", ",\n")
            unaligned.add(bar(d["off"], d["len"], -1.05, role, txt, 13))
        for u in unaligned:
            self.play(FadeIn(u, shift=OUT * 0.3), run_time=0.28)
        self.say("Three NOPs, then cmp al eats the next opcode. The pattern repeats down the page as a NOP sled.")
        self.beat()
        self.play(frame.animate.reorient(-18, 50, 0, center=(0, -0.2, 0.3), height=8.2), run_time=2.5)
        self.say("The JIT wrote the page RWX, so NX has nothing to stop. Swap the constants and the sled ends in shellcode.")
        self.beat()
        self.play(frame.animate.to_default_state(), run_time=1.5)

        self.quiz("All three answers pass VRIG's check.")
        self.outro()


class Adv2_97(AsmAdv, Vrig3DScene):
    trace_name = "adv2-97"
    quiz_labels = [
        "Address the speculative load touches with x = 64",
        "Is the value still in a register after rollback? (1 = yes)",
        "array2 offset that gets cached for secret 0x41",
    ]

    def construct(self):
        tr = self.load()
        frame = self.frame
        frame.reorient(0, 0)
        self.heading("The CPU runs ahead of a bounds check, and the cache remembers.")

        lst, regs = self.walk_setup(tr.instructions, ("eip", "eax", "ebx", "edx"), size=18)
        flags = Flags().next_to(regs, DOWN, buff=0.25)
        # array1 and the byte 64 past it
        size = next(m["value"] for m in tr["initialMemory"] if m["addr"] == 0x0804a000)
        a1 = VGroup(*(ByteCell(None) for _ in range(size))).arrange(RIGHT, buff=GAP).scale(0.8)
        dots = mono("...", 20, T.text_dim)
        sec = ByteCell(tr["secret"], "leak").scale(0.8)
        strip = VGroup(a1, dots, sec).arrange(RIGHT, buff=0.25).move_to(DOWN * 1.9 + RIGHT * 0.4)
        a1_lab = mono(f"array1[{size}] @ 0x0804b000", 16, T.label).next_to(a1, UP, buff=0.15, aligned_edge=LEFT)
        sec_lab = mono("array1[64]", 16, T.leak).next_to(sec, UP, buff=0.15)
        size_box = mono(f"array1_size = {size}", 18, T.mitigation).next_to(a1, DOWN, buff=0.2, aligned_edge=LEFT)
        sec.set_opacity(0)
        sec_lab.set_opacity(0)
        self.play(FadeIn(lst), FadeIn(regs), FadeIn(flags), FadeIn(a1), FadeIn(a1_lab), FadeIn(size_box),
                  FadeIn(dots))
        self.say("The victim checks x against array1_size before it reads. The attacker passes x = 64.")
        self.beat()

        def on(s):
            m = s["instr"]["mnemonic"]
            if m == "cmp":
                self.play(Indicate(size_box, color=T.highlight))
            if m == "jge":
                self.say("64 isn't below 16. jge is taken and the program skips the loads. Architecturally, nothing leaks.")
                self.beat()

        arch = self.walk(tr.steps, lst, regs, flags=flags, on=on, rt=0.6)

        # replay the window the CPU actually ran before the branch resolved
        self.say("But the predictor was trained on in-bounds calls. Before cmp resolves, the CPU guesses not taken and keeps going.")
        self.beat()
        spec = tr["spec"]["steps"]
        at_branch = tr.steps[1]["regs"]
        sec.set_opacity(1)
        sec_lab.set_opacity(1)
        self.play(FadeIn(sec), FadeIn(sec_lab), *regs.set("eax", at_branch["eax"], "label"))

        def on_spec(s):
            if s["instr"]["mnemonic"] == "mov" and s["instr"]["operands"].startswith("ebx"):
                rd = s["memReads"][0]
                lab = mono(f"read {hx(rd['addr'])}", 16, T.leak).next_to(sec, DOWN, buff=0.2)
                self.play(Indicate(sec, color=T.leak, scale_factor=1.3), FadeIn(lab))
                self.say("array1[64] is past the end. The load runs anyway and pulls in the secret byte.")
                self.beat()
            elif s["instr"]["operands"].startswith("edx"):
                rd = s["memReads"][0]
                self.probe_lab = mono(f"touch array2 + {hx(rd['addr'] - tr['array2'], 4)}", 18, T.leak)
                self.probe_lab.next_to(regs, LEFT, buff=0.5)
                self.play(FadeIn(self.probe_lab))
                self.say("Shift by 8 and use it as an index. One line of array2 lands in the cache.")
                self.beat()

        self.walk(spec, lst, regs, init_regs=at_branch, role="leak", on=on_spec, rt=0.6, focus_color=T.leak)

        squash = [regs.set(r, arch[r], "crash")[0] for r in ("ebx", "edx")]
        self.play(*squash, lst.focus(0x0804801b))
        self.say("Then the branch resolves. Registers roll back to what the real path computed. The cache line stays.")
        self.beat()

        self.cache_act()
        self.frame.to_default_state()
        self.quiz("VRIG accepts all three.")
        self.outro()

    def cache_act(self):
        tr, frame = self.tr, self.frame
        self.clear_stage()
        n, gap = 16, 0.36
        lines = Group()
        for i in range(256):
            c = Prism(0.28, 0.28, 0.12, color=T.cell_fill, opacity=1)
            c.move_to([(i % n - 7.5) * gap, (7.5 - i // n) * gap, 0.06])
            lines.add(c)
        lines.shift(LEFT * 1.0 + UP * 0.8)
        hit = tr["secret"]
        self.play(frame.animate.reorient(-10, 32, 0, center=(-1.0, -0.2, 0.3), height=8.5), run_time=1.5)
        title = mono("array2: 256 cache lines, one per byte value", 20, T.label).to_corner(UR, buff=0.4).fix_in_frame()
        self.play(FadeIn(lines, lag_ratio=0.002), FadeIn(title), run_time=1.5)
        self.play(lines[hit].animate.set_color(T.leak), run_time=0.6)
        self.say("Every possible secret maps to its own line. The speculative access warmed exactly one.")
        self.beat()

        # flush+reload: time a read of every line. slow = miss, short = hit
        rng = random.Random(97)
        anims = []
        for i, c in enumerate(lines):
            h = 0.12 if i == hit else rng.uniform(0.3, 0.5)
            anims.append(c.animate.stretch(h / 0.12, 2, about_edge=IN).set_color(T.leak if i == hit else T.label))
        self.say("Now the attacker times a read of every line. Misses are slow and tall. One read comes back fast.")
        self.play(LaggedStart(*anims, lag_ratio=0.004), run_time=3.5)
        res = mono(f"fastest line: {hx(hit, 2)}  so the secret byte is {hx(hit, 2)}", 22, T.leak)
        res.next_to(title, DOWN, buff=0.3).align_to(title, RIGHT).fix_in_frame()
        # the hit is short and hides among the misses, so stand a beam on it
        top = lines[hit].get_center() + OUT * 0.06
        ring = Line(top, top + OUT * 2.2).set_stroke(T.leak, 6)
        self.play(FadeIn(res), ShowCreation(ring))
        self.play(frame.animate.reorient(-30, 45, 0, center=(-1.0, -0.2, 0.3), height=8.5), run_time=2.5)
        self.beat()
        self.play(frame.animate.reorient(0, 0, 0, center=ORIGIN, height=8), run_time=1.5)


class Adv2_98(AsmAdv, VrigScene):
    trace_name = "adv2-98"
    quiz_labels = [
        "Worst case connections to leak a 4-byte canary",
        "What a stop gadget does (2 = hang)",
        "First byte of a glibc canary",
    ]

    def construct(self):
        tr = self.load()
        self.heading("Exploit a server you don't have the binary for.")
        lst, regs = self.walk_setup(tr.instructions, ("eip", "esp", "eax", "ebx", "ecx", "edx"), size=17)
        self.play(FadeIn(lst), FadeIn(regs))
        self.say("The listing walks BROP's phases. First, four registers hold the canary bytes, one guess each.")

        def on(s):
            ins = s["instr"]
            if ins["mnemonic"] == "call":
                self.say("call then jmp is the PLT signature. VRIG's run ends at the call, the resolver isn't in the listing.")
                self.beat()

        self.walk(tr.steps, lst, regs, on=on, rt=0.5)

        # phase 1: byte at a time against a forking server
        self.clear_stage()
        server = VGroup(RoundedRectangle(width=3.0, height=1.2, corner_radius=0.15).set_stroke(T.label, 2),
                        mono("server, forks per connection", 16, T.label))
        server[1].move_to(server[0])
        server.move_to(LEFT * 4.4 + UP * 1.8)
        sub = mono("every child has the same canary", 16, T.text_dim).next_to(server, DOWN, buff=0.15)
        can = VGroup(*(ByteCell(None) for _ in tr["canary"])).arrange(RIGHT, buff=GAP).scale(1.4)
        can.move_to(RIGHT * 1.2 + UP * 1.6)
        can_lab = mono("canary", 20, T.canary).next_to(can, UP, buff=0.2)
        self.play(FadeIn(server), FadeIn(sub), FadeIn(can), FadeIn(can_lab))
        self.say("A crash kills one child. The next connection gets a fresh fork with the same canary.")
        self.beat()

        guess = mono("guess 00", 24, T.attacker_bytes).next_to(can, DOWN, buff=0.6)
        tries_lab = mono("", 20, T.text)
        total = 0
        rows = VGroup()
        self.add(guess)
        for k, (byte, tries) in enumerate(zip(tr["canary"], tr["tries"])):
            guess.next_to(can[k], DOWN, buff=0.6)
            cnt = ValueTracker(0)

            def updater(k, cnt):
                # two-arg updaters get dt, so bind k and cnt out here
                return lambda m: m.become(mono(f"guess {int(cnt.get_value()):02x}", 24, T.attacker_bytes)
                                          .next_to(can[k], DOWN, buff=0.6))

            guess.add_updater(updater(k, cnt))
            rt = 0.4 + 2.0 * tries / 256
            self.play(cnt.animate.set_value(byte), can[k].box.animate.set_fill(T.crash, 0.6), run_time=rt,
                      rate_func=linear)
            guess.clear_updaters()
            new = can[k].relabel(byte)
            self.play(Transform(can[k].label, new), can[k].box.animate.set_fill(T.win, 0.85), run_time=0.4)
            total += tries
            row = mono(f"byte {k}: {hx(byte, 2)} after {tries} {'try' if tries == 1 else 'tries'}", 18, T.text)
            rows.add(row)
            row.move_to(DOWN * 0.4 + DOWN * 0.38 * k + RIGHT * 1.2)
            self.play(FadeIn(row, shift=UP * 0.1), run_time=0.3)
            if k == 0:
                self.say("Wrong guesses crash. A right one keeps the connection alive, so lock it in and move to the next byte.")
                self.beat()
        self.play(FadeOut(guess))
        tot = mono(f"{total} connections. worst case 4 x 256 = {tr.quiz[0]['answer']}", 20, T.win)
        tot.next_to(rows, DOWN, buff=0.35)
        self.play(FadeIn(tot))
        self.say("Byte zero was 00, the glibc terminator. Guessing per byte turns four billion into about a thousand.")
        self.beat()

        # phases 2 to 4
        self.clear_stage()
        probes = [i for i in tr.instructions if i["mnemonic"] == "nop"]
        cards = VGroup()
        for p, (res, role) in zip(probes, [("crash", "crash"), ("hang = stop gadget", "win")]):
            cards.add(VGroup(mono(f"ret -> {hx(p['addr'])}", 20, T.text), mono(res, 20, getattr(T, role)))
                      .arrange(RIGHT, buff=0.5))
        cards.arrange(DOWN, aligned_edge=LEFT, buff=0.3).move_to(UP * 2.0 + LEFT * 2.5)
        ph2 = mono("phase 2: scan .text", 18, T.text_dim).next_to(cards, UP, buff=0.25, aligned_edge=LEFT)
        self.play(FadeIn(ph2), LaggedStart(*map(FadeIn, cards), lag_ratio=0.4))
        self.say("Phase two returns into one address at a time. Most crash. A hang means a stop gadget.")
        self.beat()

        plt = [i for i in tr.instructions if i["mnemonic"] in ("call", "jmp")]
        sig = VGroup(*(mono(f"{' '.join(f'{b:02x}' for b in i['bytes'])}   {i['mnemonic']} {i['operands']}", 20, T.gadget)
                       for i in plt)).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        sig.next_to(cards, DOWN, buff=0.9, aligned_edge=LEFT)
        ph3 = mono("phase 3: find the PLT", 18, T.text_dim).next_to(sig, UP, buff=0.25, aligned_edge=LEFT)
        self.play(FadeIn(ph3), FadeIn(sig))
        self.beat(pause=0.5)

        dump_src = next(l for l in tr["source"] if l.startswith("write("))
        dump = mono(dump_src, 22, T.win).move_to(RIGHT * 3.2 + UP * 0.2)
        ph4 = mono("phase 4", 18, T.text_dim).next_to(dump, UP, buff=0.25, aligned_edge=LEFT)
        stream = VGroup(*(ByteCell(b, "text_section").scale(0.7) for b in tr["instructions"][0]["bytes"] +
                          tr["instructions"][1]["bytes"])).arrange(RIGHT, buff=0.03)
        stream.next_to(dump, DOWN, buff=0.5)
        self.play(FadeIn(ph4), FadeIn(dump))
        self.play(LaggedStart(*(FadeIn(c, shift=RIGHT * 0.5) for c in stream), lag_ratio=0.1), run_time=1.5)
        self.say("Phase four calls write@PLT on the socket and the server sends its own binary back. Then it's normal ROP.")
        self.beat()

        self.quiz("VRIG takes all three.")
        self.outro()


class Adv2_100(AsmAdv, VrigScene):
    trace_name = "adv2-100"
    quiz_labels = [
        "Signal number for SIGSYS",
        "write's number in the 64-bit syscall table",
        "PROT_READ | PROT_WRITE | PROT_EXEC",
    ]

    def construct(self):
        tr = self.load()
        self.heading("A syscall filter, what it blocks, and what it lets through.")
        lst, regs = self.walk_setup(tr.instructions, ("eip", "eax", "ebx", "ecx", "edx"), size=17)
        self.play(FadeIn(lst), FadeIn(regs))

        # filter panel built from the seccomp_rule_add lines in the source
        allowed = [l.split("SCMP_SYS(")[1].split(")")[0] for l in tr["source"] if "SCMP_SYS(" in l]
        box = RoundedRectangle(width=4.4, height=2.2, corner_radius=0.15).set_stroke(T.mitigation, 2)
        head = mono("seccomp-BPF filter", 18, T.mitigation).next_to(box.get_top(), DOWN, buff=0.15)
        chips = VGroup(*(mono(a, 18, T.text) for a in allowed)).arrange(RIGHT, buff=0.45)
        chips_lab = mono("ALLOW", 15, T.text_dim).next_to(chips, LEFT, buff=0.3)
        default = mono("default: SCMP_ACT_KILL", 16, T.crash)
        VGroup(VGroup(chips_lab, chips), default).arrange(DOWN, buff=0.35).move_to(box).shift(DOWN * 0.2)
        filt = VGroup(box, head, chips_lab, chips, default).move_to(RIGHT * 3.6 + DOWN * 1.25)
        self.play(FadeIn(filt))
        self.say("Every syscall goes through this filter first. Anything not on the allow list kills the process.")
        self.beat()

        def on(s):
            if s["instr"]["mnemonic"] == "int":
                eax = tr["killed"]["eax"]
                tok = mono(f"eax = {eax}  execve", 20, T.attacker_bytes).next_to(filt, UP, buff=0.3)
                self.play(TransformFromCopy(regs.rows["eax"][1], tok))
                self.play(tok.animate.move_to(box.get_center() + UP * 0.1).scale(0.9), run_time=0.7)
                self.play(Indicate(default, color=T.crash, scale_factor=1.2), FadeOut(tok))
                verdict = mono(f"KILL  SIGSYS ({tr.quiz[0]['answer']})", 22, T.crash).next_to(filt, UP, buff=0.3)
                self.play(FadeIn(verdict, scale=1.2), Flash(box.get_top(), color=T.crash))
                self.say("execve is 11 and it isn't allowed. VRIG's run stops at the int 0x80. The kernel sends SIGSYS.")
                self.beat()
                self.verdict = verdict

        kill_at = tr["killed"]["at"]
        self.walk([s for s in tr.steps if s["instr"]["addr"] <= kill_at], lst, regs, on=on, rt=0.5)

        # second run: the allowed path, starting fresh
        self.say("Second run, starting at the write half. Same filter.")
        init = tr["allowed"]["init"]["regs"]
        self.play(FadeOut(self.verdict), *[regs.set(r, init[r], "label")[0] for r in ("eax", "ebx", "ecx", "edx")])

        def on_ok(s):
            if s["instr"]["mnemonic"] == "nop":
                eax = s["regs"]["eax"]
                tok = mono(f"eax = {eax}  write", 20, T.attacker_bytes).next_to(filt, UP, buff=0.3)
                self.play(TransformFromCopy(regs.rows["eax"][1], tok))
                self.play(tok.animate.move_to(box.get_center() + UP * 0.1).scale(0.9), run_time=0.7)
                w = chips[allowed.index("write")]
                self.play(Indicate(w, color=T.win, scale_factor=1.3), FadeOut(tok))
                out = mono(f"{s['regs']['edx']} bytes from {hx(s['regs']['ecx'])} to fd {s['regs']['ebx']}", 20, T.win)
                out.next_to(filt, UP, buff=0.3)
                self.play(FadeIn(out, shift=RIGHT * 0.3))
                self.say("write is allowed, so 4096 bytes of memory go out to stdout. No shell needed to leak the data.")
                self.beat()

        self.walk(tr["allowed"]["steps"], lst, regs, init_regs=init, on=on_ok, rt=0.5)

        # escape ideas: two syscall tables, and mprotect's bits
        self.clear_stage()
        mp = int(tr.quiz[2]["question"].split("syscall ")[1].split(" ")[0])
        t32 = VGroup(mono("int 0x80  (32-bit table)", 20, T.label),
                     mono(f"4    write", 20, T.text), mono(f"11   execve", 20, T.text), mono(f"{mp}  mprotect", 20, T.text))
        t64 = VGroup(mono("syscall  (64-bit table)", 20, T.label), mono(f"{tr.quiz[1]['answer']}    write", 20, T.text))
        for t in (t32, t64):
            t.arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        VGroup(t32, t64).arrange(RIGHT, buff=1.4, aligned_edge=UP).move_to(UP * 1.4)
        self.play(FadeIn(t32), FadeIn(t64))
        self.say("Same call, different numbers. A filter that only knows the 64-bit table can be dodged through int 0x80.")
        self.beat()

        bits = VGroup()
        for name, v in (("PROT_READ", 1), ("PROT_WRITE", 2), ("PROT_EXEC", 4)):
            bits.add(VGroup(mono(name, 20, T.text), mono(str(v), 22, T.attacker_bytes)).arrange(DOWN, buff=0.12))
        bits.arrange(RIGHT, buff=0.8).move_to(DOWN * 1.0)
        tot = mono(f"= {tr.quiz[2]['answer']}  rwx", 24, T.crash).next_to(bits, RIGHT, buff=0.6)
        self.play(LaggedStart(*map(FadeIn, bits), lag_ratio=0.3), run_time=1.2)
        self.play(FadeIn(tot))
        self.say("If mprotect is allowed, one call with 7 turns a data page executable, and shellcode runs inside the sandbox.")
        self.beat()

        self.quiz("All three match VRIG's answers.")
        self.outro()


class Adv2_102(AsmAdv, VrigScene):
    trace_name = "adv2-102"
    quiz_labels = [
        "Turing complete without touching a code pointer? (1 = yes)",
        "What mov eax, [edx] at 0x08048012 is (1 = LOAD)",
        "Does CFI catch it? (1 = yes)",
    ]

    def construct(self):
        tr = self.load()
        self.heading("The program's own loop, fed records the attacker wrote.")
        lst, regs = self.walk_setup(tr.instructions, ("eip", "ebx", "eax", "edx", "ecx"), size=16)
        flags = Flags(16).next_to(regs, DOWN, buff=0.2)
        self.play(FadeIn(lst), FadeIn(regs), FadeIn(flags))

        recs = tr["records"]
        fields = ("type", "src", "dst", "next")
        boxes = VGroup()
        for r in recs:
            b = MemBox(f"op @ {hx(r['at'])}", r["at"], [(f, 0) for f in fields], show_addr=False, size=14, width=1.6)
            boxes.add(b)
        boxes.arrange(DOWN, buff=0.45).move_to(RIGHT * 0.7 + DOWN * 0.6)

        def ascii(v):
            return bytes((v >> (8 * i)) & 0xff for i in range(4)).rstrip(b"\0").decode()

        sec = MemBox(f"secret @ {hx(tr['secretAddr'])}", tr["secretAddr"],
                     [(f'"{ascii(v)}"', v) for v in tr["secret"]], role="leak", show_addr=False, size=14, width=1.6)
        out = MemBox(f"out @ {hx(tr['outAddr'])}", tr["outAddr"], [("", 0), ("", 0)], show_addr=False, size=14,
                     width=1.6)
        VGroup(sec, out).arrange(DOWN, buff=0.45).move_to(RIGHT * 4.6 + DOWN * 1.35)
        self.play(FadeIn(boxes), FadeIn(sec), FadeIn(out))
        self.say("process() walks a list of op records. As shipped the record is empty, so the loop reads zeros and quits.")
        self.walk(tr.steps, lst, regs, flags=flags, rt=0.3)
        self.beat()

        # the overflow rewrites the records
        anims = []
        for b, r in zip(boxes, recs):
            for i, f in enumerate(fields):
                anims.append(b.set_value(i, r[f], T.attacker_bytes))
        self.play(LaggedStart(*anims, lag_ratio=0.05), run_time=1.6)
        self.say("Now overflow into the list. Two LOAD records, each copying a secret word into the output buffer.")
        self.beat()

        where = {}
        for b in (*boxes, sec, out):
            for i in range(len(b.cells)):
                where[b.base + 4 * i] = (b, i)
        attack_init = tr["attack"]["init"]["regs"]
        self.play(*[regs.set(r, attack_init[r], "label")[0] for r in ("ebx", "eax", "edx", "ecx")])

        def on(s):
            a = s["instr"]["addr"]
            if a == 0x08048012:
                b, i = where[s["memReads"][0]["addr"]]
                self.play(Indicate(b.box(i), color=T.leak, scale_factor=1.1), run_time=0.4)
            elif a == 0x08048014:
                wr = s["memWrites"][0]
                b, i = where[wr["addr"]]
                self.play(TransformFromCopy(regs.rows["eax"][1], b.cells[i].val), b.set_value(i, wr["value"], T.leak),
                          run_time=0.6)
                if i == 0:
                    self.say("The LOAD gadget reads where src says and the store writes where dst says. Both addresses are the attacker's.")
                    self.beat()
            elif a == 0x08048016 and s["regs"]["ebx"]:
                nb = where[s["regs"]["ebx"]][0]
                arr = Arrow(boxes[0].box(3).get_right(), nb.title.get_right(), buff=0.1).set_color(T.pointer)
                self.play(GrowArrow(arr), run_time=0.4)

        self.walk(tr["attack"]["steps"], lst, regs, init_regs=attack_init, flags=flags, on=on, rt=0.35)
        self.say("The secret is in the output buffer. Every instruction that ran is in the original loop.")
        checks = VGroup(*(mono("ok", 14, T.win).next_to(r, RIGHT, buff=0.2) for r in lst.rows))
        for c in checks:
            c.set_x(lst.get_right()[0] + 0.25, LEFT)
        self.play(LaggedStart(*map(FadeIn, checks), lag_ratio=0.08))
        self.say("No return address, vtable, or function pointer changed. CFI has nothing to flag.")
        self.beat()

        self.quiz("VRIG accepts all three.")
        self.outro()


# ======================================================================
# unit 18: kernel
# ======================================================================

class Kern103(AsmAdv, Vrig3DScene):
    trace_name = "kern-103"
    quiz_labels = [
        "Ring the kernel runs in",
        "Zero nibbles after 0xffff8000",
        "Kernel stack size in 4 KB pages",
        "Bits of KASLR entropy on x86-64",
    ]

    def construct(self):
        tr = self.load()
        frame = self.frame
        frame.reorient(0, 0)
        self.heading("Where the kernel lives before you try to attack it.")

        src = VGroup(*(mono(l, 17, T.text_dim if l.strip().startswith("//") else T.text)
                       for l in tr["source"][6:13])).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        src.to_corner(UL, buff=0.5).shift(DOWN * 0.5)
        for m, l in zip(src, tr["source"][6:13]):
            m.shift(RIGHT * 0.1 * (len(l) - len(l.lstrip())))
        self.play(FadeIn(src))

        rings = VGroup()
        for k, role in zip(range(4), ("kernel_space", "grid", "grid", "user_space")):
            c = Circle(radius=0.55 + 0.55 * k).set_stroke(getattr(T, role), 3)
            rings.add(c)
        labs = VGroup(*(mono(f"ring {k}", 15, T.label).move_to(rings[k].get_top() + DOWN * 0.22) for k in range(4)))
        labs[0].move_to(rings[0].get_center())
        rg = VGroup(rings, labs).move_to(RIGHT * 3.6 + DOWN * 0.3)
        k_lab = mono("kernel", 18, T.kernel_space).next_to(rg, LEFT, buff=0.3).shift(UP * 0.2)
        u_lab = mono("user programs", 18, T.user_space).next_to(rings[3], DOWN, buff=0.15)
        self.play(LaggedStart(*map(ShowCreation, rings), lag_ratio=0.2), FadeIn(labs))
        self.play(FadeIn(k_lab), FadeIn(u_lab), Indicate(labs[0], color=T.kernel_space))
        self.say("A kernel module's init runs in ring 0, the most privileged mode. Your programs run in ring 3.")
        self.beat()

        # the 64-bit address space as a tower
        self.clear_stage()
        self.play(frame.animate.reorient(-30, 70, 0, center=(0, 0, 2.2), height=8.5), run_time=2)
        user = Prism(2.0, 2.0, 1.6, color=T.user_space, opacity=0.9).move_to([0, 0, 0.8])
        hole = Prism(2.0, 2.0, 1.8, color=T.grid, opacity=0.15).move_to([0, 0, 2.5])
        kern = Prism(2.0, 2.0, 1.6, color=T.kernel_space, opacity=0.9).move_to([0, 0, 4.2])
        kb = "0x" + tr["kernelBase"]
        l_user = billboard(mono("user space", 20, T.text).move_to([2.6, 0, 0.8]), frame)
        l_hole = billboard(mono("non-canonical, unmapped", 18, T.text_dim).move_to([3.6, 0, 2.5]), frame)
        l_kern = billboard(mono("kernel space", 20, T.text).move_to([2.7, 0, 4.4]), frame)
        l_kb = billboard(mono(kb, 20, T.kernel_space).move_to([-2.9, 0, 3.4]), frame)
        l_zero = billboard(mono("0x0", 20, T.user_space).move_to([-1.8, 0, 0.0]), frame)
        self.play(FadeIn(user, shift=OUT * 0.3), FadeIn(l_user), FadeIn(l_zero))
        self.play(FadeIn(hole), FadeIn(l_hole))
        self.play(FadeIn(kern, shift=OUT * 0.3), FadeIn(l_kern), FadeIn(l_kb))
        self.say("Userland sits low. The kernel owns the top half, starting at 0xffff800000000000.")
        frame.add_ambient_rotation(4 * DEG)
        self.wait(3)
        frame.clear_updaters()
        self.beat()

        # count the trailing nibbles
        self.clear_stage()
        self.play(frame.animate.reorient(0, 0, 0, center=ORIGIN, height=8), run_time=1.5)
        digits = mono(kb, 44, T.text).move_to(UP * 1.2).fix_in_frame()
        self.play(FadeIn(digits))
        tail = digits[2 + len("ffff8000"):]
        counts = VGroup()
        for i, d in enumerate(tail):
            n = mono(str(i + 1), 18, T.highlight).next_to(d, DOWN, buff=0.2).fix_in_frame()
            counts.add(n)
            self.play(d.animate.set_color(T.highlight), FadeIn(n), run_time=0.22)
        self.say("After 0xffff8000 come eight zero nibbles.")
        self.beat()

        # kernel stack: four pages
        pages = VGroup()
        for i in range(tr["stackPages"]):
            r = Rectangle(2.6, 0.5).set_stroke(T.grid, 1.5).set_fill(T.kernel_space, 0.7)
            pages.add(VGroup(r, mono("4 KB page", 16, T.text).move_to(r)))
        pages.arrange(UP, buff=0.05).move_to(LEFT * 3.4 + DOWN * 1.4).fix_in_frame()
        st = mono(f"kernel stack = {tr['stackKB']} KB", 20, T.label).next_to(pages, UP, buff=0.2).fix_in_frame()
        self.play(LaggedStart(*(FadeIn(p, shift=UP * 0.2) for p in pages), lag_ratio=0.2), FadeIn(st))
        self.say("Each task gets its own kernel stack, four pages, sixteen KB since 3.15.")
        self.beat()

        # KASLR: 512 slots
        cols, rows = 32, 16
        s = 0.14
        slots = VGroup(*(Square(s).set_stroke(T.grid, 0.6) for _ in range(cols * rows)))
        slots.arrange_in_grid(rows, cols, buff=0.02).move_to(RIGHT * 2.6 + DOWN * 1.5).fix_in_frame()
        kl = mono(f"KASLR: {tr['kaslrBits']} bits = {tr['kaslrSlots']} slots", 20, T.label)
        kl.next_to(slots, UP, buff=0.2).fix_in_frame()
        self.play(FadeIn(slots, lag_ratio=0.001), FadeIn(kl), run_time=1.2)
        img = Square(s).set_fill(T.kernel_space, 1).set_stroke(width=0).fix_in_frame()
        rng = random.Random(103)
        img.move_to(slots[rng.randrange(len(slots))])
        self.add(img)
        self.say("At boot the kernel image picks one of 512 positions. That's nine bits.")
        for _ in range(5):
            self.play(img.animate.move_to(slots[rng.randrange(len(slots))]), run_time=0.45)
        self.beat()

        self.quiz("All four answers pass VRIG's quiz.")
        self.outro()


# ======================================================================
# unit 20: teaching gaps
# ======================================================================

class Gap113(AsmAdv, VrigScene):
    trace_name = "gap-113"

    def construct(self):
        tr = self.load()
        self.heading("execve(\"/bin/sh\") in 23 bytes with no zeros.")

        # BAD and GOOD encodings, straight from the exercise source
        enc = []
        for l in tr["source"]:
            if "→" in l and l.startswith("// ") and ("B8" in l or "B9" in l or "31" in l or "B0" in l):
                ins, bs = l[3:].split("→")
                enc.append((ins.strip(), [int(b, 16) for b in bs.split()]))
        rows = VGroup()
        for ins, bs in enc:
            cells = VGroup(*(ByteCell(b, "crash" if b == 0 else "attacker_bytes") for b in bs)).arrange(RIGHT, buff=GAP)
            row = VGroup(mono(ins, 22, T.text), cells).arrange(RIGHT, buff=0.5)
            cells.set_x(1.0, LEFT)
            rows.add(row)
        rows.arrange(DOWN, buff=0.25, aligned_edge=LEFT).move_to(UP * 0.4)
        for r in rows:
            r[1].set_x(1.0, LEFT)
        bad = mono("strcpy stops at 00", 18, T.crash).next_to(rows[:2], RIGHT, buff=0.5)
        self.play(FadeIn(rows[:2]), FadeIn(bad))
        self.say("The obvious encodings are full of zero bytes, and strcpy stops at the first one.")
        self.beat()
        self.play(LaggedStart(*map(FadeIn, rows[2:]), lag_ratio=0.3))
        self.say("xor reg, reg zeroes a register in two bytes. mov al writes only the low byte.")
        self.beat()

        # the finished shellcode
        self.clear_stage()
        sc = tr["shellcode"]
        cells = VGroup(*(ByteCell(b, "attacker_bytes") for b in sc)).arrange(RIGHT, buff=GAP)
        cells.set_width(min(cells.get_width(), 12.8)).move_to(UP * 1.6)
        self.play(FadeIn(cells, lag_ratio=0.03))
        groups = VGroup()
        p = 0
        for ins in tr.instructions:
            n = len(ins["bytes"])
            g = cells[p:p + n]
            br = Line(g.get_corner(DL), g.get_corner(DR)).shift(DOWN * 0.12).set_stroke(T.text_section, 3)
            lab = mono(f"{ins['mnemonic']} {ins['operands']}", 13, T.label)
            lab.rotate(-50 * DEG).next_to(br, DOWN, buff=0.1).align_to(br, LEFT)
            groups.add(VGroup(br, lab))
            p += n
        self.play(LaggedStart(*map(FadeIn, groups), lag_ratio=0.1), run_time=1.6)
        scan = SurroundingRectangle(cells[0], buff=0.04).set_stroke(T.highlight, 3)
        self.play(ShowCreation(scan))
        self.play(scan.animate.move_to(cells[-1]), run_time=1.8, rate_func=linear)
        res = mono(f"{len(sc)} bytes, {sc.count(0)} zeros", 22, T.win).next_to(cells, UP, buff=0.3)
        self.play(FadeOut(scan), FadeIn(res))
        self.say("Twenty three bytes. Not one zero, so the whole thing survives the copy.")
        self.beat()

        # run it
        self.clear_stage()
        lst, regs = self.walk_setup(tr.instructions, ("eip", "esp", "eax", "ebx", "ecx", "edx"), size=18)
        writes = [w for s in tr.steps for w in (s.get("memWrites") or [])]
        lo = min(w["addr"] for w in writes)
        words = VGroup()
        for a in range(lo, lo + 4 * len(writes), 4):
            row = VGroup(*(ByteCell(None) for _ in range(4))).arrange(RIGHT, buff=GAP)
            row.add(mono(hx(a), 15, T.text_dim).next_to(row, LEFT, buff=0.2))
            row.addr = a
            words.add(row)
        words.arrange(UP, buff=0.08, aligned_edge=RIGHT).move_to(RIGHT * 3.2 + DOWN * 1.4)
        st_lab = mono("stack", 16, T.text_dim).next_to(words, UP, buff=0.15)
        self.play(FadeIn(lst), FadeIn(regs), FadeIn(words), FadeIn(st_lab))
        self.say("Step through it. Watch the pushes build the string on the stack.")

        def on(s):
            for w in s.get("memWrites") or []:
                row = next(r for r in words if r.addr == w["addr"])
                anims = []
                for i in range(4):
                    b = (w["value"] >> (8 * i)) & 0xff
                    g = chr(b) if 32 < b < 127 else None
                    c = row[i]
                    anims.append(Transform(c.label, c.relabel(b, g)))
                    anims.append(c.box.animate.set_fill(T.attacker_bytes if b else T.cell_fill, 0.85 if b else 1))
                self.play(*anims, run_time=0.5)
            if s["instr"]["mnemonic"] == "mov" and s["instr"]["operands"] == "ebx, esp":
                top = next(r for r in words if r.addr == s["regs"]["ebx"])
                start = np.array([regs.get_left()[0] - 0.1, regs.rows["ebx"].get_y(), 0])
                arr = Arrow(start, top.get_right(), buff=0.15).set_color(T.pointer)
                self.play(GrowArrow(arr))
                self.say(f'ebx points at "{tr["ebxString"]}", null terminated by the first push.')
                self.beat()
            if s["instr"]["mnemonic"] == "int":
                f = tr["final"]
                call = mono(f'execve("{tr["ebxString"]}", {f["ecx"]}, {f["edx"]})', 26, T.win)
                call.move_to(LEFT * 2.6 + DOWN * 1.8)
                sub = mono(f"eax = {hx(f['eax'], 2)}  int 0x80", 18, T.text_dim).next_to(call, DOWN, buff=0.15)
                self.play(FadeIn(call, scale=1.2), FadeIn(sub))
                self.say("eax is 0x0b, ecx and edx are zero. int 0x80 makes the call and a shell comes up.")
                self.beat(pause=1.8)

        self.walk(tr.steps, lst, regs, on=on, rt=0.55)
        self.outro()
