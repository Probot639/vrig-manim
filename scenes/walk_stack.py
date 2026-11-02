"""
VRIG's guided step lessons with a stack view: imagine-rit, intro C, stack-01,
the mitigation tours, kern-106, and the unit 20 gaps.

    node tools/vrig-trace/dist/vrig-walk_stack.mjs c-01 c-02 ...   # traces
    manimgl scenes/walk_stack.py C01 -w -l                         # quick look

StepWalkthrough plays a trace one VRIG click at a time: the exec line moves,
bytes that changed flip, and the range VRIG highlighted gets a box. Each
lesson subclass adds captions, region tags, and whatever picture the idea
needs (pointer arrows, GOT tables, a race timeline).
"""
from manimlib import *

from vrig.mob.cpu import CodeListing
from vrig.mob.memory import CELL, LIFT, mono, prose
from vrig.mob.walk_stack import MemColumn, Panel, WalkTrace, h32, hl_rect, perm_badge
from vrig.scene import VrigScene
from vrig.theme import T


class StepWalkthrough(VrigScene):
    trace_name = ""
    subtitle = ""
    captions: dict = {}          # step index -> caption
    fields: list = []            # (offset, size, name, role) tags beside the memory
    offsets = None               # word rows to draw, None for the whole frame
    addr_base = None             # relabel row addresses (c-02, see there)
    ascii_col = False
    code_from = 0                # first source line shown
    code_size = 24
    mem_scale = 1.35
    code_box = (6.2, 5.4)        # max width, height of the listing
    code_at = LEFT * 3.6 + UP * 0.35
    mem_at = RIGHT * 3.3 + UP * 0.35
    outro_note = None
    beat_pause = 1.5
    line_fix: dict = {}          # step -> source line, where VRIG's srcLine is off by one

    def construct(self):
        self.tr = WalkTrace.load(self.trace_name)
        self.exec_line = -1
        self.hl = None
        self.intro()
        self.build()
        for i, st in enumerate(self.tr.steps):
            self.step(i, st)
        self.outro()

    # -- framing -----------------------------------------------------------

    def intro(self):
        title = prose(self.tr.title, 46).to_edge(UP, buff=0.4)
        sub = prose(self.subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.25)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.55).to_corner(UL, buff=0.25))
        self.title = title

    def build(self):
        self.code = self.make_code()
        self.mem = self.make_mem()
        tags = VGroup(*(self.mem.tag(*f) for f in self.fields))
        self.play(FadeIn(self.code, shift=RIGHT * 0.3), FadeIn(self.mem.stack, lag_ratio=0.03))
        if len(tags):
            self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.25))
        self.beat()

    def make_code(self) -> CodeListing:
        lines = self.tr.source[self.code_from:]
        code = CodeListing(lines, size=self.code_size)
        w, h = self.code_box
        if code.get_width() > w:
            code.set_width(w)
        if code.get_height() > h:
            code.set_height(h)
        return code.move_to(self.code_at)

    def make_mem(self) -> MemColumn:
        return MemColumn(self.tr, self.offsets, step=-1, base=self.addr_base,
                         ascii_col=self.ascii_col).scale(self.mem_scale).move_to(self.mem_at)

    # -- one VRIG click -------------------------------------------------------

    def step(self, i: int, st: dict):
        cap = self.captions.get(i)
        if cap:
            self.say(cap, run_time=0.5)
        hook = getattr(self, f"before_{i}", None)
        if hook:
            hook(st)
        self.apply(st)
        hook = getattr(self, f"after_{i}", None)
        if hook:
            hook(st)
        self.beat()
        settle = self.mem.settle(st["written"])
        if settle:
            self.play(*settle, run_time=0.3)

    def apply(self, st: dict, run_time: float = 0.8):
        anims = []
        exec_line = self.line_fix.get(st["index"], st["execLine"])
        line = exec_line - self.code_from
        if exec_line != self.exec_line and 0 <= line < len(self.code.lines):
            anims.append(self.code.focus(line))
        self.exec_line = exec_line
        anims += self.mem.sync(st["memory"], st["written"])
        anims += self.move_hl(st["hl"])
        if anims:
            self.play(*anims, run_time=run_time)

    def move_hl(self, hl) -> list[Animation]:
        new = hl_rect(self.mem, *hl) if hl else None
        if new is not None and not len(new.get_points()):
            new = None
        old = self.hl
        self.hl = new
        if old is None and new is None:
            return []
        if old is None:
            return [ShowCreation(new)]
        if new is None:
            return [FadeOut(old)]
        return [ReplacementTransform(old, new)]

    def outro(self):
        self.unsay()
        keep = [m for m in self.mobjects if m is not self.title and m is not self.frame]
        n = len(self.tr.steps)
        done = mono(f"Step {n}/{n}   All steps complete", 22, T.win)
        msg = prose(self._wrap(self.tr.win_msg, 54), 30, T.text)
        grp = VGroup(done, msg).arrange(DOWN, buff=0.45).move_to(DOWN * 0.2)
        self.play(*(FadeOut(m) for m in keep), FadeIn(done, shift=UP * 0.2))
        self.play(Write(msg, run_time=1.5))
        if self.outro_note:
            note = prose(self.outro_note, 24, T.text_dim).next_to(grp, DOWN, buff=0.5)
            self.play(FadeIn(note))
        self.beat(pause=2.0)

    @staticmethod
    def _wrap(s: str, width: int) -> str:
        import textwrap
        return "\n".join(textwrap.wrap(s, width))

    # -- helpers for subclasses ----------------------------------------------

    def left_brace(self, start: int, end: int, text: str, role: str = "label") -> VGroup:
        rows = VGroup(*(r for o, r in self.mem.rows.items() if start <= o < end))
        b = Brace(rows, LEFT, buff=0.15).set_color(getattr(T, role))
        t = mono(text, 16, getattr(T, role)).next_to(b, LEFT, buff=0.1)
        return VGroup(b, t)

    def value_tag(self, start: int, size: int, text: str, role: str = "highlight", side=LEFT) -> Text:
        cells = self.mem.cells_in(start, start + size)
        return mono(text, 18, getattr(T, role)).next_to(cells, side, buff=0.25)

    def arrow_between(self, a: Mobject, b: Mobject, role: str = "pointer", angle: float = -60) -> Arrow:
        return CurvedArrow(a.get_left() + LEFT * 0.05, b.get_left() + LEFT * 0.05, angle=angle * DEG) \
            .set_stroke(getattr(T, role), 3).set_fill(getattr(T, role))


# =============================================================================
# imagine-rit
# =============================================================================


