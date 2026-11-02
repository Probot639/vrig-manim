"""
Unit 3: Stack II. Pilot for the visual language, so expect this file to be
the one other units copy from.

    manimgl scenes/unit3_stack_ii.py RopBasics            # live window
    manimgl scenes/unit3_stack_ii.py RopBasics -p         # presenter, arrows step
    manimgl scenes/unit3_stack_ii.py RopBasics -w --hd    # mp4
"""
from manimlib import *

from vrig.mob.cpu import CodeListing, RegisterFile
from vrig.mob.memory import CELL, PayloadStrip, StackView, le_assemble, mono, prose
from vrig.mob.space import arc3d, billboard
from vrig.scene import Vrig3DScene
from vrig.theme import T
from vrig.trace import StackTrace, h32


class CodeBlock(Group):
    """A chunk of executable bytes standing up off the floor."""

    def __init__(self, title: str, addr: int, role: str, frame, width=2.9, depth=0.62, height=0.32):
        self.slab = Prism(width, depth, height, color=getattr(T, role), opacity=0.9)
        self.slab.shift(OUT * height / 2)
        self.top_z = height + 0.01
        self.title = mono(title, 22, T.text)
        self.addr = mono(h32(addr), 15, T.text_dim)
        lab = VGroup(self.title, self.addr).arrange(DOWN, buff=0.06)
        lab.move_to(self.slab.get_center())
        # stood up facing the camera, floating just over the slab's front edge
        billboard(lab, frame)
        lab.shift(OUT * (height + 0.32) + DOWN * depth * 0.2)
        self.lab = lab
        self.role = role
        super().__init__(self.slab, lab)

    def top(self):
        return self.slab.get_center() * np.array([1, 1, 0]) + OUT * self.top_z


