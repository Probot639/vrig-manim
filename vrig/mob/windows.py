"""
Windows pieces: trace loaders for the unit8/unit9 exports, a heap column that
reads WinHeapSim snapshots, SEH records, the CFG slot strip, and the LFH
subsegment. Same rules as memory.py: low addresses at the bottom, byte 0 on
the left.
"""
from __future__ import annotations

import json

from manimlib import *

from vrig.mob.memory import CELL, GAP, LIFT, ROW, ByteCell, Word, mono
from vrig.theme import T
from vrig.trace import TRACE_DIR, StackTrace, h32


class WinStackTrace(StackTrace):
    """StackTrace plus what windows-entry.ts adds on top."""

    def __init__(self, raw: dict):
        super().__init__(raw)
        self.desc = raw["desc"]
        self.win_title = raw["winTitle"]
        self.win_msg = raw["winMsg"]
        self.solved = raw["solved"]
        self.canary = raw["canary"]
        self.attempts = raw["attempts"]
        self.orig_ret = raw["origRetAddr"]

    @classmethod
    def load(cls, name: str) -> "WinStackTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def final(self) -> dict:
        return self.steps[-1]

    def log_with(self, needle: str, steps=None) -> str:
        for s in steps or self.steps:
            for l in s["logs"]:
                if needle in l["msg"]:
                    return l["msg"]
        raise KeyError(needle)


class HeapTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.source = raw["source"]
        self.symbols = raw["symbols"]
        self.timeline = raw["timeline"]
        self.base = raw["baseAddr"]
        self.key = raw["encodingKey"]
        self.payload = raw["payload"]
        self.solved = raw["solved"]
        self.win_title = raw["winTitle"]
        self.win_msg = raw["winMsg"]
        self.version = raw["winFlags"]["winVersion"]
        self.lfh = raw.get("lfh")
        self.attempts = raw["attempts"]

    @classmethod
    def load(cls, name: str) -> "HeapTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def addr(self, off: int) -> int:
        return self.base + off

    def snap(self, label: str) -> dict:
        return next(s for s in self.timeline if s["label"] == label)

    def chunk(self, snap: dict, off: int) -> dict:
        return next(c for c in snap["chunks"] if c["addr"] == off)


def source_lines(src: list[str]) -> tuple[list[str], dict[int, int]]:
    """
    Drop #includes and doubled blank lines so the listing fits beside the
    stack. Also returns VRIG line index -> listing index, since step srcLines
    count the dropped lines.
    """
    out, where = [], {}
    for i, l in enumerate(src):
        if l.startswith("#include"):
            continue
        if not l.strip() and (not out or not out[-1].strip()):
            continue
        where[i] = len(out)
        out.append(l)
    while out and not out[-1].strip():
        out.pop()
    return out, where


def side_tag(rows: VGroup, text: str, role: str, side=RIGHT, size: int = 16) -> VGroup:
    """Bracket and name beside a run of rows (bottom row first)."""
    bot, top = rows[0], rows[-1]
    edge = bot.cells if hasattr(bot, "cells") else bot
    edge_top = top.cells if hasattr(top, "cells") else top
    if side is RIGHT:
        a = edge.get_corner(DR) + RIGHT * 0.15 + UP * 0.04
        b = edge_top.get_corner(UR) + RIGHT * 0.15 + DOWN * 0.04
    else:
        a = edge.get_corner(DL) + LEFT * 0.15 + UP * 0.04
        b = edge_top.get_corner(UL) + LEFT * 0.15 + DOWN * 0.04
    bar = Line(a, b).set_stroke(getattr(T, role), 4)
    lab = mono(text, size, getattr(T, role)).next_to(bar, side, buff=0.15)
    return VGroup(bar, lab)


