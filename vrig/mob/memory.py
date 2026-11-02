"""
Memory as cells. One rule everywhere: lower addresses at the bottom, higher at
the top, and within a word byte 0 sits on the left. So a little-endian word
reads backwards across its row, which is the point.
"""
from __future__ import annotations

from manimlib import *

from vrig.theme import T

CELL = 0.44
# Text sitting exactly on its box z-fights under ThreeDScene's depth test and
# comes out hollow. Lift it a hair toward the camera.
LIFT = OUT * 0.01
GAP = 0.04
ROW = CELL + 0.08


def mono(s: str, size: int = 20, color: str | None = None) -> Text:
    return Text(s, font=T.mono, font_size=size).set_color(color or T.text)


def prose(s: str, size: int = 28, color: str | None = None) -> Text:
    return Text(s, font=T.prose, font_size=size).set_color(color or T.text)


def tex(s: str, size: int = 36, color: str | None = None) -> Tex:
    # math only. needs the "basic" template from custom_config.yml, the
    # default one wants half of texlive-fontsextra
    return Tex(s, font_size=size).set_color(color or T.text)


class ByteCell(VGroup):
    def __init__(self, value: int | None = None, role: str = "cell_fill", glyph: str | None = None, **kw):
        self.box = Square(CELL).set_stroke(T.grid, 1.5)
        self.value = value
        # glyph overrides the hex, for views that show typed text as letters
        self.label = mono(glyph if glyph is not None else ("--" if value is None else f"{value:02x}"),
                          20 if glyph is not None else 16)
        self.label.move_to(self.box).shift(LIFT)
        super().__init__(self.box, self.label, **kw)
        self.paint(role)

    def paint(self, role: str, opacity: float = 0.85):
        color = getattr(T, role)
        self.box.set_fill(color, opacity if role != "cell_fill" else 1)
        # dark text on light fills, light on dark. 3b1b presets have both.
        dark_fill = role != "cell_fill" and _luma(color) > 0.55
        self.label.set_color(T.background if dark_fill else T.text)
        return self

    def relabel(self, value: int, glyph: str | None = None) -> Text:
        """New label, positioned, not yet swapped in. Caller animates it."""
        self.value = value
        txt = mono(glyph, 20) if glyph is not None else mono(f"{value:02x}", 16)
        return txt.set_color(self.label.get_color()).move_to(self.box).shift(LIFT)


def _luma(hexcolor: str) -> float:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class Word(VGroup):
    """One stack slot: four (or eight) ByteCells, address on the left."""

    def __init__(self, addr: int, data: list[int], role: str = "cell_fill", show_addr: bool = True):
        self.addr = addr
        self.cells = VGroup(*(ByteCell(b, role) for b in data)).arrange(RIGHT, buff=GAP)
        parts = [self.cells]
        self.addr_label = mono(f"0x{addr:08x}", 15, T.text_dim)
        self.addr_label.next_to(self.cells, LEFT, buff=0.25)
        if show_addr:
            parts.append(self.addr_label)
        super().__init__(*parts)
        self.role = role

    def boxes(self) -> VGroup:
        # recolor these, never self.cells: set_fill on cells repaints the hex text too
        return VGroup(*(c.box for c in self.cells))

    def value(self) -> int:
        return int.from_bytes(bytes(c.value or 0 for c in self.cells), "little")

    def paint(self, role: str):
        self.role = role
        for c in self.cells:
            c.paint(role)
        return self


