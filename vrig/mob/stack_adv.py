"""
Pieces for the stack_adv videos: a stack frame that can start partway up
(kern-104's kbuf is 64 bytes, nobody needs sixteen rows of 41s), C structs
drawn as field tables, and the protections row from an exercise.
"""
from __future__ import annotations

from manimlib import *

from vrig.mob.memory import CELL, LIFT, ROW, Word, mono, prose
from vrig.theme import T


class FrameView(VGroup):
    """
    StackView, but rows below `start` fold into one bar. Same rule as
    StackView: offset 0 at the bottom, so the overflow climbs.
    """

    def __init__(self, trace, step: int, start: int = 0, show_addr: bool = True,
                 offset_labels: bool = False):
        self.trace = trace
        self.start = start
        w = trace.word
        mem = trace.steps[step]["memory"]

        self.words = VGroup()
        for off in range(start, trace.total, w):
            word = Word(trace.addr(off), mem[off:off + w], "cell_fill", show_addr=show_addr or offset_labels)
            if offset_labels:
                # kern-104: VRIG's 0xbfff.. addresses would sit in user space,
                # so name slots by offset into the frame instead
                word.addr_label.become(mono(self.off_name(off), 15, T.text_dim)
                                       .next_to(word.cells, LEFT, buff=0.25))
            self.words.add(word)
        self.words.arrange(UP, buff=ROW - CELL, aligned_edge=RIGHT)

        parts = [self.words]
        self.fold = None
        if start > 0:
            n = start // w
            box = Rectangle(self.words[0].cells.get_width(), CELL * 1.1)
            box.set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            box.next_to(self.words, DOWN, buff=ROW - CELL).align_to(self.words, RIGHT)
            lab = mono(f"{n} more words", 15, T.text_dim).move_to(box).shift(LIFT)
            self.fold = VGroup(box, lab)
            parts.append(self.fold)
        self.tags = VGroup()
        parts.append(self.tags)
        super().__init__(*parts)

    def off_name(self, off: int) -> str:
        t = self.trace
        if off < t.buf_size:
            return f"kbuf+{off}"
        return f"+{off}"

    def at(self, offset: int) -> Word:
        return self.words[(offset - self.start) // self.trace.word]

    def region_tag(self, offset: int, text: str, role: str, n_words: int = 1) -> VGroup:
        w = self.trace.word
        lo = max(offset, self.start)
        hi = offset + (n_words - 1) * w
        bot = self.fold if offset < self.start and self.fold is not None else self.at(lo)
        top = self.at(hi)
        brace = Line(bot.get_corner(DR) + RIGHT * 0.15 + UP * 0.04,
                     top.get_corner(UR) + RIGHT * 0.15 + DOWN * 0.04)
        brace.set_stroke(getattr(T, role), 4)
        label = mono(text, 16, getattr(T, role)).next_to(brace, RIGHT, buff=0.15)
        tag = VGroup(brace, label)
        self.tags.add(tag)
        return tag

    def frame_tags(self, names: dict | None = None) -> VGroup:
        """names overrides the label per region: {'buffer': 'kbuf[64]', 'saved_fp': 'isAdmin'}"""
        t = self.trace
        names = names or {}
        tags = VGroup(self.region_tag(0, names.get("buffer", f"buf[{t.buf_size}]"), "buffer", t.buf_size // t.word))
        if t.canary_size:
            tags.add(self.region_tag(t.buf_size, names.get("canary", "canary"), "canary"))
        tags.add(self.region_tag(t.ebp_off, names.get("saved_fp", "saved ebp"), names.get("saved_fp_role", "saved_fp")))
        tags.add(self.region_tag(t.ret_off, names.get("saved_ret", "return addr"), "saved_ret"))
        return tags

    def write_word(self, offset: int, data: list[int], role: str, overflow: bool = False) -> list[Animation]:
        if offset < self.start:
            # folded rows: just pulse the bar so the copy still reads as moving
            return [Indicate(self.fold, color=getattr(T, role), scale_factor=1.02)]
        word = self.at(offset)
        anims = [Transform(c.label, c.relabel(b)) for c, b in zip(word.cells, data)]
        word.role = role
        anims.append(word.boxes().animate.set_fill(getattr(T, role), 0.85))
        if overflow:
            anims.append(Flash(word.cells.get_right(), color=T.crash, flash_radius=0.3, line_length=0.15))
        return anims


def _txt(s: str, size: int, color: str) -> Text:
    # Text("") has zero height and its center goes NaN when moved, so blanks
    # get an invisible placeholder
    if s:
        return mono(s, size, color)
    return mono(".", size, color).set_opacity(0)


class StructView(VGroup):
    """
    A C struct as a table, lowest offset on top the way source reads.
    fields: (offset text, name, value text). Value column can be swapped
    later with set().
    """

    def __init__(self, title: str, fields: list[tuple[str, str, str]], role: str = "cell_fill",
                 width: float = 4.2, size: int = 19, val_width: float = 1.7):
        self.rows = {}
        rows = VGroup()
        width *= size / 17  # widths below were picked at size 17
        for off, name, val in fields:
            box = Rectangle(width, 0.42 * size / 17).set_stroke(T.grid, 1.5).set_fill(getattr(T, role), 0.35 if role != "cell_fill" else 1)
            o = _txt(off, size - 3, T.text_dim)
            n = _txt(name, size, T.label)
            v = _txt(val, size, T.text)
            o.move_to(box.get_left() + RIGHT * 0.12, aligned_edge=LEFT)
            n.next_to(o, RIGHT, buff=0.2) if off else n.move_to(box.get_left() + RIGHT * 0.15, aligned_edge=LEFT)
            v.move_to(box.get_right() + LEFT * 0.15, aligned_edge=RIGHT)
            for m in (o, n, v):
                m.shift(LIFT)
            row = VGroup(box, o, n, v)
            self.rows[name] = row
            rows.add(row)
        rows.arrange(DOWN, buff=0)
        self.title = mono(title, size + 1, T.text).next_to(rows, UP, buff=0.15, aligned_edge=LEFT)
        self.body = rows
        super().__init__(self.title, rows)

    def row(self, name: str) -> VGroup:
        return self.rows[name]

    def set(self, name: str, val: str, role: str = "attacker_bytes") -> list[Animation]:
        box, _, _, old = self.rows[name]
        new = mono(val, int(old.font_size), getattr(T, role)).move_to(old, aligned_edge=RIGHT)
        if old.is_fixed_in_frame():
            new.fix_in_frame()
        return [Transform(old, new), box.animate.set_fill(getattr(T, role), 0.3),
                Indicate(self.rows[name][2], color=getattr(T, role), scale_factor=1.1)]


def pointer(a: Mobject, b: Mobject, role: str = "pointer", side=RIGHT, bend: float = -0.6) -> VMobject:
    """Arrow from the right edge of one row to the left edge of another."""
    start = a.get_right() if np.dot(side, RIGHT) > 0 else a.get_left()
    end = b.get_left() if b.get_center()[0] > a.get_center()[0] else b.get_right()
    return Arrow(start, end, buff=0.08, path_arc=bend, stroke_width=4).set_color(getattr(T, role))


PROT_ROLE = {"active": "mitigation", "bypassed": "attacker_bytes", "disabled": "text_dim"}


def protection_row(prots: list[dict], size: int = 18) -> VGroup:
    chips = VGroup()
    for p in prots:
        role = PROT_ROLE.get(p["status"], "text_dim")
        txt = mono(f"{p['name']}  {p['status']}", size, getattr(T, role))
        box = SurroundingRectangle(txt, buff=0.12).set_stroke(getattr(T, role), 1.5)
        chips.add(VGroup(box, txt))
    return chips.arrange(RIGHT, buff=0.25)