class Rit00(VrigScene):
    """
    rit-00 is the tour of the VRIG workspace, so this one draws the page as a
    schematic and lights each panel in the order the lesson's five steps name
    them. Layout follows the ExercisePageClient compact shell (directions,
    the Code / Assembly / Console / Misc tabs, bottom dock, pager).
    """
    trace_name = "rit-00"

    def construct(self):
        tr = WalkTrace.load(self.trace_name)
        title = prose(tr.title, 46).to_edge(UP, buff=0.4)
        sub = prose("A map of the screen before the first real lesson.", 26, T.text_dim)
        sub.next_to(title, DOWN, buff=0.25)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        self.play(FadeOut(sub), title.animate.scale(0.55).to_corner(UL, buff=0.25))

        W, H = 10.4, 5.6
        page = RoundedRectangle(width=W, height=H, corner_radius=0.12).set_stroke(T.grid, 2)
        page.move_to(UP * 0.15)
        x0, y0 = page.get_left()[0], page.get_top()[1]

        def box(x, y, w, h, label, size=18):
            r = Rectangle(width=w, height=h).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.8)
            r.move_to([x0 + x + w / 2, y0 - y - h / 2, 0])
            t = mono(label, size, T.label).move_to(r)
            return VGroup(r, t)

        header = box(0.0, 0.0, W, 0.5, "0xVRIG", 18)
        header[1].align_to(header[0], LEFT).shift(RIGHT * 0.2)
        sidebar = box(0.0, 0.5, 1.9, H - 0.5, "lessons", 16)
        directions = box(2.1, 0.7, W - 2.3, 1.0, "directions", 18)
        tabs = VGroup()
        tab_w = (W - 2.3) / 4
        for k, name in enumerate(["Code", "Assembly", "Console", "Misc"]):
            tabs.add(box(2.1 + k * tab_w, 1.9, tab_w - 0.05, 0.42, name, 16))
        work = box(2.1, 2.35, W - 2.3, 1.75, "", 16)
        dock = box(2.1, 4.25, W - 2.3 - 3.6, 0.65, "input   [Step] [Reset]", 15)
        pager = VGroup(*(box(W - 3.55 + k * 1.18, 4.25, 1.12, 0.65, n, 14)
                         for k, n in enumerate(["Previous", "Contents", "Next"])))

        # the workspace shows whichever tab is up. Code first.
        code_peek = VGroup(*(mono(l, 13, T.label) for l in tr.source[2:7])).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
        code_peek.move_to(work[0]).align_to(work[0], LEFT).shift(RIGHT * 0.25)
        stack_peek = MemColumn(tr, step=3).scale(0.62).move_to(work[0])
        console_peek = VGroup(*(mono(t, 12, T.label) for t in ("> Step 1/5", "> Step 2/5", "> ...")))
        console_peek.arrange(DOWN, aligned_edge=LEFT, buff=0.08).move_to(work[0]).align_to(work[0], LEFT).shift(RIGHT * 0.25)
        misc_peek = VGroup(*(mono(t, 13, T.label) for t in ("symbols", "hex calc", "payload builder", "gadgets")))
        misc_peek.arrange(RIGHT, buff=0.45).move_to(work[0])

        everything = VGroup(page, header, sidebar, directions, tabs, work, dock, pager)
        self.play(ShowCreation(page), LaggedStartMap(FadeIn, VGroup(header, sidebar, directions, tabs, work, dock, pager),
                                                     lag_ratio=0.12, run_time=1.6))
        self.play(FadeIn(code_peek))
        self.beat()

        def light(*mobs, role="highlight"):
            return [m[0].animate.set_stroke(getattr(T, role), 3) for m in mobs]

        def dim(*mobs):
            return [m[0].animate.set_stroke(T.grid, 1.5) for m in mobs]

        def tab_to(k, peek, old):
            return [tabs[k][0].animate.set_fill(T.highlight, 0.25), FadeOut(old), FadeIn(peek)]

        # step 1: directions
        self.say("The directions panel holds the goal. It stays put while you work.")
        self.play(*light(directions))
        self.beat()
        # step 2: Code and Assembly tabs
        self.say("Code shows the C source. Assembly shows the stack frame as it changes.")
        self.play(*dim(directions), *light(tabs[0], tabs[1]), tabs[0][0].animate.set_fill(T.highlight, 0.25))
        self.beat(pause=0.5)
        self.play(tabs[0][0].animate.set_fill(T.cell_fill, 0.8), *tab_to(1, stack_peek, code_peek))
        self.beat()
        # step 3: Misc tools
        self.say("Misc holds helpers like symbols, a hex calculator, the payload builder, and gadgets.")
        self.play(*dim(tabs[0], tabs[1]), tabs[1][0].animate.set_fill(T.cell_fill, 0.8),
                  *light(tabs[3]), *tab_to(3, misc_peek, stack_peek))
        self.beat()
        # Console wasn't one of the five steps but the desc names it
        self.say("Console keeps a log of every step.")
        self.play(*dim(tabs[3]), tabs[3][0].animate.set_fill(T.cell_fill, 0.8),
                  *light(tabs[2]), *tab_to(2, console_peek, misc_peek))
        self.beat()
        # step 4: input dock
        self.say("The bottom dock is where you type payloads or press Step.")
        self.play(*dim(tabs[2]), tabs[2][0].animate.set_fill(T.cell_fill, 0.8), *light(dock))
        self.beat()
        # step 5: pager
        self.say("Previous, Contents, and Next move you through the workshop.")
        self.play(*dim(dock), *light(*pager))
        self.play(Indicate(pager[1][1], color=T.highlight), *light(sidebar))
        self.beat()

        self.unsay()
        done = mono("Orientation complete", 24, T.win)
        msg = prose(StepWalkthrough._wrap(tr.win_msg, 54), 28)
        grp = VGroup(done, msg).arrange(DOWN, buff=0.4)
        self.play(FadeOut(everything), FadeOut(console_peek), FadeIn(done, shift=UP * 0.2))
        self.play(Write(msg, run_time=1.4))
        self.beat(pause=2.0)


class StackFrameBuild(StepWalkthrough):
    """rit-01 and stack-01: ret, saved ebp, then buf, pushed in that order."""
    fields = [(0, 16, "buf[16]", "buffer"), (16, 4, "saved ebp", "saved_fp"), (20, 4, "return addr", "saved_ret")]
    code_from = 2

    def build(self):
        self.code = self.make_code()
        self.mem = self.make_mem()
        self.tags = {f[2]: self.mem.tag(*f) for f in self.fields}
        for t in self.tags.values():
            t.set_opacity(0)
        # which way the stack grows
        x = self.mem.stack.get_right()[0] + 2.0
        self.grow = Arrow([x, self.mem.stack.get_top()[1] + 0.1, 0], [x, self.mem.stack.get_bottom()[1] - 0.1, 0],
                          buff=0).set_stroke(T.text_dim, 2).set_fill(T.text_dim)
        self.grow_lab = mono("grows down", 14, T.text_dim).rotate(-90 * DEG).next_to(self.grow, RIGHT, buff=0.1)
        self.esp = self.esp_marker().next_to(self.mem.row_of(self.tr.total - 4).addr_label, LEFT, buff=0.15)
        self.esp.shift(UP * 0.52)
        self.play(FadeIn(self.code, shift=RIGHT * 0.3), FadeIn(self.mem.stack, lag_ratio=0.03),
                  FadeIn(self.grow), FadeIn(self.grow_lab))
        self.play(FadeIn(self.esp))
        self.beat()

    def esp_marker(self):
        tri = Triangle().rotate(-90 * DEG).set_height(CELL * 0.45).set_fill(T.highlight, 1).set_stroke(width=0)
        lab = mono("esp", 16, T.highlight).next_to(tri, LEFT, buff=0.08)
        return VGroup(lab, tri)

    def esp_to(self, off):
        return self.esp.animate.next_to(self.mem.row_of(off).addr_label, LEFT, buff=0.15)

    def reveal(self, name, off):
        t = self.tags[name]
        return [t.animate.set_opacity(1), self.esp_to(off)]

    def before_1(self, st):
        self.call_line()

    def call_line(self):
        pass

    def after_1(self, st):
        self.play(*self.reveal("return addr", self.tr.ret_off), *self.mem.paint(20, 24, "saved_ret"))
        ret = self.tr.word(self.tr.ret_off, 1)
        lab = mono(f"ret = {h32(ret)}  (main+0x25)", 18, T.saved_ret)
        lab.next_to(self.mem.cells_in(20, 24), UP, buff=0.2)
        self.ret_lab = lab
        self.play(FadeIn(lab, shift=LEFT * 0.1))

    def after_2(self, st):
        self.play(*self.reveal("saved ebp", self.tr.ebp_off), *self.mem.paint(16, 20, "saved_fp"))

    def after_3(self, st):
        self.play(*self.reveal("buf[16]", 0), *self.mem.paint(0, 16, "buffer"))

    def after_4(self, st):
        arrow = Arrow(self.mem.cells_in(12, 16).get_top() + LEFT * 1.6, self.mem.cells_in(20, 24).get_left() + LEFT * 0.1,
                      path_arc=-70 * DEG, buff=0.05).set_stroke(T.crash, 3).set_fill(T.crash)
        self.play(GrowArrow(arrow))
        self.play(Indicate(self.mem.cells_in(20, 24), color=T.crash, scale_factor=1.08))


class Rit01(StackFrameBuild):
    trace_name = "rit-01"
    subtitle = "Three sticky notes go on the stack when a function runs."
    captions = {
        0: "main() is about to call vuln(). The stack is empty for now.",
        1: "Note one is the go-back address. vuln() returns here when it's done.",
        2: "Note two is a bookmark, the saved ebp. You can ignore it for now.",
        3: "Note three is the scratchpad. buf gets 16 bytes for your input.",
        4: "The scratchpad sits right below the go-back address. Nothing sits between them.",
    }


class Stack01(StackFrameBuild):
    """Same frame as rit-01, but this lesson ships the assembly too, so the
    asm listing drives the focus bar instead of the C."""
    trace_name = "stack-01"
    subtitle = "What call, push ebp, and sub esp do to memory."
    captions = {
        0: "main() is about to call vuln().",
        1: "call pushes the return address, the next instruction in main().",
        2: "vuln() starts with push ebp. That saves the caller's frame pointer.",
        3: "sub esp, 16 makes room for buf. Nothing gets written, esp just moves.",
        4: "buf, saved ebp, then the return address. A long write to buf climbs toward ret.",
    }
    # asm line each click lands on (VRIG's steps have no srcLine)
    ASM_FOR_STEP = {0: "    call vuln", 1: "    call vuln", 2: "    push ebp", 3: "    sub  esp, 16", 4: "    ; buf is at [ebp-16]"}

    def make_code(self):
        asm = self.tr.asm
        self.asm_lines = asm
        code = CodeListing(asm, size=20)
        code.set_height(min(code.get_height(), 5.8))
        return code.move_to(LEFT * 4.2 + UP * 0.3)

    def apply(self, st, run_time=0.8):
        i = st["index"]
        want = self.ASM_FOR_STEP[i]
        # vuln's push ebp is the second one in the listing
        idx = [k for k, l in enumerate(self.asm_lines) if l == want]
        line = idx[-1] if want == "    push ebp" else idx[0]
        anims = [self.code.focus(line)]
        anims += self.mem.sync(st["memory"], st["written"]) + self.move_hl(st["hl"])
        self.play(*anims, run_time=run_time)


# =============================================================================
# unit-intro-c
# =============================================================================


