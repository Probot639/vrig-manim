"""
Title and closing cards for the per-unit overview videos. tools/overview.sh
renders these and splices a few seconds of each lesson video between them.

    VRIG_UNIT=unit0-asm manimgl scenes/overview.py UnitIntro -w --hd
"""
import json
import os
from pathlib import Path

from manimlib import *

from vrig.mob.memory import mono, prose
from vrig.scene import VrigScene
from vrig.theme import T

UNITS = {u["id"]: u for u in json.loads(
    (Path(__file__).parent.parent / "traces/units.json").read_text())["units"]}


def unit():
    uid = os.environ.get("VRIG_UNIT", "unit0-asm")
    return UNITS[uid]


def lesson_name(title: str) -> str:
    # VRIG numbers some titles ("03: Arrays & Strings") and not others
    head, _, rest = title.partition(": ")
    return rest if rest and head.isdigit() else title


class UnitIntro(VrigScene):
    def construct(self):
        u = unit()
        track = mono(u["track"].upper(), 20, T.text_dim)
        name = prose(u["name"], 64)
        count = prose(f"{len(u['lessons'])} lessons", 26, T.label)
        head = VGroup(track, name, count).arrange(DOWN, buff=0.25)
        self.play(FadeIn(track, shift=DOWN * 0.1), Write(name), run_time=1.2)
        self.play(FadeIn(count))
        self.wait(0.6)

        rows = VGroup(*[
            VGroup(mono(f"{i + 1:02d}", 20, T.highlight), prose(lesson_name(l["title"]), 24))
            .arrange(RIGHT, buff=0.3)
            for i, l in enumerate(u["lessons"])
        ])
        for r in rows:
            r[1].align_to(r[0], DOWN)
        # long units split into two columns so nothing runs off the bottom
        if len(rows) > 5:
            half = (len(rows) + 1) // 2
            cols = VGroup(rows[:half].copy(), rows[half:].copy())
            rows = VGroup(*cols[0], *cols[1])
            for c in cols:
                c.arrange(DOWN, buff=0.28, aligned_edge=LEFT)
            cols.arrange(RIGHT, buff=1.2, aligned_edge=UP)
            listing = cols
        else:
            listing = rows.arrange(DOWN, buff=0.28, aligned_edge=LEFT)
        listing.next_to(head, DOWN, buff=0.7)
        VGroup(head, listing).center()

        self.play(LaggedStartMap(FadeIn, rows, shift=RIGHT * 0.15, lag_ratio=0.12), run_time=1.6)
        self.wait(2.2)
        self.play(FadeOut(VGroup(head, listing)))


class UnitOutro(VrigScene):
    def construct(self):
        u = unit()
        name = prose(u["name"], 48)
        line = prose("Every value on screen comes from VRIG's own engine.", 26, T.label)
        where = mono(f"videos/{u['id']}/", 20, T.text_dim)
        VGroup(name, line, where).arrange(DOWN, buff=0.35)
        self.play(FadeIn(name, shift=UP * 0.1))
        self.play(FadeIn(line), FadeIn(where))
        self.wait(2.0)
        self.play(FadeOut(VGroup(name, line, where)))