class HeapColumn(VGroup):
    """
    Heap bytes [start, end) as 8-byte rows, bottom row lowest. Every row is a
    Word, so recolor with .boxes() and swap labels the same way StackView does.
    """

    def __init__(self, tr: HeapTrace, snap: dict, start: int, end: int, per_row: int = 8):
        self.tr = tr
        self.start, self.per_row = start, per_row
        mem = snap["memory"]
        self.rows = VGroup(*(Word(tr.addr(o), mem[o:o + per_row]) for o in range(start, end, per_row)))
        self.rows.arrange(UP, buff=ROW - CELL, aligned_edge=RIGHT)
        super().__init__(self.rows)

    def row(self, off: int) -> Word:
        return self.rows[(off - self.start) // self.per_row]

    def cell(self, off: int) -> ByteCell:
        return self.row(off).cells[(off - self.start) % self.per_row]

    def span(self, off: int, n: int) -> VGroup:
        return VGroup(*(self.cell(o) for o in range(off, off + n)))

    def rows_for(self, off: int, n: int) -> VGroup:
        return VGroup(*(self.row(o) for o in range(off, off + n, self.per_row)))

    def paint(self, off: int, n: int, role: str, opacity: float = 0.85) -> Animation:
        boxes = VGroup(*(c.box for c in self.span(off, n)))
        return boxes.animate.set_fill(getattr(T, role), opacity if role != "cell_fill" else 1)

    def morph(self, snap: dict, off: int, n: int) -> list[Animation]:
        """Relabel bytes that changed between what's shown and `snap`."""
        anims = []
        for o in range(off, off + n):
            c = self.cell(o)
            b = snap["memory"][o]
            if c.value != b:
                anims.append(Transform(c.label, c.relabel(b)))
        return anims


class Slab(Group):
    """Labelled prism, the 3D stand-in for a record or block. Text lifted off the top."""

    def __init__(self, text: str, role: str, width=2.2, depth=0.7, height=0.25, size=20, sub: str | None = None,
                 text_role: str = "text"):
        self.body = Prism(width, depth, height, color=getattr(T, role), opacity=0.9)
        self.body.shift(OUT * height / 2)
        self.h = height
        lines = [mono(text, size, getattr(T, text_role))]
        if sub:
            lines.append(mono(sub, int(size * 0.7), T.text_dim))
        self.lab = VGroup(*lines).arrange(DOWN, buff=0.05)
        self.lab.move_to(self.body.get_center()).shift(OUT * (height / 2 + 0.01))
        self.role = role
        super().__init__(self.body, self.lab)

    def top(self):
        return self.body.get_center() * np.array([1, 1, 0]) + OUT * (self.h + 0.01)

    def stand(self, frame, depth: float):
        """Stand the label up facing the camera, just over the slab's front edge (CodeBlock does the same)."""
        from vrig.mob.space import billboard
        self.lab.move_to(self.body.get_center() * np.array([1, 1, 0]))
        billboard(self.lab, frame)
        self.lab.shift(OUT * (self.h + 0.3) + DOWN * depth * 0.2)
        return self


class SehRecord(VGroup):
    """EXCEPTION_REGISTRATION_RECORD as two cells: Next, then Handler."""

    def __init__(self, title: str, next_txt: str, handler_txt: str, role: str = "saved_fp", w: float = 2.0):
        self.next = self._field("Next", next_txt, role, w)
        self.handler = self._field("Handler", handler_txt, "saved_ret", w)
        body = VGroup(self.next, self.handler).arrange(RIGHT, buff=0.06)
        self.title = mono(title, 15, T.label).next_to(body, UP, buff=0.1)
        super().__init__(body, self.title)

    @staticmethod
    def _field(name, val, role, w):
        box = Rectangle(w, 0.62).set_stroke(T.grid, 1.5).set_fill(getattr(T, role), 0.35).shift(IN * 0.01)
        n = mono(name, 13, T.text_dim)
        v = mono(val, 16, T.text)
        VGroup(n, v).arrange(DOWN, buff=0.04).move_to(box).shift(OUT * 0.01)  # box sits at -0.01
        return VGroup(box, n, v)

    def set_value(self, field: str, txt: str, role: str) -> list[Animation]:
        f = getattr(self, field)
        new = mono(txt, 16, getattr(T, role)).move_to(f[2])  # f[2] is already lifted
        return [Transform(f[2], new), f[0].animate.set_fill(getattr(T, role), 0.5)]


def ptr_arrow(a, b, role: str = "pointer", path_arc: float = 0, width: float = 3) -> Arrow:
    arr = Arrow(a, b, buff=0.08, path_arc=path_arc, thickness=width)
    return arr.set_color(getattr(T, role))


class LfhGrid(Group):
    """
    A UserBlocks subsegment: nSlots same-size slots in a grid on the floor.
    In-use slots stand up, free ones lie flat.
    """

    def __init__(self, n: int, cols: int = 8, cell: float = 0.62, gap: float = 0.1):
        self.n, self.cols, self.cell = n, cols, cell
        self.tiles = Group()
        self.posts = Group()
        for i in range(n):
            r, c = divmod(i, cols)
            p = np.array([c * (cell + gap), -r * (cell + gap), 0.0])
            tile = Square(cell).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1).move_to(p)
            self.tiles.add(tile)
        self.tiles.center()
        self.idx = VGroup(*(mono(str(i), 13, T.text_dim).move_to(t.get_center() + LIFT) for i, t in enumerate(self.tiles)))
        super().__init__(self.tiles, self.idx)
        self.up: dict[int, Prism] = {}

    def post(self, i: int, role: str = "chunk_user", h: float = 0.45) -> Prism:
        p = Prism(self.cell * 0.86, self.cell * 0.86, h, color=getattr(T, role), opacity=0.92)
        p.move_to(self.tiles[i].get_center() + OUT * h / 2)
        return p

    def raise_slot(self, i: int, role: str = "chunk_user") -> Animation:
        p = self.post(i, role)
        self.up[i] = p
        return FadeIn(p, shift=OUT * 0.3)

    def drop_slot(self, i: int) -> Animation:
        p = self.up.pop(i)
        return FadeOut(p, shift=IN * 0.3)

    def top(self, i: int):
        return self.tiles[i].get_center() + OUT * 0.5


class CfgStrip(Group):
    """CFG's slot table over .text, one tile per 16 bytes. Valid call targets stand up."""

    def __init__(self, slots: list[dict], tile: float = 0.42, gap: float = 0.06):
        self.slots = slots
        self.tiles = Group()
        self.posts = {}
        for i, s in enumerate(slots):
            t = Square(tile).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 1)
            t.move_to(RIGHT * i * (tile + gap))
            self.tiles.add(t)
        self.tiles.center()
        for i, s in enumerate(slots):
            if s["valid"]:
                p = Prism(tile * 0.85, tile * 0.85, 0.55, color=T.mitigation, opacity=0.9)
                p.move_to(self.tiles[i].get_center() + OUT * 0.275)
                self.posts[i] = p
        super().__init__(self.tiles, *self.posts.values())

    def top(self, i: int, h: float | None = None):
        z = 0.56 if i in self.posts else 0.02
        return self.tiles[i].get_center() + OUT * (z if h is None else h)