class C01(StepWalkthrough):
    trace_name = "c-01"
    subtitle = "A C variable is a named run of bytes."
    code_from = 2
    offsets = [0, 4, 8, 12]
    ascii_col = True
    captions = {
        0: "Every variable gets a slot, and its type says how many bytes.",
        1: "int x = 42 takes four bytes. 42 is 0x2a, and the low byte comes first.",
        2: "char c = 'A' takes one byte. 'A' is ASCII 65, which is 0x41.",
        3: "sizeof(int) is 4 and sizeof(char) is 1.",
        4: "A variable is just bytes at an address.",
    }

    def after_1(self, st):
        self.play(*self.mem.paint(0, 4, "local_var"))
        word = self.mem.cells_in(0, 4)
        # read the word back, high byte first, the way it prints
        parts = VGroup(*(mono(f"{b:02x}", 20, T.highlight) for b in reversed(st["memory"][0:4]))).arrange(RIGHT, buff=0.03)
        val = VGroup(mono("0x", 20, T.highlight), parts).arrange(RIGHT, buff=0.03)
        val.next_to(self.mem.row_of(0).addr_label, LEFT, buff=0.5)
        self.play(*[TransformFromCopy(word[k].label, parts[3 - k], path_arc=60 * DEG) for k in range(4)],
                  FadeIn(val[0]))
        eq = mono(f"= {self.tr.word(0, 1)}", 20, T.highlight).next_to(val, DOWN, buff=0.12)
        self.play(FadeIn(eq))
        self.x_val = VGroup(val, eq)
        self.x_tag = self.mem.tag(0, 4, "int x", "local_var")
        self.play(FadeIn(self.x_tag))

    def after_2(self, st):
        self.play(*self.mem.paint(4, 5, "buffer"))
        c = self.mem.tag(4, 1, "char c", "buffer")
        self.play(FadeIn(c), Indicate(self.mem.ascii[4], color=T.buffer, scale_factor=1.4))

    def after_3(self, st):
        b4 = Brace(self.mem.cells_in(0, 4), UP, buff=0.06)
        t4 = mono("sizeof(int) = 4", 15, T.local_var).next_to(b4, UP, buff=0.06)
        # char row sits above the int row, so its brace goes on top of that row
        b4 = Brace(self.mem.cells_in(0, 4), DOWN, buff=0.06).set_color(T.local_var)
        t4.set_color(T.local_var).next_to(b4, DOWN, buff=0.06)
        b1 = SurroundingRectangle(self.mem.cells[4], buff=0.04).set_stroke(T.buffer, 3)
        t1 = mono("sizeof(char) = 1", 15, T.buffer).next_to(self.mem.row_of(4).addr_label, LEFT, buff=0.4)
        self.play(GrowFromCenter(b4), FadeIn(t4), ShowCreation(b1), FadeIn(t1), FadeOut(self.x_val))


class C02(StepWalkthrough):
    """
    VRIG's log says x lives at 0xBFFF0010 and writes that into p, but the
    StackSim puts x at its base, 0xbfff0100. Draw the rows at the address the
    lesson uses (taken from p's bytes in the trace) so the arrow is honest.
    """
    trace_name = "c-02"
    subtitle = "A pointer is a number that holds an address."
    code_from = 2
    offsets = [0, 4, 8, 12]
    captions = {
        0: "int x = 10. Four bytes hold the value 10.",
        1: "int *p = &x. p holds x's address. Same four bytes, read as a location.",
        2: "On a 32-bit machine a pointer is four bytes, like an int.",
        3: "*p = 20 follows the address in p and writes there. x changes.",
        4: "Writing *p and writing x touch the same bytes.",
        5: "Control a pointer and you can reach any address.",
    }

    def setup(self):
        super().setup()
        tr = WalkTrace.load(self.trace_name)
        p = tr.word(4, 1)
        self.addr_base = p  # x is at offset 0

    def after_0(self, st):
        self.play(*self.mem.paint(0, 4, "local_var"), FadeIn(self.mem.tag(0, 4, "int x", "local_var")))
        self.xv = mono("x = 10", 18, T.local_var).next_to(self.mem.cells_in(0, 4), RIGHT, buff=1.6)

    def after_1(self, st):
        self.play(*self.mem.paint(4, 8, "pointer", 0.35), FadeIn(self.mem.tag(4, 4, "int *p", "pointer")))
        p = self.tr.word(4, 1)
        val = mono(f"p = {h32(p)}", 18, T.pointer).next_to(self.mem.row_of(4).addr_label, LEFT, buff=0.9)
        self.play(FadeIn(val))
        self.pval = val
        self.arrow = CurvedArrow(self.mem.row_of(4).addr_label.get_left() + LEFT * 0.1,
                                 self.mem.row_of(0).addr_label.get_left() + LEFT * 0.1,
                                 angle=120 * DEG).set_color(T.pointer)
        self.play(Indicate(self.mem.row_of(0).addr_label, color=T.pointer), ShowCreation(self.arrow))

    def after_3(self, st):
        flash = self.arrow.copy().set_stroke(T.highlight, 5)
        self.play(ShowPassingFlash(flash, time_width=0.6, run_time=1.0))
        self.play(Indicate(self.mem.cells_in(0, 4), color=T.highlight, scale_factor=1.08))


class C03(StepWalkthrough):
    trace_name = "c-03"
    subtitle = "Arrays are runs of bytes. Nothing guards the end."
    code_from = 3
    offsets = [0, 4, 8, 12]
    ascii_col = True
    captions = {
        0: "name[8] = \"Alice\". Five letters, then a zero byte that ends the string.",
        1: "buf[8] is the next eight bytes in this model. C doesn't promise that.",
        2: "strlen and printf stop at the zero. Lose it and they keep reading.",
        3: "name[7] = 'Z' is the last legal slot. Index 7 of 0 through 7.",
        4: "name[10] = '!' is out of bounds. C writes it anyway, into buf.",
        5: "No bounds check. That gap is where buffer overflows come from.",
    }

    def after_0(self, st):
        self.play(*self.mem.paint(0, 8, "buffer"), FadeIn(self.mem.tag(0, 8, "name[8]", "buffer")))
        self.play(Indicate(self.mem.cells_in(0, 5), color=T.highlight, scale_factor=1.05))

    def after_1(self, st):
        self.play(*self.mem.paint(8, 16, "local_var", 0.35), FadeIn(self.mem.tag(8, 8, "buf[8]", "local_var")))

    def after_2(self, st):
        self.play(Indicate(self.mem.cells[5], color=T.highlight, scale_factor=1.25))

    def after_3(self, st):
        self.play(Indicate(self.mem.cells[7], color=T.win, scale_factor=1.2))

    def after_4(self, st):
        c = self.mem.cells[10]
        lab = mono("name + 10", 18, T.crash).next_to(self.mem.row_of(8).addr_label, LEFT, buff=0.4)
        self.play(Flash(c, color=T.crash, flash_radius=0.35), c.box.animate.set_stroke(T.crash, 3), FadeIn(lab))


class C04(StepWalkthrough):
    """Call stack as frames: main's frame stays, greet's frame grows below it
    and is thrown away on return."""
    trace_name = "c-04"
    subtitle = "What a call leaves on the stack, and what return reads back."
    code_from = 2
    offsets = [0, 4, 8, 12]
    captions = {
        0: "The stack grows toward lower addresses as functions get called.",
        1: "main() calls greet(). The return address into main goes on the stack first.",
        2: "greet() builds its frame. Saved ebp, then its local x = 5.",
        3: "Local x, saved ebp, return address. That's greet's whole frame.",
        4: "At the closing brace greet() returns. ret jumps to the saved address.",
        5: "Overwrite the return address and you pick where ret goes.",
    }

    def build(self):
        super().build()
        top = self.mem.stack.get_top() + UP * 0.25
        self.main_frame = VGroup(
            Rectangle(width=2.0, height=0.45).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.8),
            mono("main()", 16, T.label)).move_to(top + UP * 0.25)
        self.main_frame.set_x(self.mem.stack[0].cells.get_x() if hasattr(self.mem.stack[0], "cells") else 0)
        self.main_frame[1].move_to(self.main_frame[0])
        self.play(FadeIn(self.main_frame, shift=DOWN * 0.1))

    def after_1(self, st):
        self.play(*self.mem.paint(12, 16, "saved_ret"), FadeIn(self.mem.tag(12, 4, "return addr", "saved_ret")))

    def after_2(self, st):
        self.play(*self.mem.paint(8, 12, "saved_fp"), *self.mem.paint(0, 4, "local_var"),
                  FadeIn(self.mem.tag(8, 4, "saved ebp", "saved_fp")), FadeIn(self.mem.tag(0, 4, "int x", "local_var")))
        self.frame_brace, self.frame_lab = self.left_brace(0, 16, "greet()\nframe")
        self.play(GrowFromCenter(self.frame_brace), FadeIn(self.frame_lab))

    def after_4(self, st):
        ret = self.tr.word(12, 4)
        val = mono(f"ret -> {h32(ret)}", 18, T.saved_ret).next_to(self.main_frame, LEFT, buff=0.6)
        self.play(FadeIn(val, shift=LEFT * 0.2), Indicate(self.mem.cells_in(12, 16), color=T.saved_ret))
        main_line = self.code.lines[9 - self.code_from]  # printf("Back in main")
        jump = CurvedArrow(val.get_left(), main_line.get_right() + RIGHT * 0.1, angle=40 * DEG).set_color(T.saved_ret)
        self.play(ShowCreation(jump), self.code.focus(9 - self.code_from))
        self.wait(1.0)
        self.play(*(m.animate.set_opacity(0.3) for m in (self.mem.cells_in(0, 16), self.frame_brace, self.frame_lab)),
                  FadeOut(val), FadeOut(jump))


