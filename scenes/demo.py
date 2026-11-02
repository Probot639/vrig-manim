"""
The three booth challenges from VRIG's /demo, one video each. Every outcome
shown comes from traces/demo.json, which is VRIG's own demo logic run on
the inputs below (tools/vrig-trace/demo-entry.ts).

    manimgl scenes/demo.py DemoOverflow  -w --hd
    manimgl scenes/demo.py DemoAddresses -w --hd
    manimgl scenes/demo.py DemoCounter   -w --hd

Audience is whoever walks up to the booth, so the words stay plain. Hex and
addresses still show up on screen, they're what the demo shows too.
"""
import json

from manimlib import *

from vrig.mob.memory import GAP, ByteCell, mono, prose, tex
from vrig.mob.space import arc3d, billboard
from vrig.scene import Vrig3DScene, VrigScene
from vrig.theme import T
from vrig.trace import TRACE_DIR, h32

DEMO = json.loads((TRACE_DIR / "demo.json").read_text())

BUF, SAVED, RET = 16, 20, 24  # region ends, same split as MemoryDiagram.tsx


def glyph_for(state: dict, i: int) -> str:
    """Same rules MemoryDiagram uses to draw a slot."""
    written = state["written"][i]
    byte = state["memory"][i]
    typed = len(state["text"].encode())
    is_addr = written and state["ending"] is not None and i >= typed
    if not written and i < BUF:
        return "·"
    if written and not is_addr and 32 <= byte <= 126:
        return "␠" if byte == 32 else chr(byte)
    return f"{byte:02x}"


def role_for(state: dict, i: int) -> str:
    written = state["written"][i]
    typed = len(state["text"].encode())
    if not written:
        return "cell_fill"
    if state["ending"] is not None and i >= typed:
        return "win" if state["outcome"] == "success" else "crash"
    return "buffer" if i < BUF else "crash"


class DemoStrip(VGroup):
    """The booth's memory row: name buffer, saved frame, return address."""

    def __init__(self, state: dict, n: int = RET):
        self.n = n
        self.cells = VGroup(*(ByteCell(state["memory"][i], role_for(state, i), glyph=glyph_for(state, i))
                              for i in range(n)))
        groups = VGroup(self.cells[:BUF], self.cells[BUF:SAVED], self.cells[SAVED:RET])
        for g in groups:
            g.arrange(RIGHT, buff=GAP)
        groups.arrange(RIGHT, buff=0.28)

        self.labels = VGroup()
        for g, (name, note, role) in zip(groups, [
            ("name buffer", "16 bytes for your name", "buffer"),
            ("saved frame", "4 bytes", "saved_fp"),
            ("return address", "where to go next", "saved_ret"),
        ]):
            bar = Line(g.get_corner(DL), g.get_corner(DR)).shift(DOWN * 0.14).set_stroke(getattr(T, role), 4)
            top = mono(name, 17, getattr(T, role)).next_to(bar, DOWN, buff=0.12)
            sub = mono(note, 13, T.text_dim).next_to(top, DOWN, buff=0.06)
            self.labels.add(VGroup(bar, top, sub))
        super().__init__(self.cells, self.labels)
        # what each cell shows right now. compare against this, not a whole
        # state: typing one letter at a time means the strip is between states
        self.shown = [(glyph_for(state, i), role_for(state, i)) for i in range(n)]

    def ret_cells(self) -> VGroup:
        return self.cells[SAVED:RET]

    def morph(self, state: dict, only=None) -> list[Animation]:
        """Animations taking the shown cells to `state`. Cells that don't change are left alone."""
        anims = []
        for i in (range(self.n) if only is None else only):
            g, r = glyph_for(state, i), role_for(state, i)
            if (g, r) == self.shown[i]:
                continue
            cell = self.cells[i]
            anims.append(Transform(cell.label, cell.relabel(state["memory"][i], glyph=g)))
            anims.append(cell.box.animate.set_fill(getattr(T, r), 1 if r == "cell_fill" else 0.85))
            self.shown[i] = (g, r)
        return anims


