"""
Template for making a stack video by hand. Copy this file, change TRACE
and the captions, and you have a new scene. VRIG.md walks through the
whole thing (payload, trace, scene, render).

    manimgl scenes/example_by_hand.py ExampleByHand -w -l    # quick look
    manimgl scenes/example_by_hand.py ExampleByHand -w --hd  # mp4

The example plays back the ROP Basics trace that's already committed, so
it needs nothing new from VRIG.
"""
from manimlib import *

from vrig.mob.cpu import CodeListing
from vrig.mob.memory import PayloadStrip, StackView, le_assemble, mono, prose
from vrig.scene import VrigScene
from vrig.theme import T
from vrig.trace import StackTrace, h32

TRACE = "stack2-12"
TITLE = "Making a video by hand"


class ExampleByHand(VrigScene):
    def construct(self):
        self.tr = StackTrace.load(TRACE)
        self.pipeline()
        self.overflow()
        self.read_back()

    # what the person making the video actually does, as one picture
    def pipeline(self):
        title = prose(TITLE, 48).to_edge(UP, buff=0.4)
        self.play(Write(title))

        stages = [
            ("payload hex", "you write this"),
            ("vrig-trace.mjs", "runs VRIG's own engine"),
            (f"traces/{TRACE}.json", "every step, every byte"),
            ("scenes/your_file.py", "reads the trace"),
            ("videos/…/id.mp4", "manimgl -w --hd"),
        ]
        boxes = VGroup()
        for name, note in stages:
            label = mono(name, 18)
            box = SurroundingRectangle(label, buff=0.2, color=T.grid).set_fill(T.cell_fill, 0.6)
            # commands go in mono, the prose font ligatures -- into a dash
            sub = (mono if note.startswith("manimgl") else prose)(note, 16, T.text_dim)
            sub.next_to(box, DOWN, buff=0.15)
            boxes.add(VGroup(box, label, sub))
        boxes.arrange(RIGHT, buff=0.55).set_width(FRAME_WIDTH - 1.8).shift(UP * 0.3)
        arrows = VGroup(*[
            Arrow(a[0].get_right(), b[0].get_left(), buff=0.08, stroke_width=3, color=T.pointer)
            for a, b in zip(boxes, boxes[1:])
        ])

        self.say("Every number in the video comes from VRIG. You never type one in.")
        for i, stage in enumerate(boxes):
            anims = [FadeIn(stage, shift=RIGHT * 0.2)]
            if i:
                anims.append(GrowArrow(arrows[i - 1]))
            self.play(*anims, run_time=0.6)
        self.beat()

        self.say("The trace also says whether the payload wins. A scene that claims a win checks first.")
        won = mono(f"won() = {self.tr.won()}", 20, T.win).next_to(boxes[2], UP, buff=0.35)
        self.play(FadeIn(won, shift=DOWN * 0.15))
        assert self.tr.won(), "payload doesn't win in VRIG, re-export the trace"
        self.beat()

        self.play(FadeOut(VGroup(boxes, arrows, won)), title.animate.scale(0.6).to_corner(UL, buff=0.25))
        self.title = title

    def overflow(self):
        tr = self.tr
        src = [l for l in tr.source if not l.startswith("#include")]
        code = CodeListing(src, size=17).to_corner(UL, buff=0.5).shift(DOWN * 0.45)
        stack = StackView(tr, n_words=len(tr.payload) // tr.word).shift(RIGHT * 1.9 + UP * 0.1)
        tags = stack.frame_tags()

        self.say("Here is what the scene draws from that trace.")
        self.play(FadeIn(code, shift=RIGHT * 0.3), FadeIn(stack.words, lag_ratio=0.05))
        self.play(LaggedStartMap(FadeIn, tags, shift=LEFT * 0.2, lag_ratio=0.3))
        self.beat()

        gets_line = next(i for i, l in enumerate(src) if "gets(" in l)
        self.play(code.focus(gets_line))
        strip = PayloadStrip(tr.payload).next_to(code, DOWN, buff=0.45, aligned_edge=LEFT)
        strip_lab = mono("input", 16, T.text_dim).next_to(strip, UP, buff=0.12, aligned_edge=LEFT)
        self.say("The payload goes in one word at a time, in the order VRIG wrote it.")
        self.play(FadeIn(strip_lab), FadeIn(strip, lag_ratio=0.02, run_time=1.2))

        # one VRIG gets() step per word. hl[0] is the offset that step wrote
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
                self.say("Past buf and saved ebp, the input reaches the return address.")
                self.beat()
            if off >= tr.ret_off:
                break  # the template stops at ret. ROP Basics keeps going

        self.play(FadeOut(strip), FadeOut(strip_lab), FadeOut(tags))
        self.stack, self.code = stack, code

    def read_back(self):
        tr = self.tr
        word = self.stack.at(tr.ret_off)
        value, anims = le_assemble(word)
        self.say("Read the bytes back little-endian and you get where ret will jump.")
        self.play(*anims, run_time=0.8)

        target = tr.word_at(tr.ret_off)
        name = tr.gadgets.get(target) or next(
            (f"{n}()" for n, a in tr.symbols.items() if a == target), h32(target))
        lab = mono(name, 16, T.gadget).next_to(value, RIGHT, buff=0.25)
        self.play(FadeIn(lab, shift=LEFT * 0.15), word.boxes().animate.set_fill(T.gadget, 0.85))
        self.beat()

        self.say("Copy this file, point TRACE at your own trace, and rewrite the captions.")
        self.beat(pause=1.5)
        self.unsay()