class StackView(VGroup):
    """
    A stack from a StackTrace. Offset 0 (buf[0]) is the bottom row, so the
    overflow visibly climbs toward the saved registers.
    """

    def __init__(self, trace, n_words: int | None = None, step: int | None = None):
        self.trace = trace
        mem = trace.raw["initial"]["memory"] if step is None else trace.steps[step]["memory"]
        n_words = n_words or trace.total // trace.word
        w = trace.word

        self.words = VGroup()
        for i in range(n_words):
            off = i * w
            # unwritten slots above the frame start blank, not zero: we don't
            # know what the caller had there and pretending 00 is a lie
            data = mem[off:off + w]
            role = "cell_fill"
            word = Word(trace.addr(off), data, role)
            if trace.region(off) == "arg" and not any(mem[off:off + w]):
                for c in word.cells:
                    c.label.become(mono("??", 16, T.text_dim).move_to(c.box).shift(LIFT))
                    c.value = None
            self.words.add(word)
        self.words.arrange(UP, buff=ROW - CELL, aligned_edge=RIGHT)

        self.tags = VGroup()
        super().__init__(self.words, self.tags)

    def at(self, offset: int) -> Word:
        return self.words[offset // self.trace.word]

    def region_tag(self, offset: int, text: str, role: str, n_words: int = 1) -> VGroup:
        """Bracket + name on the right of a run of words."""
        top = self.at(offset + (n_words - 1) * self.trace.word)
        bot = self.at(offset)
        brace = Line(bot.get_corner(DR) + RIGHT * 0.15 + UP * 0.04,
                     top.get_corner(UR) + RIGHT * 0.15 + DOWN * 0.04)
        brace.set_stroke(getattr(T, role), 4)
        label = mono(text, 16, getattr(T, role)).next_to(brace, RIGHT, buff=0.15)
        tag = VGroup(brace, label)
        self.tags.add(tag)
        return tag

    def frame_tags(self) -> VGroup:
        t = self.trace
        return VGroup(
            self.region_tag(0, f"buf[{t.buf_size}]", "buffer", t.buf_size // t.word),
            self.region_tag(t.ebp_off, "saved ebp", "saved_fp"),
            self.region_tag(t.ret_off, "return addr", "saved_ret"),
        )

    def write_word(self, offset: int, data: list[int], role: str, overflow: bool = False) -> list[Animation]:
        """Animations that drop new bytes into a word and recolor it."""
        word = self.at(offset)
        anims = []
        for cell, b in zip(word.cells, data):
            new = cell.relabel(b)
            anims.append(Transform(cell.label, new))
        word.role = role
        anims.append(word.boxes().animate.set_fill(getattr(T, role), 0.85))
        if overflow:
            anims.append(Flash(word.cells.get_right(), color=T.crash, flash_radius=0.3, line_length=0.15))
        return anims


def le_assemble(word: Word, color: str | None = None) -> tuple[VGroup, list[Animation]]:
    """
    Copies of the byte labels slide right and re-stack in reverse to form the
    word's value. Shows little-endian without saying "little-endian".
    """
    pieces = VGroup(*(c.label.copy() for c in word.cells))
    target = VGroup(*(mono(f"{c.value:02x}", 18, color or T.highlight) for c in reversed(word.cells)))
    target.arrange(RIGHT, buff=0.02)
    prefix = mono("0x", 18, color or T.highlight)
    value = VGroup(prefix, target).arrange(RIGHT, buff=0.02)
    value.next_to(word, RIGHT, buff=0.35)
    anims = [
        TransformFromCopy(word.cells[i].label, target[len(word.cells) - 1 - i], path_arc=-60 * DEG)
        for i in range(len(word.cells))
    ]
    anims.append(FadeIn(prefix, shift=LEFT * 0.2))
    return value, anims


class PayloadStrip(VGroup):
    """The raw input as one row of bytes, the way gets() sees it."""

    def __init__(self, data: list[int], per_row: int = 24, w: int = 4):
        self.cells = VGroup(*(ByteCell(b, "attacker_bytes") for b in data))
        rows = VGroup()
        for r in range(0, len(data), per_row):
            row = VGroup()
            for k in range(r, min(r + per_row, len(data)), w):
                row.add(VGroup(*self.cells[k:k + w]).arrange(RIGHT, buff=0.02))
            rows.add(row.arrange(RIGHT, buff=0.12))
        rows.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        rows.set_width(min(rows.get_width(), 6.2))
        super().__init__(rows)

    def word(self, i: int, w: int = 4) -> VGroup:
        return self.cells[i * w:(i + 1) * w]