class RopBasics(Vrig3DScene):
    trace_name = "stack2-12"

    def construct(self):
        tr = StackTrace.load(self.trace_name)
        assert tr.won(), "trace payload doesn't actually win, re-export it"
        self.tr = tr
        self.frame.reorient(0, 0)

        self.act_overflow()
        self.act_chain()

    # -- act 1: flat. the payload lands -----------------------------------

    def act_overflow(self):
        tr = self.tr
        title = prose("ROP Basics", 48).to_edge(UP, buff=0.4)
        sub = prose("NX is on, so nothing on the stack can run.", 26, T.text_dim)
        sub.next_to(title, DOWN, buff=0.2)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()

        src = [l for l in tr.source if not l.startswith("#include")]
        code = CodeListing(src, size=17).to_corner(UL, buff=0.5).shift(DOWN * 0.45)
        stack = StackView(tr, n_words=len(tr.payload) // tr.word).shift(RIGHT * 1.9 + UP * 0.1)
        tags = stack.frame_tags()

        self.play(FadeOut(sub), title.animate.scale(0.6).to_corner(UL, buff=0.25),
                  FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.3))
        self.stack, self.title, self.code = stack, title, code
        self.beat()

        gets_line = next(i for i, l in enumerate(src) if "gets(" in l)
        self.play(code.focus(gets_line))
        self.say("gets() copies until newline. It has no idea how big buf is.")

        strip = PayloadStrip(tr.payload).next_to(code, DOWN, buff=0.45, aligned_edge=LEFT)
        strip_lab = mono("input", 16, T.text_dim).next_to(strip, UP, buff=0.12, aligned_edge=LEFT)
        self.play(FadeIn(strip_lab), FadeIn(strip, lag_ratio=0.02, run_time=1.2))
        self.beat()

        # walk VRIG's own gets() steps, one word each
        w = tr.word
        for step in tr.steps:
            if not step["label"].startswith("gets(): write"):
                continue
            off = step["hl"][0]
            data = step["memory"][off:off + w]
            src_cells = strip.cells[off:off + w]
            self.play(
                *[TransformFromCopy(sc, c, path_arc=-20 * DEG) for sc, c in zip(src_cells, stack.at(off).cells)],
                src_cells.animate.set_opacity(0.2),
                run_time=0.45 if off < tr.buf_size else 0.7,
            )
            over = tr.buf_size <= off <= tr.ret_off
            self.play(*stack.write_word(off, data, "attacker_bytes", overflow=over), run_time=0.3)
            if off == tr.ebp_off:
                self.say("Past the end of buf. Saved ebp goes first.", run_time=0.5)
            if off == tr.ret_off:
                self.say("Then the return address. ret will trust whatever is here.", run_time=0.5)
                self.beat()

        self.play(FadeOut(strip), FadeOut(strip_lab), FadeOut(tags))
        self.say("Read each overwritten word back the way the CPU will.")
        self.beat()

        meanings = VGroup()
        for off in range(tr.ret_off, len(tr.payload), w):
            name, role = self.meaning(tr.word_at(off))
            word = stack.at(off)
            value, anims = le_assemble(word)
            self.play(*anims, run_time=0.6)
            m = mono(name, 16, getattr(T, role)).next_to(value, RIGHT, buff=0.25)
            self.play(FadeIn(m, shift=LEFT * 0.15), word.boxes().animate.set_fill(getattr(T, role), 0.85),
                      run_time=0.4)
            meanings.add(VGroup(value, m))
        self.say("That's a list of return addresses now, with data mixed in.")
        self.meanings = meanings
        self.beat()

    def meaning(self, v: int) -> tuple[str, str]:
        tr = self.tr
        if v in tr.gadgets:
            return tr.gadgets[v], "gadget"
        for name, addr in tr.symbols.items():
            if addr == v:
                return f"{name}()", "win"
        if v == tr.flag_addr:
            return "&flag_check", "attacker_bytes"
        return "data", "attacker_bytes"

    # -- act 2: tilt into 3d. the chain runs -------------------------------

    def act_chain(self):
        tr, stack, frame = self.tr, self.stack, self.frame
        self.play(FadeOut(self.code), FadeOut(self.meanings), FadeOut(self.title))
        self.unsay()

        # tags were faded out in act 1 but they're still in the stack's family,
        # so moving the stack drags them back. Bring them back on purpose instead:
        # in 3d they're what tells you which slot was the return address.
        stack.tags.set_opacity(0)
        self.play(stack.animate.shift(LEFT * 3.5))
        self.play(stack.tags.animate.set_opacity(1), run_time=0.5)
        self.play(frame.animate.reorient(-24, 50, 0, center=(0.9, 0.0, 0.6), height=9.2), run_time=2.5)

        # code lives somewhere else entirely: .text and .data off to the right.
        # blocks get built after the tilt so their labels can face the camera.
        order = sorted(set(tr.gadgets) | {tr.symbols["win"]})
        blocks = {}
        text_group = Group()
        for addr in order:
            name, role = self.meaning(addr)
            blocks[addr] = CodeBlock(name, addr, role, frame)
            text_group.add(blocks[addr])
        text_group.arrange(UP, buff=0.55).move_to(RIGHT * 3.6 + DOWN * 0.6)
        text_lab = billboard(mono(".text  r-x", 20, T.text_dim).next_to(text_group, DOWN, buff=0.35), frame)

        flag = CodeBlock("flag_check = 0", tr.flag_addr, "cell_fill", frame, width=2.6)
        flag.move_to(RIGHT * 3.6 + UP * 3.3)
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

        def esp_to(off):
            return esp_arrow.animate.next_to(stack.at(off), LEFT, buff=0.12)

        esp_arrow.next_to(stack.at(tr.ret_off), LEFT, buff=0.12)
        self.play(FadeIn(esp_arrow), *regs.set("esp", tr.addr(tr.ret_off), role="label"))
        self.beat()

        trail = VGroup()
        src_off = tr.ret_off  # slot the next eip gets popped from
        esp = tr.ret_off + w
        eip = tr.word_at(tr.ret_off)

        for ev in tr.rop_events():
            assert ev.addr == eip, f"trace disagrees with stack: {h32(ev.addr)} vs {h32(eip)}"
            blk = blocks[ev.addr]
            jump = arc3d(stack.at(src_off).cells.get_right(), blk.top())
            self.play(ShowCreation(jump), stack.at(src_off).cells.animate.set_opacity(0.35), esp_to(esp),
                      *regs.set("eip", ev.addr), *regs.set("esp", tr.addr(esp), role="label"),
                      run_time=1.1)
            trail.add(jump)
            self.play(blk.slab.animate.set_color(T.highlight), run_time=0.3)
            self.say(f"ret pops {h32(ev.addr)} into eip and lands on  {ev.text}", run_time=0.4)

            for reg, val in ev.pops:
                slot = stack.at(esp)
                self.play(Indicate(slot.cells, color=T.highlight, scale_factor=1.05), *regs.set(reg, val))
                slot.cells.set_opacity(0.35)
                esp += w
                self.play(esp_to(esp), *regs.set("esp", tr.addr(esp), role="label"), run_time=0.4)

            if ev.write:
                val, addr = ev.write
                assert addr == tr.flag_addr
                hop = arc3d(blk.top(), flag.top(), lift=1.2, color=T.attacker_bytes)
                # same size as the old title. billboard() rotates in place, so
                # measure first, rotate second
                newlab = mono(f"flag_check = {val:#x}", 22, T.text).move_to(flag.title)
                billboard(newlab, frame)
                self.play(ShowCreation(hop), run_time=0.8)
                self.play(flag.slab.animate.set_color(T.attacker_bytes), FadeTransform(flag.title, newlab))
                self.say("Three gadgets add up to mov [ebx], eax, which writes any value to any address.")
                trail.add(hop)

            self.play(blk.slab.animate.set_color(getattr(T, blk.role)), run_time=0.3)
            self.beat(pause=0.4)
            src_off, eip = esp, ev.next_eip
            esp += w

        # last ret goes to win()
        assert eip == tr.symbols["win"]
        win = blocks[eip]
        jump = arc3d(stack.at(src_off).cells.get_right(), win.top(), color=T.win)
        self.play(ShowCreation(jump), stack.at(src_off).cells.animate.set_opacity(0.35), esp_to(esp - w),
                  *regs.set("eip", eip, role="win"), run_time=1.1)
        trail.add(jump)
        self.play(win.slab.animate.set_color(T.win).stretch(2.4, 2, about_edge=IN),
                  win.lab.animate.shift(OUT * 0.45))
        self.say("win() finds flag_check == 0xdeadbeef.   FLAG{rop_chain}")
        self.beat()

        # back off and look at the whole thing
        self.play(trail.animate.set_stroke(width=7),
                  frame.animate.reorient(-40, 58, 0, center=(0.8, 0.2, 0.8), height=10.0), run_time=2)
        self.say("NX never fired. Every instruction that ran came from .text.")
        frame.add_ambient_rotation(3 * DEG)
        self.wait(5)
        frame.clear_updaters()
        self.beat(pause=1.5)

    def esp_marker(self) -> VGroup:
        tri = Triangle().rotate(-90 * DEG).set_height(CELL * 0.5)
        tri.set_fill(T.highlight, 1).set_stroke(width=0)
        lab = mono("esp", 18, T.highlight).next_to(tri, LEFT, buff=0.1)
        return VGroup(lab, tri)