class C05(StepWalkthrough):
    """struct Player: fields at fixed offsets from the struct's start."""
    trace_name = "c-05"
    # VRIG's srcLines for c-05 land one line early (3 is "struct Player {",
    # the log is about hp on line 4)
    line_fix = {1: 4, 2: 5, 3: 6, 4: 6}
    subtitle = "Struct fields sit at fixed offsets."
    code_from = 3
    offsets = [0, 4, 8, 12]
    ascii_col = True
    captions = {
        0: "A struct is its fields, laid end to end in the order you wrote them.",
        1: "hp is at offset 0, four bytes. p.hp = 100 is 0x64.",
        2: "score is at offset 4, right after hp.",
        3: "name[8] is at offset 8. sizeof(struct Player) is 16. No padding is needed.",
        4: "p.name is just p plus 8. Overflow name and you write past the struct.",
    }

    def offset_mark(self, off, text):
        row = self.mem.row_of(off)
        t = mono(text, 14, T.text_dim).next_to(row.addr_label, LEFT, buff=0.25)
        return t

    def after_1(self, st):
        self.base_lab = mono("&p", 16, T.pointer).next_to(self.mem.row_of(0).addr_label, LEFT, buff=0.3)
        self.play(*self.mem.paint(0, 4, "local_var"), FadeIn(self.mem.tag(0, 4, "hp  +0", "local_var")),
                  FadeIn(self.base_lab))

    def after_2(self, st):
        self.play(*self.mem.paint(4, 8, "arg"), FadeIn(self.mem.tag(4, 4, "score  +4", "arg")))

    def after_3(self, st):
        self.play(*self.mem.paint(8, 16, "buffer"), FadeIn(self.mem.tag(8, 8, "name[8]  +8", "buffer")))
        self.size_brace = self.left_brace(0, 16, "sizeof = 16")
        self.play(GrowFromCenter(self.size_brace[0]), FadeIn(self.size_brace[1]), FadeOut(self.base_lab))

    def after_4(self, st):
        arc = CurvedArrow(self.base_lab.get_top(), self.mem.row_of(8).addr_label.get_left() + LEFT * 0.1,
                          angle=-60 * DEG).set_color(T.pointer)
        plus = mono("+ 8", 16, T.pointer).next_to(arc, LEFT, buff=0.05)
        self.play(FadeOut(self.size_brace), FadeIn(self.base_lab))
        self.play(ShowCreation(arc), FadeIn(plus))


class C07(StepWalkthrough):
    trace_name = "c-07"
    subtitle = "strcpy doesn't know how big buf is."
    code_from = 3
    offsets = [0, 4, 8, 12]
    ascii_col = True
    captions = {
        0: "secret = 0x42 sits right after buf[8] in this frame.",
        1: "strcpy copies 16 A's plus a zero byte into an 8-byte buf.",
        2: "The first eight fill buf. The next ones land on secret.",
        3: "secret now reads 0x41414141. strncpy with a size of 8 would have stopped.",
        4: "Off-by-one bugs and use-after-free corrupt memory in similar ways.",
        5: "C never checks sizes. When the code gets them wrong, neighbors get overwritten.",
    }

    def after_0(self, st):
        self.play(*self.mem.paint(0, 8, "buffer"), *self.mem.paint(8, 12, "local_var"),
                  FadeIn(self.mem.tag(0, 8, "buf[8]", "buffer")), FadeIn(self.mem.tag(8, 4, "int secret", "local_var")))
        self.sv = mono("secret = 0x42", 18, T.local_var).next_to(self.mem.cells_in(8, 12), LEFT, buff=1.8)
        self.play(FadeIn(self.sv))

    def after_1(self, st):
        self.play(*self.mem.paint(0, 8, "attacker_bytes"))

    def after_2(self, st):
        self.play(*self.mem.paint(8, 16, "attacker_bytes"),
                  Flash(self.mem.cells_in(8, 12).get_right(), color=T.crash, flash_radius=0.3))
        new = mono(f"secret = {self.tr.word(8, 2):#010x}", 18, T.crash).move_to(self.sv, aligned_edge=RIGHT)
        self.play(FadeTransform(self.sv, new))
        self.sv = new


class C08(StepWalkthrough):
    """
    VRIG's "Attack 1" step only fills input[16] with A's. It never writes
    the 17th byte that would reach authorized, so the video shows that byte
    as a ghost with no value instead of pretending the sim wrote it.
    """
    trace_name = "c-08"
    subtitle = "Find the line that lets input reach authorized."
    code_from = 3
    offsets = [0, 4, 8, 12, 16]
    ascii_col = True
    captions = {
        0: "This asks for a password and sets authorized = 1 on a match.",
        1: "authorized sits right after input[16].",
        2: "gets(input) reads until newline. It has no length limit. \"s3cret\" fits.",
        3: "Type 16 bytes, then one more nonzero byte. It lands in authorized.",
        4: "Type more and you reach saved ebp and the return address.",
        5: "gets() was removed from C in 2011. Next units exploit exactly this.",
    }

    def build(self):
        super().build()
        # offset 16 is where this frame keeps authorized
        self.play(FadeIn(self.mem.tag(0, 16, "input[16]", "buffer")),
                  FadeIn(self.mem.tag(16, 4, "authorized", "local_var")))

    def after_1(self, st):
        self.play(*self.mem.paint(0, 16, "buffer", 0.5), *self.mem.paint(16, 20, "local_var", 0.5))

    def after_2(self, st):
        self.play(*self.mem.paint(0, 7, "buffer"))

    def after_3(self, st):
        self.play(*self.mem.paint(0, 16, "attacker_bytes"))
        ghost = self.mem.cells[16].copy()
        ghost.box.set_fill(T.attacker_bytes, 0.25).set_stroke(T.attacker_bytes, 2)
        q = mono("!=0", 12, T.attacker_bytes).move_to(ghost.box).shift(LIFT)
        ghost.remove(ghost.label)
        g = VGroup(ghost, q)
        start = g.copy().shift(LEFT * 3.0)
        self.play(FadeIn(start))
        self.play(Transform(start, g), run_time=0.8)
        self.ghost = start
        check = self.code.lines[10 - self.code_from]
        self.play(self.code.focus(10 - self.code_from))
        ok = mono("Access granted!", 16, T.win).next_to(check, RIGHT, buff=0.4)
        self.play(FadeIn(ok, shift=LEFT * 0.1))
        self.ok = ok

    def after_4(self, st):
        self.play(FadeOut(self.ok))


# =============================================================================
# unit15-mitigations
# =============================================================================


def memmap_panel(regions: list[dict], width=3.6) -> Panel:
    rows = VGroup()
    for r in regions:
        name = mono(f"{r['name']:<6}", 16, T.label)
        addr = mono(h32(r["start"]), 14, T.text_dim)
        perm = perm_badge(r["perms"])
        row = VGroup(name, addr, perm).arrange(RIGHT, buff=0.3)
        row.region = r
        rows.add(row)
    rows.arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    return Panel("memory map", rows, width=width)


