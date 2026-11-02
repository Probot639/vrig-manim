"""
Heap walkthroughs: every guided 'step' exercise whose viz is the heap. Each
scene replays a trace from tools/vrig-trace/walk_heap-entry.ts, one VRIG
Step click per beat.

    manimgl scenes/walk_heap.py Heap15 -w -l
    manimgl scenes/walk_heap.py Heap15 -p          # presenter mode

Base class does the walk. Subclasses give captions per step index, and
override hooks where an exercise needs its own picture.
"""
from manimlib import *

from vrig.mob.cpu import CodeListing
from vrig.mob.memory import LIFT, mono, prose
from vrig.mob.space import arc3d
from vrig.mob.walk_heap import (BinsPanel, ChunkBytes, HeapStrip, HeapTrace, Layout, Stage, bin_lists,
                                chunk_at, chunk_named, fit, le32)
from vrig.scene import Vrig3DScene
from vrig.theme import T
from vrig.trace import h32


def read_time(text: str) -> float:
    # about 3.5 words a second, which is a slow reading pace on purpose
    return max(1.4, len(text.split()) / 3.5)


class CodeWindow:
    """A CodeListing that only shows `rows` lines and scrolls to follow focus."""

    def __init__(self, scene, lines, corner=(-6.75, 3.25), rows: int = 11, size: int = 18, max_w: float = 6.6):
        self.scene, self.lines, self.rows, self.size = scene, lines, rows, size
        self.corner, self.max_w = np.array([*corner, 0]), max_w
        self.lo = 0
        self.view = self._build(0)

    def _build(self, lo):
        self.lo = lo
        sub = self.lines[lo:lo + self.rows]
        v = CodeListing(sub, size=self.size)
        if v.get_width() > self.max_w:
            v.set_width(self.max_w)
        v.move_to(self.corner, aligned_edge=UL)
        return v.fix_in_frame()

    def show(self):
        return FadeIn(self.view, shift=RIGHT * 0.2)

    hidden = False   # set while a scene has the listing faded out for a 3d beat

    def focus(self, line: int) -> list[Animation]:
        if line is None or line < 0 or line >= len(self.lines):
            return []
        if self.hidden:
            # keep following along off screen so it comes back on the right line
            lo = self.lo if self.lo <= line < self.lo + self.rows else \
                max(0, min(line - self.rows // 2, len(self.lines) - self.rows))
            self.view = self._build(lo)
            a = self.view.focus(line - self.lo)
            a.begin()
            a.finish()
            self.view.bar.fix_in_frame()
            return []
        if not (self.lo <= line < self.lo + self.rows):
            lo = max(0, min(line - self.rows // 2, len(self.lines) - self.rows))
            new = self._build(lo)
            old = self.view
            self.view = new
            self.scene.play(FadeOut(old), FadeIn(new), run_time=0.4)
        bar = self.view.focus(line - self.lo)
        self.view.bar.fix_in_frame()
        return [bar]

    def hide(self):
        return FadeOut(self.view)


class HeapWalk(Vrig3DScene):
    trace_id = ""
    subtitle = ""
    captions: dict = {}          # step index -> caption, said before that step's beat
    outro = ""                   # takeaway line said under the win card
    code_rows = 11
    code_size = 18
    layout_kw: dict = {}
    bins_kw: dict = {}
    arrows = True
    step_time = 0.9
    top_label = None

    # -- hooks, override per exercise --
    def name_fn(self, c, snap):
        return "/".join(c["names"]) or None

    def body_fn(self, c, snap):
        return None  # None means "use the default" (fd/bk when freed)

    def before_step(self, i, step):
        pass

    def cap_vars(self) -> dict:
        return {}

    def show_step(self, i, step):
        """visuals for this step, played before its caption"""
        pass

    def after_step(self, i, step):
        """runs after the caption and beat, for beats with their own captions"""
        pass

    def finale(self):
        pass

    # -- the walk --
    def construct(self):
        tr = HeapTrace.load(self.trace_id)
        assert tr.raw["solved"], f"{tr.id}: trace says the walkthrough didn't complete"
        self.tr = tr
        self.frame.reorient(0, 0)
        self.open_title()
        self.setup_heap()
        # a hook may swap self.seq mid-walk (whint-60 reruns on a bigger heap)
        self.seq = list(tr.steps)
        prev = tr.initial
        for i in range(len(self.seq)):
            step = self.seq[i]
            self.before_step(i, step)
            self.play_step(i, step, prev)
            self.after_step(i, step)
            prev = self.seq[i]
        self.finale()
        self.close_out()

    def open_title(self):
        title = prose(self.tr.title, 46).to_edge(UP, buff=0.5)
        sub = prose(self.subtitle, 26, T.text_dim).next_to(title, DOWN, buff=0.3)
        fit(sub, 12.5, 0.3)
        tag = mono(f"{self.tr.id}   {self.sim_tag()}", 16, T.text_dim).next_to(sub, DOWN, buff=0.35)
        self.fix(title, sub, tag)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2), FadeIn(tag))
        self.wait(read_time(self.subtitle))
        self.beat()
        small = prose(self.tr.title, 26).to_corner(UL, buff=0.25).fix_in_frame()
        self.play(FadeOut(sub), FadeOut(tag), FadeTransform(title, small))
        self.title = small

    def sim_tag(self):
        tr = self.tr
        if tr.win:
            return f"WinHeapSim {tr.raw['winVersion']}, {tr.heap_size} B heap"
        return f"HeapSim, glibc {tr.raw['glibcVersion']}, {tr.heap_size} B heap"

    def fix(self, *mobs):
        for m in mobs:
            m.fix_in_frame()

    def make_layout(self, snaps=None):
        kw = dict(self.layout_kw)
        return Layout(self.tr.span(snaps), **kw)

    def setup_heap(self):
        tr = self.tr
        self.lay = self.make_layout()
        self.strip = HeapStrip(tr, self.lay, name_fn=self.name_fn, body_fn=self._body, arrows=self.arrows,
                               top_label=self.top_label)
        self.bins = BinsPanel(tr, **self.bins_kw)
        self.code = CodeWindow(self, tr.source, rows=self.code_rows, size=self.code_size)
        self.heap_stage = Stage(self)
        self.bin_stage = Stage(self)
        floor = self.heap_floor()
        self.play(self.code.show(), FadeIn(floor))
        self.floor = floor
        anims = self.heap_stage.goto(self.strip.build(tr.initial)) + self.bin_stage.goto(self.bins.build(tr.initial))
        if anims:
            self.play(*anims)

    def heap_floor(self):
        # sim and glibc version, tucked under the title
        return mono(self.sim_tag(), 14, T.text_dim).next_to(self.title, RIGHT, buff=0.4).fix_in_frame()

    def _body(self, c, snap):
        b = self.body_fn(c, snap)
        if b is None:
            from vrig.mob.walk_heap import default_body
            return default_body(self.tr)(c, snap)
        return b or None

    def play_step(self, i, step, prev):
        anims = self.code.focus(step["srcLine"])
        anims += self.heap_stage.goto(self.strip.build(step))
        anims += self.bin_stage.goto(self.bins.build(step))
        if anims:
            self.play(*anims, run_time=self.step_time)
        self.show_step(i, step)
        cap = self.captions.get(i)
        if cap:
            # numbers in captions come from the trace, never typed in
            cap = cap.format(**self.cap_vars())
            self.say(cap)
            self.wait(read_time(cap))
            self.beat()
        else:
            self.beat(pause=0.35)

    def close_out(self):
        self.unsay()
        keep = [self.title]
        fade = [m for m in self.mobjects if m not in keep and m is not self.frame]
        win_t = prose(self.tr.raw["winTitle"], 40, T.win)
        msg = prose(self.wrap(self.tr.raw["winMsg"], 62), 24, T.text)
        card = VGroup(win_t, msg).arrange(DOWN, buff=0.4).move_to(UP * 0.4)
        self.fix(card)
        self.play(*[FadeOut(m) for m in fade], run_time=0.8)
        self.play(Write(win_t), FadeIn(msg, shift=UP * 0.2))
        self.wait(read_time(self.tr.raw["winMsg"]) * 0.8)
        if self.outro:
            self.say(self.outro)
            self.wait(read_time(self.outro))
        self.beat(pause=1.5)

    @staticmethod
    def wrap(s, width):
        import textwrap
        return "\n".join(textwrap.wrap(s, width))

    # -- shared extras --------------------------------------------------------
    def chunk_mob(self, name, step):
        c = chunk_named(step, name)
        return self.heap_stage.get(f"chunk:{c['addr']}")

    def callout(self, target, text, role="highlight", direction=UP, size=17, buff=0.35):
        """Label with a short leader line. target is a mobject or a point."""
        p = target.get_edge_center(direction) if isinstance(target, Mobject) else np.array(target)
        lab = mono(text, size, getattr(T, role))
        lab.move_to(p + direction * (buff + lab.get_height() / 2))
        # keep the label on screen, the leader line can slant to reach it
        over = lab.get_right()[0] - 6.8
        if over > 0:
            lab.shift(LEFT * over)
        under = -6.8 - lab.get_left()[0]
        if under > 0:
            lab.shift(RIGHT * under)
        line = Line(p, lab.get_edge_center(-direction), buff=0.05).set_stroke(getattr(T, role), 2)
        return VGroup(line, lab)

    def note(self, text, at, size=15, role="text_dim", **kw):
        return mono(text, size, getattr(T, role)).move_to(at, **kw)

    # chunk zoom: one chunk as byte cells in the band between code and strip
    zoom_y = 0.25

    def glibc_fields(self, c, snap, n):
        f = [("prev_size", 0, 4, "chunk_header"), ("size", 4, 8, "chunk_header")]
        if c["allocated"]:
            f.append(("user data", 8, n, "chunk_user"))
            return f
        from vrig.mob.walk_heap import bin_of
        b = bin_of(snap, c["addr"])
        kind = b.kind if b else "tcache"
        role = b.role if b else "tcache"
        f.append(("fd", 8, 12, role))
        if kind in ("unsorted", "smallbins", "largebins"):
            f.append(("bk", 12, 16, role))
        elif kind == "tcache" and self.tr.raw["glibcVersion"] >= "2.29":
            f.append(("key", 12, 16, role))
        return f

    def cell_roles(self, c, n):
        user = "chunk_user" if c["allocated"] else "freed_chunk"
        return {i: ("chunk_header" if i < self.tr.hdr else user) for i in range(n)}

    def set_zoom(self, snap, name, n=24, fields=None, roles=None, glyphs=None, values=None, mark=(),
                 width=11.0, x=-0.6, run_time=0.8, link=True):
        c = chunk_named(snap, name)
        n = min(n, c["size"])
        fields = fields if fields is not None else self.glibc_fields(c, snap, n)
        roles = roles or self.cell_roles(c, n)
        z = ChunkBytes(snap, c["addr"], n, fields, self.tr, roles, glyphs=glyphs, values=values, mark=mark)
        if z.get_width() > width:
            z.set_width(width)
        z.move_to([x, self.zoom_y, 0])
        old = getattr(self, "zb", None)
        self.zb = z
        anims = [FadeIn(z, shift=UP * 0.2)] if old is None else [FadeTransform(old, z)]
        if link:
            ch = self.heap_stage.get(f"chunk:{c['addr']}")
            ln = self.zoom_link(z, ch)
            oldl = getattr(self, "zlink", None)
            anims.append(FadeIn(ln) if oldl is None else FadeTransform(oldl, ln))
            self.zlink = ln
        self.play(*anims, run_time=run_time)
        return z

    def zoom_link(self, z, ch):
        lo = z.cells.get_corner(DL), z.cells.get_corner(DR)
        bot = min(z.brackets.get_bottom()[1], z.cells.get_bottom()[1]) - 0.05
        a = np.array([lo[0][0], bot, 0])
        b = np.array([lo[1][0], bot, 0])
        return VGroup(DashedLine(a, ch.get_corner(UL), dash_length=0.06),
                      DashedLine(b, ch.get_corner(UR), dash_length=0.06)).set_stroke(T.text_dim, 1)

    def drop_zoom(self):
        anims = []
        for k in ("zb", "zlink"):
            m = getattr(self, k, None)
            if m is not None:
                anims.append(FadeOut(m))
                setattr(self, k, None)
        return anims

    def lift_bins(self, step, hold=2.5, phi=62, theta=-18):
        """
        Stand the bins panel up over the heap and run a line from every node
        down to its chunk on the floor, then put everything back.
        """
        bins = self.bin_stage.group()
        if not len(bins):
            return
        frame = self.frame
        saved = [m.copy() for m in bins]
        lay = self.lay
        target_center = np.array([0, lay.y + 1.2, 2.6])
        # the panel sits off to the right, stand it up over the middle of the heap
        self.play(frame.animate.reorient(theta, phi, 0, center=(0, lay.y + 1.2, 1.1), height=8.8),
                  FadeOut(self.code.view),
                  bins.animate.rotate(90 * DEG, RIGHT).move_to(target_center), run_time=2.2)
        lines = VGroup()
        for b in bin_lists(step):
            for addr in b.nodes:
                keys = [kk for kk in self.bin_stage.mobs if kk.startswith(f"node:{b.key}:{addr}:")]
                ch = self.heap_stage.get(f"chunk:{addr}")
                for key in keys:
                    node = self.bin_stage.mobs[key]
                    lines.add(arc3d(node.get_corner(IN), ch.user.get_top(), lift=0.3,
                                    color=getattr(T, b.role), width=3))
        self.play(LaggedStartMap(ShowCreation, lines, lag_ratio=0.15), run_time=1.5)
        self.wait(hold)
        self.beat()
        self.play(FadeOut(lines))
        self.play(frame.animate.reorient(0, 0, 0, center=ORIGIN, height=8),
                  FadeIn(self.code.view),
                  *[Transform(m, s) for m, s in zip(bins, saved)], run_time=1.8)


def strcpy_values(text: str, at: int = 8) -> tuple[dict, dict]:
    vals = {at + i: ord(ch) for i, ch in enumerate(text)}
    vals[at + len(text)] = 0
    glyphs = {at + i: ch for i, ch in enumerate(text)}
    return vals, glyphs


# ---------------------------------------------------------------------------
# unit-intro-c

class C06(HeapWalk):
    trace_id = "c-06"
    subtitle = "Stack memory comes and goes with function calls. Heap memory lives until you free it."
    captions = {
        0: "The stack cleans up after every call on its own. The heap holds memory you ask for at runtime "
           "and hand back yourself.",
        1: "malloc(16) returns a pointer to 16 usable bytes. An 8-byte header sits just in front of them.",
        2: "strcpy copies the five letters of hello and a zero byte into the block. The other ten bytes stay "
           "allocated but unused.",
        3: "free(buf) hands the block back. It goes on tcache, and its first four bytes become the list link.",
        4: "buf still holds the old address. Reading or writing through it now is a use-after-free.",
        5: "Mistakes with heap lifetimes are where a lot of real exploits start.",
    }
    code_rows = 9

    def show_step(self, i, step):
        tr = self.tr
        text = tr.extra["strcpy"]["text"]
        vals, glyphs = strcpy_values(text)
        if i == 1:
            self.set_zoom(step, "buf")
        if i == 2:
            self.set_zoom(step, "buf", values=vals, glyphs=glyphs, mark=tuple(vals))
            # HeapSim never stores these, the step has no vizAction. Say so.
            self.foot = self.note("bytes from the strcpy line. VRIG's sim leaves them 00", self.zb.get_top() + UP * 0.3)
            self.play(FadeIn(self.foot))
        if i == 3:
            # the tcache link is four bytes on this 32-bit heap, the tail of
            # the string survives the free
            keep = {k: v for k, v in vals.items() if k >= 12}
            g = {k: v for k, v in glyphs.items() if k >= 12}
            self.set_zoom(step, "buf", values=keep, glyphs=g, mark=(8, 9, 10, 11))
            self.play(FadeOut(self.foot))
        if i == 4:
            c = chunk_named(step, "buf")
            ptr = tr.base + c["addr"] + tr.hdr
            box = VGroup(mono(f"buf = {h32(ptr)}", 18, T.crash))
            box.add(SurroundingRectangle(box[0], buff=0.12).set_stroke(T.crash, 2))
            box.move_to([2.6, 2.2, 0])
            arrow = Arrow(box.get_bottom(), self.zb.cells[8].get_top(), buff=0.1).set_color(T.crash)
            self.play(FadeIn(box), GrowArrow(arrow))
            self.dangle = VGroup(box, arrow)


# ---------------------------------------------------------------------------
# unit4-heap

class Heap15(HeapWalk):
    trace_id = "heap-15"
    subtitle = "malloc carves blocks off the top. free puts them on a list for reuse."
    captions = {
        0: "One empty region. All of it is the top chunk for now.",
        1: "malloc(16) takes 24 bytes from the top. Eight are header and 16 are yours.",
        2: "The second block lands right after the first.",
        3: "free(a) pushes A onto tcache. Its first four bytes now hold fd, which is null.",
        4: "free(b) goes on the front. B's fd points at A's data, so the list runs B, then A.",
        5: "malloc(16) checks tcache first and pops the head. c gets B's old memory back.",
    }
    outro = "Last in, first out. Freed memory comes straight back to the next request of the same size."

    def after_step(self, i, step):
        if i == 4:
            self.say("Stand the list up. Each node is a chunk sitting in the heap.")
            self.lift_bins(step)


# ---------------------------------------------------------------------------
# unit11-heap-internals

class Hint53(HeapWalk):
    trace_id = "hint-53"
    subtitle = "Every chunk carries an 8-byte header in front of the pointer malloc gives you."
    code_rows = 8
    captions = {
        0: "ptmalloc2 splits the heap into chunks. Each one starts with a small header.",
        1: "malloc(16) carves a 24-byte chunk. The pointer it returns is 8 bytes past the chunk start.",
        2: "The first word is prev_size. It only means something when the chunk before this one is free.",
        3: "The second word is size. Sizes are multiples of 8, so the low three bits are spare for flags.",
        4: "0x19 is 24 with the P bit set. Nothing in front of A is free.",
        5: "free(A) reuses the user area. Its first word is now fd, the tcache link.",
        6: "Corrupt these fields and the allocator believes whatever you wrote.",
    }

    def show_step(self, i, step):
        tr = self.tr
        if i == 1:
            self.set_zoom(step, "A")
            c = chunk_named(step, "A")
            p = self.callout(self.zb.cells[8], f"p = {h32(tr.base + c['addr'] + tr.hdr)}", "chunk_user", UP)
            self.play(FadeIn(p))
            self.ptr = p
        if i == 2:
            self.set_zoom(step, "A", mark=(0, 1, 2, 3))
        if i == 3:
            self.set_zoom(step, "A", mark=(4, 5, 6, 7))
        if i == 4:
            c = chunk_named(step, "A")
            self.play(FadeIn(self.flag_panel(c["sizeField"]), shift=LEFT * 0.2))
        if i == 5:
            self.set_zoom(step, "A", mark=(8, 9, 10, 11))

    def before_step(self, i, step):
        if i == 5:
            self.play(FadeOut(self.ptr), FadeOut(self.flags))

    def flag_panel(self, size):
        bits = VGroup()
        for name, bit in (("A", 2), ("M", 1), ("P", 0)):
            on = (size >> bit) & 1
            box = Square(0.5).set_fill(T.highlight if on else T.cell_fill, 0.85).set_stroke(T.grid, 1.5)
            v = mono(str(on), 20, T.background if on else T.text).move_to(box).shift(LIFT)
            lab = mono(name, 16, T.label).next_to(box, UP, buff=0.08)
            bits.add(VGroup(box, v, lab))
        bits.arrange(RIGHT, buff=0.1)
        head = mono(f"size field {size:#x} = {size:#010b}", 18, T.text)
        rest = mono(f"{size:#x} & ~7 = {size & ~7:#x} = {size & ~7} bytes", 18, T.chunk_header)
        g = VGroup(head, bits, rest).arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        g.move_to([3.4, 1.55, 0])
        self.flags = g
        return g


class Hint54(HeapWalk):
    trace_id = "hint-54"
    subtitle = "The same bytes hold your data while a chunk is in use and allocator pointers after free."
    code_rows = 8
    captions = {
        0: "Follow one chunk from malloc to free and watch what its bytes mean at each point.",
        1: "malloc(32) carves a 40-byte chunk. size reads 0x29, which is 40 with the P bit set.",
        2: "The program writes HELLO starting at p. The header just before p stays untouched.",
        3: "p minus 8 is prev_size and size. The program should never write there, but an overflow can.",
        4: "free(A) writes the tcache fd over the first four bytes. HELL is gone, and the O is still sitting there.",
        5: "p still points here. Reading it leaks heap pointers, and writing it rewrites the free list.",
        6: "Use-after-free and double free both live in this switch from data to metadata.",
    }

    def hello(self):
        w = next(w for s in self.tr.steps for w in s["wishes"] if w[0] == "writeData")
        bs = w[2]
        vals = {8 + k: b for k, b in enumerate(bs)}
        glyphs = {8 + k: chr(b) for k, b in enumerate(bs)}
        return vals, glyphs

    def show_step(self, i, step):
        tr = self.tr
        vals, glyphs = self.hello()
        if i == 1:
            self.set_zoom(step, "A")
            c = chunk_named(step, "A")
            self.ptr = self.callout(self.zb.cells[8], f"p = {h32(tr.base + c['addr'] + tr.hdr)}", "chunk_user", UP)
            more = self.note(f"... {c['size'] - 24} more bytes", self.zb.cells.get_right() + RIGHT * 0.9)
            self.more = more
            self.play(FadeIn(self.ptr), FadeIn(more))
        if i == 2:
            self.set_zoom(step, "A", values=vals, glyphs=glyphs, mark=tuple(vals))
            self.foot = self.note("bytes from the exercise's writeData call. HeapSim has no writeData, so its copy stays 00",
                                  [0, self.zoom_y - 1.05, 0], size=13)
            self.play(FadeIn(self.foot))
        if i == 3:
            self.set_zoom(step, "A", values=vals, glyphs=glyphs, mark=tuple(range(8)))
        if i == 4:
            keep = {k: v for k, v in vals.items() if k >= 12}
            g = {k: v for k, v in glyphs.items() if k >= 12}
            self.play(FadeOut(self.foot))
            self.set_zoom(step, "A", values=keep, glyphs=g, mark=(8, 9, 10, 11))
            self.keep = (keep, g)
        if i == 5:
            new = self.callout(self.zb.cells[8], self.ptr[1].text, "crash", UP)
            self.play(FadeTransform(self.ptr, new))
            self.ptr = new


class Hint55(HeapWalk):
    trace_id = "hint-55"
    subtitle = "Chunk size decides which free list a chunk lands on."
    captions = {
        0: "Freed chunks go into bins by size. This run uses glibc 2.23, which has no tcache.",
        1: "malloc(24) makes a 32-byte chunk. That's fastbin size.",
        2: "malloc(256) makes a 264-byte chunk, too big for any fastbin.",
        3: "A small guard chunk keeps M from merging into top when it's freed.",
        4: "free(S) pushes S onto fastbin[32]. Fastbins are singly linked and never merge with neighbours.",
        6: "free(M) goes to the unsorted bin. Its bk points at main_arena, and the guard's P bit drops to 0.",
        7: "Small bins hold one exact size each, and large bins hold ranges. The next malloc sorts unsorted chunks into them.",
    }

    def after_step(self, i, step):
        if i == 6:
            self.say("Two lists, two chunks. Fastbin is one-way. Unsorted links both ways.")
            self.lift_bins(step)


class Hint56(HeapWalk):
    trace_id = "hint-56"
    subtitle = "Fill one tcache bin and watch where the eighth free goes."
    code_rows = 7
    code_size = 16
    step_time = 0.6
    bins_kw = dict(origin=[-6.5, 0.75, 0], max_nodes=7)
    captions = {
        0: "tcache keeps one list per chunk size. Each list holds at most 7 chunks.",
        1: "malloc(24) is a 32-byte chunk. Nine of them, all the same size.",
        9: "Nine identical chunks. Now free them in order.",
        10: "free(P0). Count 1 of 7. P0's fd is null, the end of the list.",
        11: "free(P1) goes on the front. P1's fd points at P0.",
        16: "free(P6). The bin is full at 7.",
        17: "free(P7) can't go in tcache, so it falls through to fastbin[32].",
        18: "P8 follows it. Fastbin[32] is now P8, then P7.",
        19: "Filling tcache first is how classic fastbin attacks get their chunks onto the old path.",
    }

    def show_step(self, i, step):
        # before the caption, or the count reads one free behind
        n = len(step["freeLists"]["tcache"].get("32", []))
        head = self.bin_stage.get("head:tcache:32")
        if head is None:
            return
        cnt = mono(f"{n}/7", 17, T.tcache).next_to(head, DOWN, buff=0.08, aligned_edge=LEFT)
        old = getattr(self, "cnt", None)
        self.play(FadeIn(cnt) if old is None else FadeTransform(old, cnt), run_time=0.3)
        self.cnt = cnt



class Hint57(HeapWalk):
    trace_id = "hint-57"
    subtitle = "One process, several allocators. The A bit in each chunk says which one owns it."
    captions = {
        0: "Each arena is a separate allocator with its own bins and its own top chunk.",
        1: "The main thread's malloc(32) comes from the main arena. Bit 2 of size, the A bit, is 0.",
        2: "Other threads get arenas of their own, so they don't all fight over one lock.",
        3: "Thread arenas live in mmap'd heaps. Their chunks set the A bit, which would make this size 0x2d.",
        4: "free(M) reads the A bit to find the owner. A is 0, so M goes back to the main arena side.",
        5: "A poisoned list in one arena can't reach chunks that belong to another.",
    }

    def show_step(self, i, step):
        if i == 1:
            c = chunk_named(step, "M")
            ch = self.chunk_mob("M", step)
            self.abit = self.callout(ch.header, f"size {c['sizeField']:#x}  A={(c['sizeField'] >> 2) & 1}",
                                     "chunk_header", UP, buff=0.5)
            self.play(FadeIn(self.abit))
        if i == 2:
            self.arenas(step)
        if i == 3:
            c = chunk_named(step, "M")
            g = mono(f"a chunk here would read size {c['sizeField'] | 4:#x}  A=1", 26, T.unsorted)
            g.move_to(self.thread_plane.get_center() + DOWN * 0.45).shift(OUT * 0.01)
            self.play(Write(g))
            self.ghost = g

    def before_step(self, i, step):
        if i == 4:
            # back to the flat view before the free, so the bin update shows
            self.play(FadeOut(self.ghost), FadeOut(self.thread), FadeOut(self.main_lab),
                      self.frame.animate.reorient(0, 0, 0, center=ORIGIN, height=8), run_time=1.8)
            self.code.hidden = False
            self.play(FadeIn(self.code.view), *[FadeIn(m) for m in self.bin_stage.group()])

    def arenas(self, step):
        lay = self.lay
        # main arena is the strip already on the floor. The thread arena is a
        # second floor above it. Nothing in VRIG allocates there, so it's
        # drawn without numbers.
        main = mono("main arena, grows with brk()", 26, T.text_dim)
        main.move_to([lay.right, lay.y + lay.h / 2 + 0.35, 0], aligned_edge=RIGHT)
        plane = Rectangle(13.0, 2.4).set_fill(T.cell_fill, 0.7).set_stroke(T.unsorted, 2)
        plane.move_to([0, lay.y, 2.3])
        info = Rectangle(2.4, 1.0).set_fill(T.chunk_header, 0.85).set_stroke(T.background, 1)
        info.move_to(plane.get_corner(UL) + RIGHT * 1.4 + DOWN * 0.7).shift(OUT * 0.01)
        info_t = mono("heap_info", 24, T.background).move_to(info).shift(OUT * 0.02)
        ar = mono("thread arena, mmap()'d heap", 26, T.unsorted)
        ar.next_to(info, RIGHT, buff=0.4).shift(OUT * 0.01)
        tp = Rectangle(3.0, 1.0).set_fill(T.top_chunk, 0.6).set_stroke(T.top_chunk, 1.5)
        tp.move_to(plane.get_corner(UR) + LEFT * 1.7 + DOWN * 0.7).shift(OUT * 0.01)
        tp_t = mono("its own top", 22, T.text).move_to(tp).shift(OUT * 0.02)
        self.thread = Group(plane, info, info_t, ar, tp, tp_t)
        self.thread_plane = plane
        self.code.hidden = True
        self.play(self.frame.animate.reorient(0, 50, 0, center=(0, lay.y + 0.3, 1.5), height=9.6),
                  FadeIn(main), FadeOut(self.code.view), *[FadeOut(m) for m in self.bin_stage.group()],
                  run_time=2)
        self.play(FadeIn(self.thread, shift=OUT * 0.6))
        self.main_lab = main


class Hint58(HeapWalk):
    trace_id = "hint-58"
    subtitle = "Free neighbours merge into one chunk, and unlink stitches the list back together."
    captions = {
        0: "When two neighbouring chunks are both free, glibc merges them into one.",
        1: "Three 136-byte chunks, A, B, and C. Each size field reads 0x89.",
        4: "A guard chunk keeps C away from top.",
        5: "free(B) goes to unsorted. C's P bit drops to 0 and its prev_size becomes 0x88.",
        6: "free(A) sees that B is free and merges forward. One 272-byte chunk, size 0x111.",
        7: "Unlink took B off its list by rewriting its neighbours' pointers. Before glibc checked them, "
           "a forged fd and bk meant a write anywhere.",
        8: "Modern glibc checks fd and bk, but faking size and prev_size still fools the merge.",
    }

    def show_step(self, i, step):
        if i == 5:
            c = chunk_named(step, "C")
            ch = self.chunk_mob("C", step)
            self.cp = self.callout(ch.header, f"prev_size {c['prevSizeField']:#x}  size {c['sizeField']:#x}",
                                   "chunk_header", UP, buff=0.6)
            self.play(FadeIn(self.cp))
        if i == 6:
            c = chunk_named(step, "C")
            ch = self.chunk_mob("C", step)
            new = self.callout(ch.header, f"prev_size {c['prevSizeField']:#x}  size {c['sizeField']:#x}",
                               "chunk_header", UP, buff=0.6)
            self.play(FadeTransform(self.cp, new))
            self.cp = new
        if i == 7:
            lines = ["FD = B->fd;", "BK = B->bk;", "FD->bk = BK;", "BK->fd = FD;"]
            code = VGroup(*(mono(l, 20, T.unsorted) for l in lines)).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
            code.move_to([3.6, 1.6, 0])
            self.play(LaggedStartMap(FadeIn, code, shift=LEFT * 0.2, lag_ratio=0.3))


# ---------------------------------------------------------------------------
# unit12-win-heap-internals

class WinWalk(HeapWalk):
    top_label = "uncommitted"   # what VRIG's HeapViz calls it for Windows

    def setup_heap(self):
        super().setup_heap()
        key = self.tr.raw["encodingKey"]
        k = mono(f"encoding key {key:#010x}, random in VRIG, seeded here", 13, T.text_dim)
        k.to_corner(UR, buff=0.3).fix_in_frame()
        self.play(FadeIn(k))


class Whint59(WinWalk):
    trace_id = "whint-59"
    subtitle = "The back end splits a segment into blocks and keeps free ones on size-indexed lists."
    captions = {
        0: "Every Windows process gets a default heap from GetProcessHeap. HeapAlloc goes through ntdll.",
        1: "HeapAlloc(16) gives a 24-byte block. Its _HEAP_ENTRY says Size 3, counted in 8-byte units.",
        2: "HeapAlloc(64) gives 72 bytes, Size 9.",
        3: "In memory each header is XORed with a per-heap key. The labels here show decoded values.",
        4: "HeapFree(A) links A into ListHints[3] through Flink and Blink.",
        5: "HeapFree(B) finds A free right behind it and merges. One 96-byte block, now on ListHints[12].",
        6: "The LFH front end only takes over a size after many allocations of it.",
    }


class Whint60(WinWalk):
    trace_id = "whint-60"
    subtitle = "The Low Fragmentation Heap takes over a size class after enough allocations of it."
    step_time = 0.7
    captions = {
        0: "The LFH is the NT heap's front end. It stays off for a size until that size gets busy.",
        1: "Allocation 1 of 32 bytes. That's a Size 5 block, served by the back end.",
        4: "Thirteen more. Each one bumps the counter for Size 5.",
        5: "Allocation 17. One short of the threshold.",
        7: "UserBlocks is one region cut into equal slots. A bitmap tracks which ones are busy.",
        8: "Since Windows 8 the scan starts at a random slot, so neighbours are hard to predict.",
        9: "A big enough spray still lands next to the target often enough to work.",
    }

    def setup_heap(self):
        self._big = self.tr.extra["bigHeap"]["steps"]
        super().setup_heap()

    def make_layout(self, snaps=None):
        # whole heap to scale, top included, so you can see how little is left
        return self.full_layout(self.tr.steps)

    @staticmethod
    def full_layout(steps):
        end = steps[-1]["top"]
        return Layout(end["addr"], top_cap=end["size"])

    def name_fn(self, c, snap):
        n = "/".join(c["names"])
        return n[1:] if n else None

    def count(self, step):
        n = step["activationCounts"].get("5", 0)
        t = mono(f"allocs of Size 5: {n}", 20, T.tcache).move_to([3.4, 2.3, 0])
        old = getattr(self, "cnt", None)
        self.play(FadeIn(t) if old is None else FadeTransform(old, t), run_time=0.3)
        self.cnt = t

    def show_step(self, i, step):
        self.count(step)

    def after_step(self, i, step):
        if i == 6:
            a18 = chunk_named(step, "A18")
            prev = self.seq[5]
            need = 32 * a18["size"]
            top = self.heap_stage.get("top")
            left = self.callout(top, f"{prev['top']['size']} B free before A18, UserBlocks wants {need:,}", "tcache", UP, size=18)
            self.play(FadeIn(left))
            self.left = left
            self.say(f"Allocation 18 should switch Size 5 to the LFH. UserBlocks needs {need:,} bytes and this "
                     f"{self.tr.heap_size}-byte heap has {prev['top']['size']} left, so VRIG serves A18 from the back end.")
            self.wait(5.5)
            self.beat()
            self.switch_heap()

    def switch_heap(self):
        big = self._big
        self.seq = [self.seq[k] if k < 6 else big[k] for k in range(len(self.seq))]
        step = big[6]
        a18 = chunk_named(step, "A18")
        start = big[5]["top"]["addr"]
        slot = (a18["addr"] - start) // a18["size"]
        self.play(FadeOut(self.left))
        self.lay = self.strip.lay = self.full_layout(big)
        anims = self.heap_stage.goto(self.strip.build(step))
        self.play(*anims, run_time=1.5)
        lay = self.lay
        x0, x1 = lay.x(start), lay.x(start + 32 * a18["size"])
        y = lay.y + lay.h / 2 + 0.15
        brace = Line([x0, y, 0], [x1, y, 0]).set_stroke(T.tcache, 4)
        ticks = VGroup(*(Line([lay.x(start + k * a18["size"]), lay.y - lay.h / 2, 0],
                              [lay.x(start + k * a18["size"]), lay.y + lay.h / 2, 0]).set_stroke(T.tcache, 1, 0.5)
                         for k in range(33)))
        lab = mono(f"UserBlocks  32 slots of {a18['size']} B", 18, T.tcache).next_to(brace, UP, buff=0.12)
        self.ub = VGroup(brace, ticks, lab)
        self.play(ShowCreation(brace), FadeIn(ticks), FadeIn(lab))
        self.say(f"Same steps on a {self.tr.extra['bigHeap']['heapSize']}-byte heap. UserBlocks fits, and A18 "
                 f"lands in slot {slot} of 32.")
        self.wait(4)
        self.beat()


class Whint61(WinWalk):
    trace_id = "whint-61"
    subtitle = "Size picks the backend. Each backend keeps its own metadata."
    layout_kw = dict(top_cap=200)
    captions = {
        0: "Windows 10 added the Segment Heap. It sends each request to a backend picked by size.",
        1: "32 bytes. In the real Segment Heap this goes to the LFH tier.",
        2: "512 bytes goes to the VS backend, variable-size blocks inside committed pages.",
        3: "1,024 bytes is still VS. Only requests past 128 KB go straight to VirtualAlloc.",
        4: "Segment Heap headers are encoded too, and guard pages sit between segments.",
        5: "VRIG's sim carves all three from one region. The tags show the backend Windows would pick.",
    }
    tiers = {"S": ("LFH", "tcache"), "M": ("VS", "unsorted"), "L": ("VS", "unsorted")}

    def show_step(self, i, step):
        if step["action"] == "malloc":
            ch = self.chunk_mob(step["name"], step)
            name, role = self.tiers[step["name"]]
            self.play(FadeIn(self.callout(ch.user, name, role, UP, size=20, buff=0.3)))
        if i == 4:
            ladder = VGroup(*(mono(t, 18, getattr(T, r)) for t, r in (
                ("LFH            small sizes", "tcache"),
                ("VS             up to 128 KB", "unsorted"),
                ("VirtualAlloc   past that", "top_chunk"))))
            ladder.arrange(DOWN, buff=0.15, aligned_edge=LEFT).move_to([3.3, 1.9, 0])
            self.play(LaggedStartMap(FadeIn, ladder, shift=LEFT * 0.2, lag_ratio=0.3))


class Whint62(WinWalk):
    trace_id = "whint-62"
    subtitle = "Heap headers are stored XORed with a secret, so blind overwrites get caught."
    code_rows = 9
    code_size = 16
    captions = {
        0: "Since Vista, each _HEAP_ENTRY is XORed with a random key kept in the _HEAP.",
        1: "The raw header for A has Size 3, the BUSY flag, and a checksum byte. XOR it with the key to get what's stored.",
        2: "Stored, the header looks random. The key lives once in _HEAP, nowhere near the chunk.",
        3: "On free the heap XORs again and recomputes the checksum.",
        4: "The checksum matches, so HeapFree accepts A and links it into ListHints[3].",
        5: "To get past this, leak the key or go after user data such as function pointers.",
    }

    def rows(self, step):
        """raw header, key mask, stored bytes. raw ^ mask has to equal stored."""
        tr = self.tr
        c = chunk_named(step, "A")
        d = c["decoded"]
        raw = [d["sizeUnits"] & 0xff, d["sizeUnits"] >> 8, d["flags"], d["smallTagIndex"],
               d["prevSizeUnits"] & 0xff, d["prevSizeUnits"] >> 8, d["segmentOffset"], d["unusedBytes"]]
        key = tr.raw["encodingKey"]
        k0, k1 = key & 0xff, (key >> 8) & 0xff
        mask = [k0, k1, k0, k0, k0, k1, k0, k0]
        stored = c["bytes"][:8]
        assert [r ^ m for r, m in zip(raw, mask)] == stored, "decoded header doesn't XOR back to memory"
        return raw, mask, stored, d

    def row(self, label, bs, role, label_role="label"):
        from vrig.mob.memory import ByteCell
        cells = VGroup(*(ByteCell(b, role) for b in bs)).arrange(RIGHT, buff=0.04)
        lab = mono(label, 17, getattr(T, label_role)).next_to(cells, LEFT, buff=0.3)
        return VGroup(lab, cells)

    def show_step(self, i, step):
        if i == 1:
            raw, mask, stored, d = self.rows(step)
            fields = mono("Size    Flg Tag Prev    Seg Unu", 15, T.text_dim)
            r1 = self.row("raw", raw, "chunk_header")
            r2 = self.row("xor key", mask, "mitigation")
            r3 = self.row("stored", stored, "cell_fill")
            g = VGroup(r1, r2, r3).arrange(DOWN, buff=0.14, aligned_edge=RIGHT)
            fields.next_to(r1[1], UP, buff=0.1, aligned_edge=LEFT)
            g.add(fields)
            g.move_to([2.8, 1.3, 0])
            self.enc = g
            self.play(FadeIn(r1), FadeIn(fields))
            self.play(FadeIn(r2, shift=DOWN * 0.1))
            self.play(TransformFromCopy(VGroup(r1[1], r2[1]), r3[1]), FadeIn(r3[0]))
        if i == 4:
            # HeapFree rewrote the header with Flags 0, so raw and stored both
            # change and the old checksum line no longer matches what's shown
            self.play(FadeOut(self.check), run_time=0.4)
            raw, mask, stored, d = self.rows(step)
            for k, bs, role in ((0, raw, "chunk_header"), (2, stored, "cell_fill")):
                new = self.row(self.enc[k][0].text, bs, role).move_to(self.enc[k])
                self.play(FadeTransform(self.enc[k], new), run_time=0.6)
                self.enc.submobjects[k] = new
        if i == 3:
            raw, mask, stored, d = self.rows(step)
            s = d["sizeUnits"]
            tag = (s & 0xff) ^ (s >> 8) ^ d["flags"]
            ok = "ok" if tag == d["smallTagIndex"] else "BAD"
            t = mono(f"Tag = {s & 0xff:02x} ^ {s >> 8:02x} ^ {d['flags']:02x} = {tag:02x}   stored {d['smallTagIndex']:02x}  {ok}",
                     18, T.win if ok == "ok" else T.crash)
            t.next_to(self.enc, DOWN, buff=0.3, aligned_edge=RIGHT)
            self.check = t
            self.play(Write(t))

    def after_step(self, i, step):
        if i == 4:
            self.corrupt()

    def corrupt(self):
        x = self.tr.extra["corrupt"]
        d = x["decodedNaive"]
        r = self.row("overflow", x["naive"], "attacker_bytes")
        r.next_to(self.enc, DOWN, buff=0.14, aligned_edge=RIGHT)
        size = x["naive"][0] | x["naive"][1] << 8
        self.say(f"Now an overflow writes a plain header without the key, Size {size:#x} and BUSY.")
        self.wait(2.5)
        self.play(FadeIn(r, shift=DOWN * 0.1))
        s = d["sizeUnits"]
        tag = (s & 0xff) ^ (s >> 8) ^ d["flags"]
        verdict = "passes" if x["validAfter"] else "fails"
        t = mono(f"decoded Size {s}   Tag {tag:02x} vs {d['smallTagIndex']:02x}   {verdict}", 18,
                 T.crash if not x["validAfter"] else T.win)
        t.next_to(r, DOWN, buff=0.25, aligned_edge=RIGHT)
        fail = mono("RtlReportHeapFailure()", 22, T.crash).next_to(t, DOWN, buff=0.2, aligned_edge=RIGHT)
        self.play(Write(t))
        self.play(FadeIn(fail, scale=1.2))
        self.say(f"It decodes to Size {s} and the checksum {verdict}. The heap reports corruption and kills the process.")
        self.wait(3.5)
        self.beat()
        self.play(FadeOut(VGroup(t, fail, r)))


# ---------------------------------------------------------------------------
# unit16-advanced

class Adv87(HeapWalk):
    trace_id = "adv-87"
    subtitle = "Virtual calls go through a pointer stored inside the object."
    code_rows = 9
    code_size = 16
    zoom_y = -0.25
    captions = {
        0: "A class with virtual methods gets a hidden pointer in every object, the vptr.",
        1: "new Animal() asks for 8 bytes. HeapSim rounds that up to a 16-byte chunk.",
        2: "The constructor stores the vtable's address at offset 0. Every Animal shares one table in .rodata.",
        3: "a->health = 100 lands at offset 4, right after the vptr.",
        4: "a->speak() loads the vptr, reads slot 0, and calls through it.",
        5: "Overwrite the vptr and the same call goes through a table the attacker built.",
        6: "One overwritten pointer decides where every virtual call on this object goes.",
    }

    def fields(self):
        return [("prev_size", 0, 4, "chunk_header"), ("size", 4, 8, "chunk_header"),
                ("vptr", 8, 12, "pointer"), ("health", 12, 16, "chunk_user")]

    def health(self):
        import re
        line = next(l for l in self.tr.source if "health =" in l and "->" in l)
        v = int(re.search(r"=\s*(\d+)", line)[1])
        return {12 + k: b for k, b in enumerate(v.to_bytes(4, "little"))}

    def show_step(self, i, step):
        q = {8 + k: "??" for k in range(4)}
        if i == 1:
            self.set_zoom(step, "Animal", fields=self.fields(), x=-2.6, width=7.5)
        if i == 2:
            self.set_zoom(step, "Animal", fields=self.fields(), glyphs=q, values={8 + k: 0 for k in range(4)},
                          mark=(8, 9, 10, 11), x=-2.6, width=7.5)
            self.vtable()
            a = Arrow(self.zb.cells[11].get_right(), self.vt.get_left(), buff=0.12, path_arc=-30 * DEG)
            a.set_color(T.pointer)
            self.vptr_arrow = a
            self.play(GrowArrow(a))
        if i == 3:
            h = self.health()
            vals = {**h, **{8 + k: 0 for k in range(4)}}
            self.set_zoom(step, "Animal", fields=self.fields(), glyphs=q, values=vals, mark=tuple(h), x=-2.6, width=7.5)
            f = self.note("health bytes from the source line, the sim stores none of these", self.zb.get_bottom() + DOWN * 0.3, 13)
            self.play(FadeIn(f))
            self.foot = f
        if i == 4:
            slot = self.slots[0]
            fn = VGroup(mono("Animal::speak()", 18, T.text_section))
            fn.add(SurroundingRectangle(fn[0], buff=0.12).set_stroke(T.text_section, 2))
            fn.next_to(self.vt, DOWN, buff=0.8)
            a = Arrow(slot.get_right(), fn.get_right(), buff=0.08, path_arc=-90 * DEG).set_color(T.highlight)
            self.play(Indicate(self.zb.cells[8:12], color=T.highlight), run_time=0.6)
            self.play(Indicate(slot, color=T.highlight), GrowArrow(a))
            self.play(FadeIn(fn))
            self.call = VGroup(fn, a)
        if i == 5:
            fake = VGroup(mono("fake vtable", 18, T.attacker_bytes), mono("[0] attacker code", 16, T.attacker_bytes))
            fake.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
            fake.add(SurroundingRectangle(fake, buff=0.15).set_stroke(T.attacker_bytes, 2))
            fake.move_to([4.4, -0.35, 0])
            a = Arrow(self.zb.cells[11].get_right(), fake.get_left(), buff=0.12).set_color(T.attacker_bytes)
            self.play(FadeOut(self.call), self.vt[0].animate.set_stroke(opacity=0.3), self.vt[1].animate.set_opacity(0.3),
                      FadeTransform(self.vptr_arrow, a), FadeIn(fake, shift=LEFT * 0.2),
                      *[c.box.animate.set_fill(T.attacker_bytes, 0.85) for c in self.zb.cells[8:12]])

    def vtable(self):
        head = mono("Animal_vtable   .rodata", 18, T.text_section)
        s0 = mono("[0] &Animal::speak", 17, T.text)
        s1 = mono("[1] &Animal::eat", 17, T.text)
        g = VGroup(head, s0, s1).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        box = SurroundingRectangle(g, buff=0.18).set_stroke(T.text_section, 2)
        self.vt = VGroup(box, g).move_to([3.9, 1.0, 0])
        self.slots = [s0, s1]
        self.play(FadeIn(self.vt, shift=LEFT * 0.2))


# ---------------------------------------------------------------------------
# unit17-advanced-ii

class Adv2_96(HeapWalk):
    trace_id = "adv2-96"
    subtitle = "Shape the pool so the vulnerable buffer lands right next to a victim object."
    code_rows = 10
    code_size = 16
    captions = {
        0: "The kernel pool is the kernel's heap. Every allocation starts with an 8-byte POOL_HEADER.",
        1: "Spray Event objects. Same size, packed side by side.",
        3: "After enough of them the layout is predictable.",
        4: "Free every other one. Each hole is exactly one Event wide.",
        5: "The driver's buffer takes the hole, right between Event_0 and Event_2.",
        6: "The driver copies too much. The overflow runs into Event_2's headers and rewrites its TypeIndex.",
        7: "Now the kernel looks up Event_2's type in a table the attacker controls.",
    }

    def name_fn(self, c, snap):
        return c["names"][-1] if c["names"] else None

    def show_step(self, i, step):
        if i == 6:
            v = self.chunk_mob("vuln_buf", step)
            e2 = self.chunk_mob("Event_2", step)
            lay = self.lay
            # the sim doesn't run the copy, this is the picture of it
            spill = Rectangle(e2.header.get_right()[0] + lay.w(8) - v.user.get_left()[0], lay.h * 0.35)
            spill.set_fill(T.attacker_bytes, 0.9).set_stroke(width=0)
            spill.move_to(v.user.get_left(), aligned_edge=LEFT).align_to(v.user, DOWN).shift(UP * 0.04 + LIFT)
            self.play(GrowFromEdge(spill, LEFT), run_time=1.4)
            self.play(e2.header.animate.set_fill(T.crash, 0.95))
            t = self.callout(e2.header, "TypeIndex", "crash", UP, buff=0.5)
            self.play(FadeIn(t))


# ---------------------------------------------------------------------------
# unit18-kernel

class Kern107(HeapWalk):
    trace_id = "kern-107"
    subtitle = "Turn a use-after-free into a kernel write, then let the kernel run your script."
    code_rows = 9
    code_size = 16
    layout_kw = dict(top_cap=60)
    # the exercise's own variable names for the four chunks its vizActions make
    stages = ["note", "note2", "spray", "target"]
    captions = {
        0: "modprobe_path is a kernel string. Run a file with unknown magic and the kernel runs that path as root.",
        1: "A note struct holds a size and a data pointer. Editing the note writes wherever data points.",
        2: "Free the note, keep the pointer, and reallocate over it. The new data pointer aims at modprobe_path.",
        3: "Writing the note now writes /tmp/x into modprobe_path.",
        4: "Run a file that starts with ff ff ff ff. No handler matches, so the kernel runs /tmp/x as root.",
        5: "No kernel code pointer changed, which is why SMEP and SMAP never fire.",
    }

    def name_fn(self, c, snap):
        return self.stages[[x["addr"] for x in snap["chunks"]].index(c["addr"])]

    def body_fn(self, c, snap):
        bs = c["bytes"]
        if self.name_fn(c, snap) == "target":
            return '"' + bytes(b for b in bs[8:16] if b).decode() + '"'
        return f"size {le32(bs, 8)}\ndata {le32(bs, 12):#010x}"

    def show_step(self, i, step):
        if i == 0:
            mp = self.tr.extra["slab"]["modprobePath"]
            box = VGroup(mono("modprobe_path", 18, T.kernel_space), mono(f'"{mp}"', 20, T.text))
            box.arrange(DOWN, buff=0.12)
            box.add(SurroundingRectangle(box, buff=0.15).set_stroke(T.kernel_space, 2))
            box.move_to([4.6, 0.3, 0])
            self.mp = box
            self.play(FadeIn(box))
        if i == 2:
            c = chunk_at(step, step["chunks"][2]["addr"])
            ptr = le32(c["bytes"], 12)
            ch = self.heap_stage.get(f"chunk:{c['addr']}")
            lab = mono(f"{ptr:#010x}", 15, T.kernel_space).next_to(self.mp, DOWN, buff=0.1)
            a = Arrow(ch.user.get_top(), self.mp.get_bottom() + DOWN * 0.35, buff=0.1).set_color(T.attacker_bytes)
            self.play(GrowArrow(a), FadeIn(lab))
            self.aim = VGroup(a, lab)
        if i == 3:
            c = step["chunks"][3]
            s = bytes(b for b in c["bytes"][8:16] if b).decode()
            new = mono(f'"{s}"', 20, T.attacker_bytes).move_to(self.mp[1])
            self.play(FadeTransform(self.mp[1], new), self.mp[2].animate.set_stroke(T.attacker_bytes))
        if i == 4:
            r = VGroup(mono("/tmp/bad  ff ff ff ff", 18, T.text), mono("kernel runs /tmp/x as uid 0", 20, T.win))
            r.arrange(DOWN, buff=0.15).next_to(self.mp, UP, buff=0.4)
            self.play(FadeOut(self.slabg), FadeIn(r[0]))
            self.play(Write(r[1]))

    def after_step(self, i, step):
        if i == 2:
            self.slab()

    def slab(self):
        x = self.tr.extra["slab"]
        cls = x["note"]["slabClass"]
        rows = VGroup(
            mono(f"KernelSim kmalloc-{cls}", 17, T.kernel_space),
            mono(f"kmalloc(16) -> {x['note']['addr']:#010x}  note", 16, T.text),
            mono(f"kfree(note)  freed={str(x['freed']).lower()}", 16, T.text_dim),
            mono(f"kmalloc(16) -> {x['spray']['addr']:#010x}  spray", 16, T.attacker_bytes),
        ).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        rows.move_to([1.6, 2.2, 0])
        self.slabg = rows
        self.play(LaggedStartMap(FadeIn, rows, lag_ratio=0.4), run_time=1.6)
        self.say("VRIG draws each stage as a fresh chunk. In KernelSim's slab cache the freed note comes "
                 "straight back to the next kmalloc of that size.")
        self.wait(4.5)
        self.beat()


# ---------------------------------------------------------------------------
# unit19-glibc-bypass

class Glibc108(HeapWalk):
    trace_id = "glibc-108"
    subtitle = "The tcache key catches a double free, unless you can wipe it first."
    code_rows = 9
    code_size = 16
    captions = {
        0: "In glibc 2.31 a chunk freed into tcache carries a key. Free it again and glibc aborts.",
        1: "Two 16-byte requests, two 24-byte chunks.",
        2: "free(a) puts A on tcache and writes the key, {key}, at data+4.",
        3: "free(a) again. The key matches, so the second free gets refused.",
        4: "A use-after-free write sets the key back to 0.",
        5: "Now free(a) passes. A is on tcache twice and its fd points at itself.",
    }

    def cap_vars(self):
        return {"key": h32(self.tr.raw["tcacheKeyAddr"])}

    def show_step(self, i, step):
        tr = self.tr
        if i == 1:
            self.set_zoom(step, "A")
        if i == 2:
            self.set_zoom(step, "A", mark=(12, 13, 14, 15))
        if i == 3:
            p = tr.extra["doubleFreeProbe"]
            assert p["returned"] is False and p["memoryUnchanged"]
            err = mono(p["lastError"], 22, T.crash).move_to([2.6, 2.2, 0])
            self.play(Indicate(self.zb.cells[12:16], color=T.crash), FadeIn(err, scale=1.2))
            self.err = err
        if i == 4:
            self.play(FadeOut(self.err))
            self.set_zoom(step, "A", mark=(12, 13, 14, 15))
        if i == 5:
            self.set_zoom(step, "A", mark=(8, 9, 10, 11, 12, 13, 14, 15))

    def after_step(self, i, step):
        if i == 5:
            self.say("From here malloc returns A, you write fd, and a later malloc returns any address you chose.")
            self.wait(3.5)
            self.beat()


class Glibc109(HeapWalk):
    trace_id = "glibc-109"
    subtitle = "Safe-linking hides heap pointers, until one leak gives away the mask."
    code_rows = 9
    code_size = 16
    captions = {
        0: "glibc 2.32 mangles tcache and fastbin fd pointers. The stored fd is the slot's address shifted right 12, XOR next.",
        1: "A and B, 24 bytes each.",
        2: "free(a), then free(b). Neither fd looks like a heap pointer any more.",
        3: "A is the tail, so its fd is the mask XOR 0. Reading it hands you the mask directly.",
        4: "XOR B's fd with the mask and you get A's data. Store mask XOR target instead, and malloc hands back the target.",
    }

    def show_step(self, i, step):
        x = self.tr.extra["safeLinking"]
        if i == 2:
            rows = VGroup(
                mono(f"A.fd = ({h32(x['aVaddr'])} >> 12) ^ 0     = {x['aFdStored']:#x}", 18, T.tcache),
                mono(f"B.fd = ({h32(x['bVaddr'])} >> 12) ^ {x['bFdRevealed']:#x}   = {x['bFdStored']:#x}", 18, T.tcache),
            ).arrange(DOWN, buff=0.18, aligned_edge=LEFT).move_to([2.8, 1.9, 0])
            self.math = rows
            self.play(LaggedStartMap(FadeIn, rows, shift=LEFT * 0.2, lag_ratio=0.4))
        if i == 3:
            leak = mono(f"mask = A.fd = {x['aKey']:#x}", 20, T.leak).next_to(self.math, DOWN, buff=0.3, aligned_edge=LEFT)
            self.play(Write(leak))
            self.leak = leak
        if i == 4:
            rows = VGroup(
                mono(f"{x['bFdStored']:#x} ^ {x['bKey']:#x} = {x['bFdRevealed']:#x}   A's data", 18, T.leak),
                mono("B.fd = mask ^ target", 20, T.attacker_bytes),
            ).arrange(DOWN, buff=0.18, aligned_edge=LEFT).next_to(self.leak, DOWN, buff=0.25, aligned_edge=LEFT)
            foot = self.note("VRIG keeps next pointers as heap offsets, so A's data shows up as 0x8", rows.get_bottom() + DOWN * 0.3, 13)
            self.play(LaggedStartMap(FadeIn, rows, shift=LEFT * 0.2, lag_ratio=0.5), FadeIn(foot))


class Glibc110(HeapWalk):
    trace_id = "glibc-110"
    subtitle = "Lie about prev_size and free() merges right over a live chunk."
    code_rows = 9
    code_size = 16
    captions = {
        0: "free() checks the next chunk's P bit. If it's clear, glibc trusts prev_size to find the chunk behind.",
        1: "A, B, and C are 136 bytes each, with a guard at the end.",
        2: "free(A) goes to unsorted and clears the P bit in B's size.",
        3: "An overflow from B forges C's header. prev_size becomes 0x110 and P drops to 0.",
        4: "free(C) walks back 0x110 bytes, lands on A, and merges.",
    }

    def show_step(self, i, step):
        lay = self.lay
        if i == 3:
            c = chunk_named(step, "C")
            ch = self.chunk_mob("C", step)
            t = self.callout(ch.header, f"prev_size {c['prevSizeField']:#x}  size {c['sizeField']:#x}",
                             "attacker_bytes", UP, buff=0.55)
            back = c["addr"] - c["prevSizeField"]
            y = lay.y + lay.h / 2 + 0.22
            reach = Arrow([lay.x(c["addr"]), y, 0], [lay.x(back), y, 0], buff=0).set_color(T.attacker_bytes)
            rl = mono(f"back {c['prevSizeField']:#x} bytes", 15, T.attacker_bytes).next_to(reach, UP, buff=0.06)
            self.play(ch.header.animate.set_fill(T.attacker_bytes, 0.9), FadeIn(t))
            self.play(GrowArrow(reach), FadeIn(rl))
            self.forge = VGroup(t, reach, rl)

    def after_step(self, i, step):
        if i == 4:
            self.free_c()

    def free_c(self):
        x = self.tr.extra["freeC"]
        assert x["returned"]
        self.play(FadeOut(self.forge))
        anims = self.heap_stage.goto(self.strip.build(x)) + self.bin_stage.goto(self.bins.build(x))
        self.play(*anims, run_time=1.2)
        a = chunk_named(x, "A")
        # A and B now overlap in the sim. Lift A onto its own lane so both show.
        am = self.heap_stage.get(f"chunk:{a['addr']}")
        self.play(am.animate.shift(UP * (self.lay.h + 0.25)), run_time=1.0)
        lab = mono(f"merged free chunk  size {a['sizeField']:#x}", 17, T.freed_chunk).next_to(am, UP, buff=0.12)
        self.play(FadeIn(lab))
        self.say("The merged free chunk starts at A and covers B, which is still allocated. "
                 "The next malloc that fits hands out memory that overlaps B.")
        self.wait(5)
        self.beat()
