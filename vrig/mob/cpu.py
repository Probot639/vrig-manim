from __future__ import annotations

from manimlib import *

from vrig.mob.memory import LIFT, mono
from vrig.theme import T


class RegisterFile(VGroup):
    def __init__(self, names=("eip", "esp", "eax", "ebx"), values: dict | None = None, width: int = 8):
        values = values or {}
        self.width = width
        self.rows = {}
        rows = VGroup()
        for n in names:
            name = mono(n, 20, T.label)
            val = self._val(values.get(n))
            row = VGroup(name, val).arrange(RIGHT, buff=0.3)
            self.rows[n] = row
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        bg = SurroundingRectangle(rows, buff=0.22).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.9)
        bg.shift(-LIFT)
        super().__init__(bg, rows)

    def _val(self, v):
        if v is None:
            return mono("?" * self.width, 20, T.text_dim)
        return mono(f"{v:0{self.width}x}", 20, T.text)

    def set(self, name: str, value: int, role: str = "highlight") -> list[Animation]:
        old = self.rows[name][1]
        new = self._val(value).set_color(getattr(T, role)).move_to(old, aligned_edge=LEFT)
        if old.is_fixed_in_frame():
            # otherwise the new text lives in world space and the HUD value
            # vanishes into the 3d scene mid-transform
            new.fix_in_frame()
        return [Transform(old, new), Indicate(self.rows[name][0], color=getattr(T, role), scale_factor=1.15)]


class CodeListing(VGroup):
    """Source lines with a bar that follows execution."""

    def __init__(self, lines: list[str], size: int = 18, keep_blank: bool = True):
        self.lines = VGroup()
        for line in lines:
            txt = line if line.strip() or keep_blank else None
            if txt is None:
                continue
            # Text() of an empty string has no height, which wrecks arrange()
            m = mono(line if line.strip() else ".", size, T.label)
            if not line.strip():
                m.set_opacity(0)
            if line.lstrip().startswith("//"):
                m.set_color(T.text_dim)
            self.lines.add(m)
        self.lines.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
        # re-indent: Text strips leading spaces when it measures
        for m, line in zip(self.lines, lines):
            indent = len(line) - len(line.lstrip(" "))
            m.shift(RIGHT * indent * 0.105 * size / 18)
        self.bar = BackgroundRectangle(self.lines[0], buff=0.06)
        self.bar.set_fill(T.highlight, 0.18).set_opacity(0).shift(-LIFT)
        super().__init__(self.bar, self.lines)

    def focus(self, i: int) -> Animation:
        line = self.lines[i]
        target = BackgroundRectangle(line, buff=0.06).set_fill(T.highlight, 0.18)
        target.stretch_to_fit_width(self.lines.get_width() + 0.2).align_to(self.lines, LEFT).shift(LEFT * 0.1)
        target.shift(-LIFT)
        return Transform(self.bar, target)