class Mit80(StepWalkthrough):
    trace_name = "mit-80"
    subtitle = "Writable or executable. A page can't be both."
    code_from = 5
    code_box = (4.6, 5.0)
    code_at = LEFT * 4.6 + UP * 0.4
    mem_at = RIGHT * 0.0 + UP * 0.35
    mem_scale = 1.1
    offsets = [0, 4, 8, 12, 16, 64, 68, 72]
    fields = [(0, 64, "buf[64]", "buffer"), (64, 4, "saved ebp", "saved_fp"), (68, 4, "ret", "saved_ret")]
    captions = {
        0: "With DEP, the stack is RW- and .text is R-X. The NX bit enforces it.",
        1: "The classic attack starts by putting shellcode in buf.",
        2: "Then the overflow points the return address at buf on the stack.",
        3: "ret jumps to the stack. The page has NX set, so the CPU faults.",
        4: "ROP skips injected code. The return address points into .text instead.",
        5: "ROP can also call mprotect to make a page executable again.",
        6: "NX stops injected code from running. It needs other mitigations, like ASLR and CFI, beside it.",
    }

    def build(self):
        super().build()
        regs = self.tr.aux(0)["memMap"]
        self.mmap = memmap_panel(regs).move_to(RIGHT * 5.0 + UP * 1.3)
        self.play(FadeIn(self.mmap, shift=LEFT * 0.2))

    def map_row(self, name):
        return next(r for r in self.mmap.body if r.region["name"] == name)

    def after_0(self, st):
        self.play(Indicate(self.map_row("stack")), Indicate(self.map_row(".text")))

    def after_1(self, st):
        self.play(*self.mem.paint(0, 17, "attacker_bytes"))
        self.play(self.map_row("stack")[0].animate.set_color(T.highlight))

    def after_2(self, st):
        self.play(*self.mem.paint(68, 72, "attacker_bytes"))
        tgt = self.tr.word(68, 2)
        lab = mono(f"ret = {h32(tgt)} = &buf", 16, T.attacker_bytes).next_to(self.mmap, DOWN, buff=0.3)
        arc = CurvedArrow(self.mem.cells_in(68, 72).get_left() + LEFT * 0.05,
                          self.mem.cells_in(0, 4).get_left() + LEFT * 0.05, angle=80 * DEG).set_color(T.attacker_bytes)
        self.play(ShowCreation(arc), FadeIn(lab))
        self.ret_arc, self.ret_lab = arc, lab

    def after_3(self, st):
        x = Cross(self.mem.cells_in(0, 4), stroke_color=T.crash, stroke_width=6)
        stack_row = self.map_row("stack")
        fault = mono("SIGSEGV  NX", 18, T.crash).next_to(self.ret_lab, DOWN, buff=0.25)
        self.play(ShowCreation(x), stack_row[2].animate.set_color(T.crash), FadeIn(fault))
        self.play(Indicate(stack_row[2][2], color=T.crash, scale_factor=1.6))
        self.beat(pause=0.4)
        self.play(FadeOut(x), FadeOut(fault), FadeOut(self.ret_arc), FadeOut(self.ret_lab),
                  stack_row[0].animate.set_color(T.label), stack_row[2].animate.set_color(T.text_dim))

    def after_4(self, st):
        self.play(*self.mem.paint(68, 76, "gadget"))
        g1, g2 = self.tr.word(68, 4), self.tr.word(72, 4)
        text = self.map_row(".text")
        labs = VGroup(mono(f"gadget {h32(g1)}", 14, T.gadget), mono(f"gadget {h32(g2)}", 14, T.gadget))
        labs.arrange(DOWN, aligned_edge=LEFT, buff=0.1).next_to(self.mmap, DOWN, buff=0.35, aligned_edge=LEFT)
        x = self.mem.tags.get_right()[0] + 0.15
        arcs = VGroup(*(Arrow([x, self.mem.cells_in(o, o + 4).get_y(), 0], text.get_left() + LEFT * 0.05,
                              buff=0.05).set_stroke(T.gadget, 3).set_fill(T.gadget) for o in (68, 72)))
        self.play(text[0].animate.set_color(T.win), LaggedStartMap(GrowArrow, arcs, lag_ratio=0.3), FadeIn(labs))
        self.rop = VGroup(arcs, labs)

    def after_5(self, st):
        self.play(FadeOut(self.rop), self.map_row(".text")[0].animate.set_color(T.label))


def got_panel(entries: list[dict]) -> Panel:
    rows = VGroup()
    for e in entries:
        rows.add(got_row(e))
    rows.arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    return Panel(".got.plt", rows, width=4.6)


def got_row(e: dict) -> VGroup:
    role = "crash" if e["overwritten"] else ("libc" if e["resolved"] else "text_section")
    note = "system!" if e["overwritten"] else ("libc" if e["resolved"] else "resolver")
    row = VGroup(mono(f"{e['name']:<7}", 16, T.label), mono(h32(e["addr"]), 14, T.text_dim),
                 mono(h32(e["value"]), 16, getattr(T, role)), mono(note, 14, getattr(T, role))).arrange(RIGHT, buff=0.25)
    return row


class Mit82(StepWalkthrough):
    """
    VRIG mirrors the GOT into the stack sim's first 12 bytes, so the memory
    column is relabeled as the GOT slots rather than buf.
    """
    trace_name = "mit-82"
    # step 4 is about Partial RELRO but VRIG points at the Full RELRO comment
    line_fix = {4: 12}
    subtitle = "Lazy binding leaves the GOT writable. Full RELRO locks it."
    code_from = 3
    code_box = (5.2, 4.6)
    code_at = LEFT * 4.3 + UP * 0.6
    mem_at = RIGHT * 0.9 + UP * 1.4
    offsets = [0, 4, 8]
    captions = {
        0: "puts() goes through a PLT stub that jumps to whatever the GOT entry says.",
        1: "First call. The GOT points at the resolver, which writes in the real puts.",
        2: "Later calls jump straight to libc. The GOT stays writable.",
        3: "An arbitrary write puts system() in puts's slot. puts(\"/bin/sh\") becomes a shell.",
        4: "Partial RELRO moves .got ahead of .bss but leaves .got.plt writable.",
        5: "Full RELRO binds everything at load, then maps the GOT read-only.",
        6: "Full RELRO costs startup time and kills GOT overwrites.",
    }

    def make_mem(self):
        col = MemColumn(self.tr, self.offsets, step=0).move_to(self.mem_at)
        # these three words are the GOT, so show GOT addresses
        for k, e in enumerate(self.tr.aux(0)["got"]):
            lab = col.addr_labels[k * 4]
            lab.become(mono(h32(e["addr"]), 15, T.text_dim).move_to(lab, aligned_edge=RIGHT))
        return col

    def build(self):
        super().build()
        names = [e["name"] for e in self.tr.aux(0)["got"]]
        self.play(*(FadeIn(self.mem.tag(k * 4, 4, f"GOT[{n}]", "text_section")) for k, n in enumerate(names)))
        self.got = got_panel(self.tr.aux(0)["got"]).move_to(RIGHT * 2.4 + DOWN * 1.35)
        self.play(FadeIn(self.got, shift=UP * 0.2))
        self.got_aux = self.tr.aux(0)["got"]

    def update_got(self, st):
        new = st["aux"]["got"]
        if not new or new == self.got_aux:
            return
        anims = []
        for k, (a, b) in enumerate(zip(self.got_aux, new)):
            if a != b:
                row = self.got.body[k]
                nr = got_row(b).move_to(row, aligned_edge=LEFT)
                anims.append(Transform(row, nr))
        self.got_aux = new
        self.play(*anims)

    def flow(self, labels, role="pointer"):
        boxes = VGroup(*(VGroup(RoundedRectangle(width=1.5, height=0.45, corner_radius=0.06)
                                .set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.9), mono(l, 15, T.label))
                         for l in labels))
        for b in boxes:
            b[1].move_to(b[0])
        boxes.arrange(RIGHT, buff=0.55).move_to(LEFT * 3.6 + DOWN * 1.85)
        arrows = VGroup(*(Arrow(boxes[k].get_right(), boxes[k + 1].get_left(), buff=0.05)
                          .set_stroke(getattr(T, role), 3).set_fill(getattr(T, role)) for k in range(len(boxes) - 1)))
        return VGroup(boxes, arrows)

    def show_flow(self, labels, role="pointer"):
        f = self.flow(labels, role)
        old = getattr(self, "flow_m", None)
        anims = [FadeIn(f[0]), LaggedStartMap(GrowArrow, f[1], lag_ratio=0.4)]
        if old is not None:
            anims.append(FadeOut(old))
        self.play(*anims, run_time=1.2)
        self.flow_m = f

    def after_0(self, st):
        self.show_flow(["puts@plt", "GOT[puts]", "resolver"])

    def after_1(self, st):
        self.update_got(st)
        self.show_flow(["puts@plt", "GOT[puts]", "libc puts"], "libc")

    def after_2(self, st):
        self.update_got(st)

    def after_3(self, st):
        self.update_got(st)
        self.play(*self.mem.paint(0, 4, "attacker_bytes"))
        self.show_flow(["puts@plt", "GOT[puts]", "system"], "crash")

    def after_4(self, st):
        rw = mono(".got.plt  RW-", 16, T.crash).next_to(self.got, UP, buff=0.12, aligned_edge=RIGHT)
        self.play(FadeIn(rw))
        self.rw = rw

    def after_5(self, st):
        self.update_got(st)
        ro = mono(".got.plt  R--", 16, T.mitigation).move_to(self.rw, aligned_edge=RIGHT)
        lock = SurroundingRectangle(self.got, buff=0.06).set_stroke(T.mitigation, 3)
        self.play(FadeTransform(self.rw, ro), ShowCreation(lock), FadeOut(self.flow_m))
        # the sim's bytes still hold system(). VRIG only resets the panel.
        x = mono("write -> SIGSEGV", 15, T.mitigation).next_to(lock, DOWN, buff=0.1, aligned_edge=RIGHT)
        self.play(FadeIn(x))


def cfi_panel(targets: list[dict]) -> Panel:
    rows = VGroup(*(cfi_row(t) for t in targets)).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
    return Panel("valid void(int) targets", rows, width=3.9)


def cfi_row(t: dict) -> VGroup:
    ok = t["valid"]
    mark = mono("ok" if ok else "no", 15, T.win if ok else T.crash)
    row = VGroup(mono(f"{t['name']:<7}", 16, T.label), mono(h32(t["addr"]), 15, T.text_dim), mark).arrange(RIGHT, buff=0.3)
    if t.get("attempted"):
        row.add(mono("<- fptr", 15, T.crash).next_to(row, RIGHT, buff=0.2))
    return row