def target_box(name: str, addr: int, role: str, width: float = 3.3) -> VGroup:
    box = RoundedRectangle(width=width, height=1.0, corner_radius=0.12)
    box.set_stroke(getattr(T, role), 3).set_fill(T.cell_fill, 1)
    t = mono(name, 22, T.text)
    a = mono(h32(addr), 16, T.text_dim)
    VGroup(t, a).arrange(DOWN, buff=0.08).move_to(box)
    return VGroup(box, t, a)


# ---------------------------------------------------------------------------

class DemoOverflow(VrigScene):
    """Challenge 1, walked through the slideshow's five beats."""

    def construct(self):
        d = DEMO["overflow"]
        st = d["states"]
        slides = {s["id"]: s for s in d["slides"]}

        title = prose(d["title"], 46).to_edge(UP, buff=0.35)
        self.play(Write(title))
        self.say("A program sets aside 16 bytes for your name. It never checks how much you type.")
        self.beat()
        self.play(title.animate.scale(0.55).to_corner(UL, buff=0.25))

        strip = DemoStrip(st["empty"]).move_to(DOWN * 0.7)
        sym = st["name"]["symbols"]
        main_box = target_box("back to main()", sym["normal"], "label").move_to(LEFT * 2.4 + UP * 2.0)
        admin_box = target_box("admin()", sym["admin"], "win").move_to(RIGHT * 2.0 + UP * 2.0)
        self.play(FadeIn(strip, lag_ratio=0.02), FadeIn(main_box), FadeIn(admin_box))

        heading = self.heading(slides["name"]["title"])

        # it starts with a name
        name = st["name"]
        for i in range(len(name["text"])):
            self.play(*strip.morph(name, only=[i]), run_time=0.14)
        arrow = self.jump(strip, main_box, T.label)
        self.play(ShowCreation(arrow))
        self.say("Each letter takes one slot. Taylor fits fine, so the program goes back to main().")
        self.beat()

        # too much input spills over
        self.play(FadeOut(arrow))
        heading = self.heading(slides["overflow"]["title"], heading)
        self.say("There's no length check. Keep typing.")
        for state, rng in ((st["full"], range(6, 16)), (st["spill"], range(16, 20)), (st["crash"], range(20, 24))):
            for i in rng:
                self.play(*strip.morph(state, only=[i]), run_time=0.11 if i < BUF else 0.2)
            if state is st["spill"]:
                self.say("Past byte 16 the letters land on saved data. Nothing stops them.")
                self.beat(pause=0.4)
        self.say("Four more and they reach the return address.")
        self.beat()

        # the program crashes
        heading = self.heading(slides["crash"]["title"], heading)
        crash = st["crash"]
        assert crash["outcome"] == "crash"
        value = self.read_back(strip, crash["destination"], T.crash)
        nowhere = target_box("nothing here", crash["destination"], "crash", width=3.0)
        nowhere.move_to(RIGHT * 5.4 + UP * 2.0)
        arrow = self.jump(strip, nowhere, T.crash)
        self.play(FadeIn(nowhere), ShowCreation(arrow))
        self.play(Flash(nowhere, color=T.crash, flash_radius=1.0), WiggleOutThenIn(nowhere))
        self.say("The return address says where to go next. Four exclamation marks make 0x21212121, and no code lives there.")
        self.beat()

        # give the overflow a destination
        heading = self.heading(slides["repair"]["title"], heading)
        self.play(FadeOut(arrow), FadeOut(nowhere), FadeOut(value))
        spill = st["spill"]
        self.play(*strip.morph(spill, only=range(20, 24)), run_time=0.6)
        self.say("Keep 20 bytes of padding. The next 4 bytes become the address of admin().")
        self.beat()

        admin = st["admin"]
        addr_txt = admin_box[2]
        hexpairs = [f"{b:02x}" for b in admin["destination"].to_bytes(4, "big")]  # 08 04 81 50
        pieces = VGroup(*(mono(p, 18, T.win) for p in hexpairs)).arrange(RIGHT, buff=0.06)
        pieces.next_to(addr_txt, DOWN, buff=0.15)
        self.play(TransformFromCopy(addr_txt, pieces))
        # most significant byte ends up last. backwards on purpose
        ret = strip.ret_cells()
        self.play(*[pieces[3 - k].animate.move_to(ret[k]).set_opacity(0) for k in range(4)],
                  *strip.morph(admin, only=range(20, 24)), run_time=1.4)
        self.remove(pieces)
        self.say("The bytes go in backwards. 0x08048150 is stored as 50 81 04 08.")
        self.beat()

        # guest becomes admin
        heading = self.heading(slides["admin"]["title"], heading)
        assert admin["outcome"] == "success"
        value = self.read_back(strip, admin["destination"], T.win)
        arrow = self.jump(strip, admin_box, T.win)
        self.play(ShowCreation(arrow))
        self.play(admin_box[0].animate.set_fill(T.win, 0.35), Flash(admin_box, color=T.win, flash_radius=1.2))
        self.say(d["takeaway"])
        self.beat(pause=3)

    def heading(self, text: str, old=None) -> Text:
        new = prose(text, 30, T.highlight).to_corner(UR, buff=0.3)
        self.play(FadeIn(new, shift=DOWN * 0.15), *([FadeOut(old, shift=UP * 0.15)] if old else []))
        return new

    def jump(self, strip, box, color) -> Arrow:
        start = strip.ret_cells().get_top() + UP * 0.05
        return CurvedArrow(start, box.get_bottom() + DOWN * 0.05, angle=-30 * DEG if box.get_x() < start[0] else 30 * DEG,
                           color=color, stroke_width=5)

    def read_back(self, strip, value: int, color) -> Text:
        txt = mono(h32(value), 22, color).next_to(strip.ret_cells(), UP, buff=0.25)
        self.play(*[TransformFromCopy(c.label, txt) for c in strip.ret_cells()], run_time=0.8)
        return txt


