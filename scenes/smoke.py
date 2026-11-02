from manimlib import *

from vrig.scene import VrigScene
from vrig.theme import T


# Throwaway: every role as a swatch, to eyeball a preset after editing it.
class ThemeSwatches(VrigScene):
    def construct(self):
        cells = VGroup()
        for role, color in T.roles.items():
            box = Square(0.55).set_fill(color, 1).set_stroke(width=0)
            name = Text(role, font_size=16).set_color(T.label).next_to(box, DOWN, buff=0.08)
            cells.add(VGroup(box, name))
        cells.arrange_in_grid(n_cols=8, buff=0.35)
        title = Text(f"theme: {T.name}", font_size=32).set_color(T.text).to_edge(UP)
        self.add(title, cells.next_to(title, DOWN, buff=0.4))