class Mit84(StepWalkthrough):
    trace_name = "mit-84"
    subtitle = "Check every indirect jump against a list made at compile time."
    code_from = 4
    code_box = (5.0, 5.0)
    code_at = LEFT * 4.4 + UP * 0.4
    mem_at = RIGHT * 1.2 + UP * 1.45
    mem_scale = 1.1
    offsets = [0, 4, 28, 32, 36]
    captions = {
        0: "fptr holds a code address. Without CFI, call *fptr goes wherever it points.",
        1: "Forward-edge CFI checks the target before the indirect call.",
        2: "Overwrite fptr with system(). Wrong type, not in the set, so the program aborts.",
        3: "Any other void(int) function still passes. CFI can't tell same-type targets apart.",
        4: "Backward edge. A shadow copy of the return address gets compared on ret.",
        5: "Forward and backward checks together stop pointer overwrites and ROP.",
    }

    def build(self):
        super().build()
        self.play(FadeIn(self.mem.tag(0, 4, "fptr", "pointer")))
        self.cfi = cfi_panel(self.tr.aux(0)["cfi"]).move_to(RIGHT * 4.4 + DOWN * 1.75)
        self.play(FadeIn(self.cfi, shift=UP * 0.2))
        self.cfi_aux = self.tr.aux(0)["cfi"]

    def update_cfi(self, st):
        new = st["aux"]["cfi"]
        if not new or new == self.cfi_aux:
            return
        anims = []
        for k, (a, b) in enumerate(zip(self.cfi_aux, new)):
            if a != b:
                row = self.cfi.body[k]
                anims.append(Transform(row, cfi_row(b).move_to(row, aligned_edge=LEFT)))
        self.cfi_aux = new
        self.play(*anims)

    def fptr_arrow(self, name, role):
        row = next(r for r, t in zip(self.cfi.body, self.cfi_aux) if t["name"] == name)
        return Arrow(self.mem.cells_in(0, 4).get_right(), row.get_left(), buff=0.15,
                     path_arc=-20 * DEG).set_stroke(getattr(T, role), 3).set_fill(getattr(T, role))

    def after_0(self, st):
        v = self.tr.word(0, 0)
        name = next(t["name"] for t in self.cfi_aux if t["addr"] == v)
        self.arrow = self.fptr_arrow(name, "win")
        self.play(GrowArrow(self.arrow))

    def after_2(self, st):
        self.update_cfi(st)
        self.play(*self.mem.paint(0, 4, "attacker_bytes"))
        new = self.fptr_arrow("system", "crash")
        self.play(Transform(self.arrow, new))
        abort = mono("__cfi_check -> abort", 16, T.crash).next_to(self.cfi, UP, buff=0.15)
        self.play(FadeIn(abort))
        self.abort = abort

    def after_3(self, st):
        rows = [r for r, t in zip(self.cfi.body, self.cfi_aux) if t["valid"]]
        self.play(FadeOut(self.abort), *(Indicate(r, color=T.highlight, scale_factor=1.05) for r in rows))

    def after_4(self, st):
        self.update_cfi(st)
        self.play(FadeOut(self.arrow), *self.mem.paint(28, 32, "mitigation"), *self.mem.paint(36, 40, "saved_ret"),
                  FadeIn(self.mem.tag(28, 4, "shadow copy", "mitigation")),
                  FadeIn(self.mem.tag(36, 4, "ret", "saved_ret")))
        eq = mono("==", 20, T.win).move_to(
            (self.mem.cells_in(28, 32).get_left() + self.mem.cells_in(36, 40).get_left()) / 2 + LEFT * 0.6)
        self.play(Write(eq))


class Mit85(StepWalkthrough):
    """Regular stack on the left, the shadow stack as its own column."""
    trace_name = "mit-85"
    subtitle = "The CPU keeps its own copy of every return address."
    code_from = 4
    code_box = (4.4, 5.2)
    code_at = LEFT * 4.8 + UP * 0.35
    mem_at = RIGHT * 0.3 + UP * 0.4
    offsets = [0, 4, 8, 12, 28, 32, 36]
    fields = [(0, 4, "ret copy", "saved_ret"), (8, 4, "target", "gadget"), (36, 4, "ret", "saved_ret")]
    captions = {
        0: "CET adds shadow stacks for returns and IBT for indirect jumps.",
        1: "CALL pushes the return address twice, once on each stack.",
        2: "RET pops both and compares them. A match means carry on.",
        3: "The overflow changes ret to 0x414141. The shadow copy still says 0x401020.",
        4: "IBT says an indirect call has to land on ENDBR64.",
        5: "Shadow stacks check every RET. IBT checks every indirect CALL and JMP.",
        6: "Both checks run in hardware and fault with #CP.",
    }

    def build(self):
        super().build()
        sh = self.tr.aux(0)["shadow"][0]
        self.shadow = self.shadow_box(sh)
        self.play(FadeIn(self.shadow, shift=LEFT * 0.2))
        self.sh_aux = sh

    def shadow_box(self, sh):
        val = mono(h32(sh["shadowRet"]), 18, T.mitigation)
        addr = mono(h32(sh["addr"]), 14, T.text_dim)
        cell = SurroundingRectangle(val, buff=0.14).set_stroke(T.mitigation, 2).set_fill(T.cell_fill, 0.9)
        body = VGroup(cell, val, addr)
        addr.next_to(cell, DOWN, buff=0.1)
        p = Panel("shadow stack", body, width=2.6)
        p.move_to(RIGHT * 5.3 + UP * 1.0)
        return p

    def compare(self, real, shadow, ok):
        role = "win" if ok else "crash"
        t = mono(f"{h32(real)} {'==' if ok else '!='} {h32(shadow)}", 17, getattr(T, role))
        t.next_to(self.shadow, DOWN, buff=0.4)
        return t

    def after_2(self, st):
        sh = st["aux"]["shadow"][0]
        c = self.compare(sh["realRet"], sh["shadowRet"], not sh["mismatch"])
        self.play(Indicate(self.mem.cells_in(36, 40), color=T.highlight), Indicate(self.shadow.body[1], color=T.highlight))
        self.play(FadeIn(c))
        self.cmp = c

    def after_3(self, st):
        sh = st["aux"]["shadow"][0]
        self.play(*self.mem.paint(36, 40, "attacker_bytes"))
        c = self.compare(sh["realRet"], sh["shadowRet"], not sh["mismatch"])
        cp = mono("#CP fault", 22, T.crash).next_to(c, DOWN, buff=0.2)
        self.play(FadeTransform(self.cmp, c))
        self.play(FadeIn(cp, scale=1.3), Flash(self.shadow, color=T.crash))
        self.cmp, self.cp = c, cp

    def after_4(self, st):
        self.play(FadeOut(self.cmp), FadeOut(self.cp), *self.mem.paint(8, 12, "gadget"))
        endbr = mono("f3 0f 1e fa = endbr64", 16, T.gadget).next_to(self.shadow, DOWN, buff=0.4)
        self.play(FadeIn(endbr))


# =============================================================================
# unit18-kernel
# =============================================================================


class Kern106(StepWalkthrough):
    """
    kern-106's vizActions write a 20-byte chain past kbuf, but StackSim's frame
    ends at ret, so in VRIG only the first gadget shows up. The trace was made
    with 16 bytes of extra room (see walk_stack-entry.ts) so the whole chain
    is visible.
    """
    trace_name = "kern-106"
    subtitle = "SMEP blocks a jump to user code. Kernel ROP turns SMEP off."
    code_from = 7
    code_box = (5.4, 4.0)
    code_at = LEFT * 3.9 + UP * 1.2
    mem_at = RIGHT * 2.2 + UP * 0.3
    offsets = [0, 60, 64, 68, 72, 76, 80]
    mem_scale = 1.1
    fields = [(0, 64, "kbuf[64]", "buffer"), (64, 4, "saved rbp", "saved_fp"), (68, 4, "ret", "saved_ret")]
    captions = {
        0: "copy_from_user copies 256 bytes into a 64-byte kernel buffer.",
        1: "Try 1. Aim ret at user code at 0x08048000. SMEP is on, so the CPU faults.",
        2: "Kernel ROP uses only kernel .text. The first gadget is pop rdi; ret.",
        3: "rdi gets 0x000406f0, a CR4 value with bit 20 off. mov cr4, rdi writes it.",
        4: "SMEP is off. The chain returns to commit_creds in kernel .text. That gives root.",
        5: "CR4 pinning, KPTI, FG-KASLR, and CFI make each of these steps harder.",
    }

    def build(self):
        super().build()
        # ring split: kernel addresses vs user addresses, as a strip on the left
        k = Rectangle(width=4.6, height=0.55).set_fill(T.kernel_space, 0.5).set_stroke(width=0)
        u = Rectangle(width=4.6, height=0.55).set_fill(T.user_space, 0.6).set_stroke(width=0)
        VGroup(k, u).arrange(DOWN, buff=0.4).move_to(LEFT * 4.0 + DOWN * 2.0)
        kl = mono("kernel .text  0xc0...", 15, T.text).move_to(k)
        ul = mono("user code  0x0804...", 15, T.text).move_to(u)
        self.ring = VGroup(k, kl, u, ul)
        self.cr4 = mono("CR4.SMEP (bit 20) = 1", 17, T.mitigation).next_to(VGroup(k, u), UP, buff=0.2)
        self.play(FadeIn(self.ring), FadeIn(self.cr4))

    def after_0(self, st):
        self.play(*self.mem.paint(64, 72, "kernel_space", 0.6))

    def after_1(self, st):
        self.play(*self.mem.paint(0, 64, "attacker_bytes"), *self.mem.paint(68, 72, "user_space"))
        arc = Arrow(self.mem.cells_in(68, 72).get_left() + LEFT * 1.4, self.ring[2].get_right(), buff=0.1,
                    path_arc=40 * DEG).set_stroke(T.crash, 3).set_fill(T.crash)
        fault = mono("SMEP fault", 20, T.text).move_to(self.ring[3])
        ul = self.ring[3].copy()
        self.play(GrowArrow(arc))
        self.play(FadeTransform(self.ring[3], fault), self.ring[2].animate.set_fill(T.crash, 0.7),
                  Flash(self.ring[2], color=T.crash))
        self.beat(pause=0.6)
        self.play(FadeOut(arc), FadeTransform(fault, ul), self.ring[2].animate.set_fill(T.user_space, 0.6))
        self.ring.submobjects[3] = ul

    def chain_arrow(self, off):
        return Arrow(self.mem.cells_in(off, off + 4).get_left() + LEFT * 1.4, self.ring[0].get_right(), buff=0.1,
                     path_arc=-30 * DEG).set_stroke(T.gadget, 3).set_fill(T.gadget)

    def after_2(self, st):
        self.play(*self.mem.paint(68, 72, "gadget"), FadeIn(self.mem.tag(68, 4, "pop rdi", "gadget", buff=1.3)))

    def after_3(self, st):
        self.play(*self.mem.paint(72, 76, "attacker_bytes"), *self.mem.paint(76, 80, "gadget"),
                  FadeIn(self.mem.tag(72, 4, "-> rdi", "attacker_bytes", buff=1.3)),
                  FadeIn(self.mem.tag(76, 4, "mov cr4, rdi", "gadget", buff=1.3)))
        v = self.tr.word(72, 3)
        off = mono(f"CR4 = {v:#010x}  SMEP = {(v >> 20) & 1}", 17, T.attacker_bytes).move_to(self.cr4)
        self.play(FadeTransform(self.cr4, off))
        self.cr4 = off

    def after_4(self, st):
        self.play(*self.mem.paint(80, 84, "win"), FadeIn(self.mem.tag(80, 4, "commit_creds", "win", buff=1.3)))
        a = self.chain_arrow(80).set_stroke(T.win).set_fill(T.win)
        root = mono("commit_creds  ->  uid=0", 17, T.win).move_to(self.ring[1])
        self.play(GrowArrow(a))
        self.play(FadeTransform(self.ring[1], root), self.ring[0].animate.set_stroke(T.win, 3))