# ---------------------------------------------------------------------------

LO, HI = 0x08040000, 0x08080000
SPAN = 10.0


def ax(addr: int) -> float:
    """Address to x on the floor. 256 KiB of address space across the frame."""
    return -SPAN / 2 + (addr - LO) * SPAN / (HI - LO)


class DemoAddresses(Vrig3DScene):
    """Challenge 2. admin() moves, an old exploit breaks, a leak fixes it."""

    def construct(self):
        d = DEMO["addresses"]
        before, after = d["before"], d["after"]
        frame = self.frame
        frame.reorient(-10, 56, 0, center=(0, -1.8, 0.0), height=8.2)

        title = prose(d["title"], 44).to_edge(UP, buff=0.35).fix_in_frame()
        self.play(Write(title))
        self.say("Same bug as before, 20 bytes of name and then a 4-byte destination. This time admin() moves.")
        self.beat()
        self.play(FadeOut(title))

        # address ruler along the floor
        ruler = Line([ax(LO), 0, 0], [ax(HI), 0, 0]).set_stroke(T.grid, 3)
        ticks = VGroup()
        for a in range(LO, HI + 1, 0x8000):
            tick = Line([ax(a), -0.12, 0], [ax(a), 0.12, 0]).set_stroke(T.grid, 2)
            lab = mono(f"{a:08x}", 17, T.text_dim).move_to([ax(a), -0.45, 0])
            billboard(lab, frame)
            ticks.add(VGroup(tick, lab))
        axis_lab = billboard(mono("program memory", 20, T.text_dim).move_to([ax(HI) - 0.9, 0.55, 0]), frame)
        self.play(ShowCreation(ruler), FadeIn(ticks, lag_ratio=0.05), FadeIn(axis_lab))

        code = self.code_slab(before)
        self.play(FadeIn(code, shift=OUT * 0.4))

        # the input row, laid on the floor in front
        st_old = d["states"]["oldAim"]
        strip = DemoStrip(st_old).scale(0.8).move_to([0, -2.3, 0])
        # first show it as it worked before the move, which is the overflow challenge's win
        worked = dict(st_old, outcome="success")
        for i in range(20, 24):
            strip.cells[i].paint(role_for(worked, i))
            strip.shown[i] = (glyph_for(worked, i), role_for(worked, i))
        self.play(FadeIn(strip, lag_ratio=0.02))

        admin_blk = code[1]
        hop = arc3d(strip.ret_cells().get_top(), admin_blk.get_top(), lift=1.8, color=T.win)
        self.play(ShowCreation(hop), run_time=1.2)
        self.play(Indicate(admin_blk, color=T.win))
        self.say(f"Aimed at {h32(before['admin'])}, this input became admin last time.")
        self.beat()

        # admin() moves
        self.play(FadeOut(hop))
        self.say("Run the program again and the code loads somewhere else.")
        shift = RIGHT * (ax(after["admin"]) - ax(before["admin"]))
        self.play(code.animate.shift(OUT * 1.2), run_time=0.6)
        self.play(code.animate.shift(shift), run_time=2.0)
        self.play(code.animate.shift(IN * 1.2), run_time=0.8)
        # the labels ride along inside `code`, so swap them once it's landed.
        # doing both in one play() fights over the same points and blows up
        new_labels = self.code_labels(after, code)
        self.play(*[Transform(o, n) for o, n in zip(self.addr_labels, new_labels)], run_time=0.6)
        self.beat()

        # the old input now jumps into nothing
        assert st_old["outcome"] == "crash" and st_old["destination"] == before["admin"]
        for i in range(20, 24):
            strip.cells[i].paint(role_for(st_old, i))
            strip.shown[i] = (glyph_for(st_old, i), role_for(st_old, i))
        land = np.array([ax(before["admin"]), 0.9, 0])
        miss = arc3d(strip.ret_cells().get_top(), land, lift=1.8, color=T.crash)
        cross = VGroup(Line(UL, DR), Line(UR, DL)).scale(0.3).set_stroke(T.crash, 8).move_to(land + OUT * 0.02)
        self.play(ShowCreation(miss), run_time=1.2)
        self.play(FadeIn(cross, scale=1.6))
        self.say(f"The old input still jumps to {h32(before['admin'])}. Nothing is there anymore, so it crashes.")
        self.beat()

        # the leak
        leak = VGroup(
            mono("$ ./login", 20, T.text_dim),
            mono(f"[debug] admin() is at {h32(after['admin'])}", 20, T.highlight),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        panel = SurroundingRectangle(leak, buff=0.25).set_stroke(T.grid, 2).set_fill(T.background, 0.92)
        term = VGroup(panel, leak).to_corner(UL, buff=0.35).fix_in_frame()
        self.play(FadeIn(term, shift=LEFT * 0.3))
        self.say("A forgotten debug message prints the new address.")
        self.beat()

        # aim at the leak
        st_new = d["states"]["leakAim"]
        assert st_new["outcome"] == "success" and st_new["destination"] == after["admin"]
        self.play(FadeOut(miss), FadeOut(cross))
        self.play(*strip.morph(st_new, only=range(20, 24)), run_time=1.0)
        hit = arc3d(strip.ret_cells().get_top(), admin_blk.get_top(), lift=1.8, color=T.win)
        self.play(ShowCreation(hit), run_time=1.2)
        self.play(admin_blk.animate.set_color(T.win), Indicate(admin_blk, color=T.win))
        self.say(d["takeaway"])
        frame.add_ambient_rotation(2 * DEG)
        self.wait(4)
        frame.clear_updaters()
        self.beat(pause=2)

    def code_slab(self, sym: dict) -> Group:
        x = ax(sym["admin"])
        main_blk = Prism(1.7, 0.7, 0.3, color=T.label, opacity=0.9).move_to([x - 1.9, 0.9, 0.15])
        admin_blk = Prism(1.7, 0.7, 0.3, color=T.gadget, opacity=0.9).move_to([x, 0.9, 0.15])
        base = Prism(4.1, 1.1, 0.06, color=T.text_section, opacity=0.6).move_to([x - 0.95, 0.9, 0.0])
        g = Group(main_blk, admin_blk, base)
        names = VGroup(mono("main()", 18, T.text), mono("admin()", 18, T.text))
        for n, blk in zip(names, (main_blk, admin_blk)):
            n.move_to(blk.get_center())
            billboard(n, self.frame)
            n.shift(OUT * 0.55)
        self.addr_labels = self.code_labels(sym, g)
        g.add(names, self.addr_labels)
        return g

    def code_labels(self, sym: dict, g) -> VGroup:
        out = VGroup()
        for addr, blk in ((sym["normal"], g[0]), (sym["admin"], g[1])):
            lab = mono(h32(addr), 14, T.text_dim).move_to(blk.get_center())
            billboard(lab, self.frame)
            out.add(lab.shift(OUT * 0.3))
        return out


# ---------------------------------------------------------------------------

class DemoCounter(VrigScene):
    """Challenge 3. An 8-bit size wraps and the buffer comes out tiny."""

    def construct(self):
        d = DEMO["counter"]
        runs = {r["requested"]: r for r in d["runs"]}

        title = prose(d["title"], 46).to_edge(UP, buff=0.35)
        self.play(Write(title))
        self.say("This toy program keeps its sizes in a counter that only holds 0 to 255.")
        self.beat()
        self.play(title.animate.scale(0.55).to_corner(UL, buff=0.25))

        center = LEFT * 3.6 + UP * 0.2
        R = 2.2
        dial = Circle(radius=R).move_to(center).set_stroke(T.grid, 3)
        ticks = VGroup()
        for v in range(0, 256, 4):
            ang = PI / 2 - TAU * v / 256
            inner = R - (0.28 if v % 32 == 0 else 0.12)
            ticks.add(Line(center + inner * np.array([np.cos(ang), np.sin(ang), 0]),
                           center + R * np.array([np.cos(ang), np.sin(ang), 0])).set_stroke(T.grid, 2))
        nums = VGroup()
        for v in (0, 64, 128, 192):
            ang = PI / 2 - TAU * v / 256
            nums.add(mono(str(v), 18, T.text_dim).move_to(center + (R + 0.35) * np.array([np.cos(ang), np.sin(ang), 0])))
        top = mono("255 | 0", 15, T.crash).move_to(center + UP * (R + 0.75))

        val = ValueTracker(0)

        def needle_tip():
            ang = PI / 2 - TAU * val.get_value() / 256
            return center + (R - 0.35) * np.array([np.cos(ang), np.sin(ang), 0])

        needle = always_redraw(lambda: Line(center, needle_tip()).set_stroke(T.highlight, 5))
        hub = Dot(center, radius=0.08).set_fill(T.highlight)
        readout = always_redraw(lambda: mono(str(int(round(val.get_value())) & 0xFF), 40, T.text)
                                .move_to(center + DOWN * 0.75))
        cap_lab = mono("counter", 16, T.text_dim).move_to(center + DOWN * 1.3)
        self.play(ShowCreation(dial), FadeIn(ticks), FadeIn(nums), FadeIn(top), FadeIn(hub), FadeIn(cap_lab))
        self.add(needle, readout)

        # the right half: the arithmetic, then memory
        math_anchor = RIGHT * 2.6 + UP * 2.2
        mem_anchor = RIGHT * 2.6 + DOWN * 1.4
        self.math = None
        self.mem = None

        self.say("Size is your request plus 8 bytes of overhead. Start small.")
        self.show_run(runs[100], val, math_anchor, mem_anchor)
        self.say("100 plus 8 is 108. The counter holds it, and 100 bytes fit in 108.")
        self.beat()

        self.show_run(runs[247], val, math_anchor, mem_anchor)
        self.say("247 plus 8 is 255, the most the counter can hold.")
        self.beat()

        self.show_run(runs[248], val, math_anchor, mem_anchor, show_bits=True)
        self.say("One more and the size wraps to 0. The ninth bit has nowhere to go.")
        self.beat()

        self.show_run(runs[250], val, math_anchor, mem_anchor, show_bits=True, spill=True)
        self.say(d["takeaway"])
        self.beat(pause=3)

    def show_run(self, r: dict, val, math_anchor, mem_anchor, show_bits=False, spill=False):
        req, total, alloc = r["requested"], r["mathematicalSize"], r["allocated"]
        assert alloc == total & 0xFF and r["wrapped"] == (total > 255)

        lines = VGroup(
            tex(rf"\text{{requested}} = {req}", 40),
            tex(rf"\text{{size}} = {req} + {r['overhead']} = {total}", 40),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to(math_anchor)
        anims = [FadeIn(lines, shift=UP * 0.1)]
        if self.math is not None:
            anims.append(FadeOut(self.math))
        if self.mem is not None:
            anims.append(FadeOut(self.mem))
            self.mem = None
        self.play(*anims, val.animate.set_value(0), run_time=0.6)
        self.math = lines
        self.play(val.animate.set_value(total), run_time=1.8 if total > 200 else 1.2, rate_func=smooth)

        if show_bits:
            bits = f"{total:09b}"
            digits = VGroup(*(mono(b, 28, T.crash if i == 0 else T.text) for i, b in enumerate(bits)))
            digits.arrange(RIGHT, buff=0.06)
            # space every four, counting from the right like a person would
            for i, dg in enumerate(digits):
                dg.shift(RIGHT * 0.14 * ((9 - i - 1) // 4 * -1 + 2))
            digits.next_to(lines, DOWN, buff=0.35, aligned_edge=LEFT)
            kept = mono(f"= {alloc}", 28, T.crash).next_to(digits, RIGHT, buff=0.3)
            mod = tex(rf"{total} \bmod 256 = {alloc}", 36, T.crash).next_to(digits, DOWN, buff=0.3, aligned_edge=LEFT)
            self.play(FadeIn(digits, lag_ratio=0.1))
            self.play(digits[0].animate.shift(DOWN * 0.8).set_opacity(0), FadeIn(kept), run_time=1.0)
            self.play(Write(mod))
            lines.add(digits, kept, mod)

        # memory: reserved block, then whatever lives after it
        scale = 5.6 / 270
        w_alloc = max(alloc * scale, 0.12)
        reserved = Rectangle(width=w_alloc, height=0.6).set_stroke(T.buffer, 3).set_fill(T.buffer, 0.5)
        neighbor = Rectangle(width=2.0, height=0.6).set_stroke(T.grid, 2).set_fill(T.cell_fill, 1)
        neighbor_lab = mono("other data", 15, T.text_dim).move_to(neighbor)
        row = VGroup(reserved, VGroup(neighbor, neighbor_lab)).arrange(RIGHT, buff=0)
        row.move_to(mem_anchor).align_to(mem_anchor + LEFT * 2.8, LEFT)
        res_lab = mono(f"reserved: {alloc} bytes", 16, T.buffer).next_to(row, UP, buff=0.15, aligned_edge=LEFT)
        self.play(FadeIn(row), FadeIn(res_lab))

        copy = Rectangle(width=req * scale, height=0.3).set_stroke(width=0)
        copy.set_fill(T.attacker_bytes, 0.9).align_to(reserved, LEFT).move_to(reserved, coor_mask=np.array([0, 1, 0]))
        copy_lab = mono(f"copy: {req} bytes", 16, T.attacker_bytes).next_to(row, DOWN, buff=0.15, aligned_edge=LEFT)
        self.play(GrowFromEdge(copy, LEFT), FadeIn(copy_lab), run_time=1.4)

        over = req > alloc
        if over:
            self.play(neighbor.animate.set_fill(T.crash, 0.6), neighbor_lab.animate.set_color(T.text),
                      Flash(neighbor, color=T.crash, flash_radius=1.0))
        self.mem = VGroup(row, res_lab, copy, copy_lab)
        assert over == r["success"] or not r["wrapped"]