# =============================================================================
# unit20-teaching-gaps. These steps carry no vizAction, so VRIG's stack view
# stays empty. The pictures here come from the log text and the extra runs
# recorded in the trace (stage3, partial).
# =============================================================================


class GapWalk(StepWalkthrough):
    """Code on the left, a free stage on the right. No memory column."""
    code_at = LEFT * 3.9 + UP * 0.35
    code_box = (5.8, 5.4)
    stage_at = RIGHT * 3.2 + UP * 0.35

    def build(self):
        self.code = self.make_code()
        self.mem = None
        self.play(FadeIn(self.code, shift=RIGHT * 0.3))
        self.stage()
        self.beat()

    def stage(self):
        pass

    def apply(self, st, run_time=0.8):
        line = st["execLine"] - self.code_from
        if st["execLine"] != self.exec_line and 0 <= line < len(self.code.lines):
            self.play(self.code.focus(line), run_time=0.6)
        self.exec_line = st["execLine"]

    def step(self, i, st):
        cap = self.captions.get(i)
        if cap:
            self.say(cap, run_time=0.5)
        self.apply(st)
        hook = getattr(self, f"after_{i}", None)
        if hook:
            hook(st)
        self.beat()


def word_cells(data: list[int], role: str) -> VGroup:
    from vrig.mob.memory import ByteCell, GAP
    return VGroup(*(ByteCell(b, role) for b in data)).arrange(RIGHT, buff=GAP)


class Gap111(GapWalk):
    trace_name = "gap-111"
    subtitle = "Leak the canary, leak libc, then overflow."
    code_from = 4
    captions = {
        0: "Three primitives in a row. Each one needs the one before it.",
        1: "Round 1. printf(buf) with %11$x prints the canary.",
        2: "Round 2. Leak a libc address and subtract its known offset.",
        3: "Round 3. Overflow with the right canary, then system() and \"/bin/sh\".",
        4: "Canary check passes, ret goes to system(\"/bin/sh\").",
    }

    def stage(self):
        s3 = self.tr.raw["stage3"]
        assert s3["solved"], "stage 3 payload didn't hold in StackSim, re-export"
        self.s3 = s3
        boxes = VGroup()
        for name in ("canary", "libc base", "ROP"):
            r = RoundedRectangle(width=1.7, height=0.55, corner_radius=0.08).set_stroke(T.grid, 1.5)
            boxes.add(VGroup(r, mono(name, 16, T.label).move_to(r)))
        boxes.arrange(RIGHT, buff=0.45).move_to(self.stage_at + UP * 2.2)
        arrows = VGroup(*(Arrow(boxes[k].get_right(), boxes[k + 1].get_left(), buff=0.05).set_stroke(T.text_dim, 2)
                          .set_fill(T.text_dim) for k in range(2)))
        self.boxes = boxes
        self.play(FadeIn(boxes), FadeIn(arrows))

    def done(self, k, role):
        b = self.boxes[k]
        return [b[0].animate.set_stroke(getattr(T, role), 3), b[1].animate.set_color(getattr(T, role))]

    def after_1(self, st):
        can = self.tr.raw["canaryValue"]
        t = mono(f"%11$x  ->  {can:08x}", 20, T.canary).move_to(self.stage_at + UP * 1.2)
        self.play(*self.done(0, "canary"), FadeIn(t, shift=UP * 0.1))
        self.can_t = t

    def after_2(self, st):
        s3 = self.s3
        sysa = self.tr.symbols["system"]
        lines = VGroup(
            mono(f"leaked system  {h32(sysa)}", 17, T.libc),
            mono(f"- offset       {h32(s3['baseSystem'])}", 17, T.text_dim),
            mono(f"= slide        {h32(s3['libcSlide'])}", 17, T.libc),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12).next_to(self.can_t, DOWN, buff=0.35)
        self.play(*self.done(1, "libc"), LaggedStartMap(FadeIn, lines, lag_ratio=0.3))
        self.libc_t = lines

    def after_3(self, st):
        s3 = self.s3
        self.play(FadeOut(self.libc_t), FadeOut(self.can_t), *self.done(2, "win"))
        mem = s3["memory"]
        lay = s3["layout"]
        rows = VGroup()
        labels = [(28, "AAAA ...", "attacker_bytes"), (32, "canary", "canary"), (36, "fake ebp", "saved_fp"),
                  (40, "system()", "libc"), (44, "dummy ret", "attacker_bytes"), (48, "&\"/bin/sh\"", "libc")]
        for off, name, role in labels:
            cells = word_cells(mem[off:off + 4], role)
            addr = mono(h32(lay["base"] + off), 14, T.text_dim).next_to(cells, LEFT, buff=0.2)
            lab = mono(name, 15, getattr(T, role)).next_to(cells, RIGHT, buff=0.2)
            rows.add(VGroup(addr, cells, lab))
        rows.arrange(UP, buff=0.08, aligned_edge=RIGHT).move_to(self.stage_at + DOWN * 0.3)
        self.play(LaggedStartMap(FadeIn, rows, shift=UP * 0.1, lag_ratio=0.15))
        self.rows = rows

    def after_4(self, st):
        ok = mono("canary intact", 17, T.win).next_to(self.rows[1], LEFT, buff=0.3)
        ret = mono(f"ret = {h32(self.s3['retAddr'])}", 17, T.win).next_to(self.rows[3], LEFT, buff=0.3)
        self.play(FadeIn(ok), FadeIn(ret))


class Gap112(GapWalk):
    """TOCTOU as two lanes on a time axis, with the symlink drawn above."""
    trace_name = "gap-112"
    subtitle = "The file can change between the check and the use."
    code_from = 4
    captions = {
        0: "access() checks a path. open() uses it later. The gap is a race window.",
        1: "access(\"userfile\") checks the real UID. userfile is the attacker's file, so it passes.",
        2: "In the window the attacker runs ln -sf /etc/shadow userfile.",
        3: "open(\"userfile\") follows the new link. The setuid program opens /etc/shadow.",
        4: "Open first and fstat the fd. An fd stays bound to one inode.",
    }

    def stage(self):
        c = self.stage_at
        axis = Arrow(c + LEFT * 2.7 + DOWN * 1.2, c + RIGHT * 2.9 + DOWN * 1.2, buff=0).set_stroke(T.text_dim, 2).set_fill(T.text_dim)
        tl = mono("time", 14, T.text_dim).next_to(axis, DOWN, buff=0.08).align_to(axis, RIGHT)
        prog = mono("setuid program", 18, T.label).move_to(c + LEFT * 1.9 + DOWN * 0.4)
        atk = mono("attacker", 18, T.attacker_bytes).move_to(c + LEFT * 2.2 + DOWN * 0.8)
        lane_p = DashedLine(c + LEFT * 0.9 + DOWN * 0.4, c + RIGHT * 2.8 + DOWN * 0.4).set_stroke(T.grid, 1.5)
        lane_a = DashedLine(c + LEFT * 0.9 + DOWN * 0.8, c + RIGHT * 2.8 + DOWN * 0.8).set_stroke(T.grid, 1.5)
        # symlink picture
        link = mono("userfile", 22, T.label).move_to(c + LEFT * 1.6 + UP * 1.4)
        owned = mono("owned.txt", 22, T.user_space).move_to(c + RIGHT * 1.6 + UP * 2.0)
        shadow = mono("/etc/shadow", 22, T.kernel_space).move_to(c + RIGHT * 1.6 + UP * 0.8)
        self.ptr = Arrow(link.get_right(), owned.get_left(), buff=0.1).set_stroke(T.pointer, 3).set_fill(T.pointer)
        self.link, self.owned, self.shadow_f = link, owned, shadow
        self.lanes = dict(p=c + DOWN * 0.4, a=c + DOWN * 0.8)
        self.play(GrowArrow(axis), FadeIn(tl), FadeIn(prog), FadeIn(atk), ShowCreation(lane_p), ShowCreation(lane_a),
                  FadeIn(link), FadeIn(owned), FadeIn(shadow), GrowArrow(self.ptr))

    def tick(self, x, lane, text, role):
        p = self.lanes[lane] + RIGHT * x
        dot = Dot(p, radius=0.07).set_fill(getattr(T, role))
        lab = mono(text, 17, getattr(T, role)).next_to(dot, UP if lane == "p" else DOWN, buff=0.08)
        return VGroup(dot, lab)

    def after_1(self, st):
        t = self.tick(-0.4, "p", "access() = 0", "win")
        self.play(FadeIn(t, scale=1.2), Indicate(self.owned, color=T.win))

    def after_2(self, st):
        win = Rectangle(width=1.7, height=0.75).set_stroke(width=0).set_fill(T.crash, 0.18)
        win.move_to(self.lanes["p"] + RIGHT * 0.65 + DOWN * 0.2)
        wl = mono("race window", 16, T.crash).next_to(win, UP, buff=0.35)
        t = self.tick(0.65, "a", "ln -sf", "attacker_bytes")
        new = Arrow(self.link.get_right(), self.shadow_f.get_left(), buff=0.1).set_stroke(T.attacker_bytes, 3).set_fill(T.attacker_bytes)
        self.play(FadeIn(win), FadeIn(wl), FadeIn(t, scale=1.2))
        self.play(Transform(self.ptr, new))

    def after_3(self, st):
        t = self.tick(1.8, "p", "open() as root", "crash")
        self.play(FadeIn(t, scale=1.2), Indicate(self.shadow_f, color=T.crash))


class Gap114(GapWalk):
    """
    Bits of the return address: the low 12 never move, the rest slide with
    ASLR. The brute force loop is real StackSim runs recorded in the trace.
    """
    trace_name = "gap-114"
    subtitle = "Change only the low bytes of ret. The page offset never moves."
    code_from = 4
    captions = {
        0: "ASLR moves the base. The low 12 bits, the page offset, stay the same.",
        1: "ret is 0xf7d2a825. Only 0x825 is fixed. win is always at page offset 0x7b0.",
        2: "One byte: 0x25 becomes 0xb0, giving 0xf7d2a8b0. Bits 8 to 11 are still wrong.",
        3: "Two bytes reach bits 8 to 15. Bits 12 to 15 are random, so 1 in 16 works.",
        4: "Retry until it hits. A forking server keeps one layout, so the odds hold.",
    }

    def stage(self):
        p = self.tr.raw["partial"]
        assert p["solved"]
        self.p = p
        self.addr = self.hex_digits(p["ret"]).move_to(self.stage_at + UP * 1.6)
        self.play(FadeIn(self.addr))

    def hex_digits(self, v, color=None) -> VGroup:
        s = f"{v:08x}"
        digits = VGroup(*(mono(ch, 30, color or T.text) for ch in s)).arrange(RIGHT, buff=0.06)
        return VGroup(mono("0x", 30, T.text_dim), digits).arrange(RIGHT, buff=0.06)

    def after_1(self, st):
        d = self.addr[1]
        rnd = Brace(d[0:5], DOWN, buff=0.1).set_color(T.attacker_bytes)
        fix = Brace(d[5:8], DOWN, buff=0.1).set_color(T.mitigation)
        rl = mono("ASLR", 18, T.attacker_bytes).next_to(rnd, DOWN, buff=0.06)
        fl = mono("page offset", 18, T.mitigation).next_to(fix, DOWN, buff=0.06).shift(DOWN * 0.32)
        self.play(GrowFromCenter(rnd), GrowFromCenter(fix), FadeIn(rl), FadeIn(fl),
                  d[0:5].animate.set_color(T.attacker_bytes), d[5:8].animate.set_color(T.mitigation))
        tgt = mono(f"win  {h32(self.p['target'])}", 22, T.win).next_to(self.addr, DOWN, buff=1.2)
        self.play(FadeIn(tgt))
        self.braces = VGroup(rnd, fix, rl, fl)
        self.tgt = tgt

    def show_try(self, run, label, y):
        v = self.hex_digits(run["ret"], T.text)
        v.scale(0.85)
        # color what the overwrite touched
        n = len(run["bytes"]) * 2
        v[1][8 - n:].set_color(T.attacker_bytes)
        res = mono("hit" if run["hit"] else "miss", 18, T.win if run["hit"] else T.crash)
        row = VGroup(mono(label, 20, T.label), v, res).arrange(RIGHT, buff=0.3).move_to(self.stage_at + DOWN * y)
        return row

    def after_2(self, st):
        row = self.show_try(self.p["oneByte"], "1 byte", 0.2)
        self.play(FadeIn(row, shift=UP * 0.1))
        self.one = row

    def after_3(self, st):
        tries = self.p["tries"]
        row = self.show_try(tries[0], "try  0", 1.0)
        self.play(FadeIn(row))
        for t in tries[1:]:
            new = self.show_try(t, f"try {t['nibble']:2d}", 1.0)
            self.play(FadeTransform(row, new), run_time=0.25 if not t["hit"] else 0.5)
            row = new
            if t["hit"]:
                self.play(Indicate(row, color=T.win, scale_factor=1.1), Indicate(self.tgt, color=T.win))
                break
        self.hit = row

    def after_4(self, st):
        p = self.p
        n = len(p["tries"])
        odds = mono(f"1 in {n}", 26, T.highlight).next_to(self.hit, DOWN, buff=0.45)
        self.play(FadeIn(odds, scale=1.2))


class Gap115(GapWalk):
    """
    setup() and leak() get the same stack slot one after the other. VRIG's
    steps carry no bytes here, so the cells show what lives in them by name.
    """
    trace_name = "gap-115"
    subtitle = "A new frame reuses old stack memory without wiping it."
    code_from = 4
    captions = {
        0: "C doesn't zero locals. A returned frame keeps its bytes until something overwrites them.",
        1: "setup() copies the canary and a libc address into secret[32], then returns.",
        2: "leak() gets the same stack slot. buf[32] starts with setup's leftovers.",
        3: "write(1, buf, 32) sends it all out. Two leaks from one read.",
        4: "Zero your buffers, or build with -ftrivial-auto-var-init=zero.",
    }

    def stage(self):
        c = self.stage_at
        slots = VGroup()
        for k in range(8):
            r = Rectangle(width=2.6, height=0.5).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            slots.add(r)
        slots.arrange(UP, buff=0.06).move_to(c + DOWN * 0.1)
        self.slots = slots
        self.frame_lab = mono("", 16, T.label)
        self.play(FadeIn(slots, lag_ratio=0.05))

    def label_frame(self, text, role):
        b = Brace(self.slots, LEFT, buff=0.15).set_color(getattr(T, role))
        t = mono(text, 19, getattr(T, role)).next_to(b, LEFT, buff=0.1)
        return VGroup(b, t)

    def after_1(self, st):
        f = self.label_frame("setup()\nsecret[32]", "local_var")
        can = mono("canary", 19, T.canary).move_to(self.slots[0])
        libc = mono("libc ptr", 19, T.libc).move_to(self.slots[1])
        self.play(FadeIn(f), self.slots[0].animate.set_fill(T.canary, 0.3), self.slots[1].animate.set_fill(T.libc, 0.3),
                  FadeIn(can), FadeIn(libc))
        self.beat(pause=0.4)
        ret = mono("setup() returns", 18, T.text_dim).next_to(self.slots, DOWN, buff=0.2)
        self.play(f.animate.set_opacity(0.3), FadeIn(ret))
        self.play(FadeOut(ret))
        self.f = f
        self.vals = VGroup(can, libc)

    def after_2(self, st):
        g = self.label_frame("leak()\nbuf[32]", "buffer")
        self.play(FadeTransform(self.f, g))
        self.play(Indicate(self.vals, color=T.highlight))

    def after_3(self, st):
        out = mono("stdout", 22, T.attacker_bytes).next_to(self.slots, RIGHT, buff=1.1)
        copies = self.vals.copy()
        self.play(FadeIn(out))
        self.play(*(c.animate.next_to(out, DOWN, buff=0.2 + 0.35 * k) for k, c in enumerate(copies)), run_time=1.2)
