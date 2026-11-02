"""
Heap walkthrough view. Reads traces from tools/vrig-trace/walk_heap-entry.ts
(VRIG's HeapSim / WinHeapSim after every guided step) and draws:

    HeapStrip   chunks left to right by address, width = real chunk size,
                header part + user part, top chunk at the end
    BinsPanel   tcache / fastbin / unsorted / ListHints as linked lists
    ChunkBytes  one chunk byte by byte, for the header-anatomy exercises

Nothing here keeps state between steps. Each step builds fresh mobjects keyed
by what they are (chunk at 0x18, second node of tcache[24], ...) and Stage
diffs the keys, so a chunk that changes morphs and a chunk that appears grows.

Kept apart from the heap-exploit scenes on purpose, they have their own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from manimlib import *

from vrig.mob.memory import LIFT, ByteCell, CELL, GAP, _luma, mono, prose
from vrig.theme import T
from vrig.trace import TRACE_DIR, h32


# -- trace -------------------------------------------------------------------

class HeapTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.unit = raw["unit"]
        self.title = raw["title"]
        self.source = raw["source"]
        self.steps = raw["steps"]
        self.initial = raw["initial"]
        self.base = raw["baseAddr"]
        self.hdr = raw["headerSize"]
        self.win = raw["sim"] == "WinHeapSim"
        self.heap_size = raw["heapSize"]
        self.extra = raw.get("extra", {})

    @classmethod
    def load(cls, name: str) -> "HeapTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def snaps(self):
        yield self.initial
        yield from self.steps

    def span(self, snaps=None) -> int:
        """Bytes from the heap start to the furthest chunk end or top start."""
        far = 0
        for s in snaps or self.snaps():
            far = max(far, s["top"]["addr"])
            for c in s["chunks"]:
                far = max(far, c["addr"] + c["size"])
        return far

    def addr(self, off: int) -> str:
        return h32(self.base + off)


def chunk_at(snap: dict, addr: int) -> dict | None:
    return next((c for c in snap["chunks"] if c["addr"] == addr), None)


def chunk_named(snap: dict, name: str) -> dict | None:
    a = snap["names"].get(name)
    return None if a is None else chunk_at(snap, a)


def le32(bs, off: int = 0) -> int:
    return int.from_bytes(bytes(bs[off:off + 4]), "little")


# -- free lists --------------------------------------------------------------

# no theme role for smallbin/largebin or the Windows lists. unsorted is the
# closest (doubly linked, sorted later), LFH buckets borrow tcache.
BIN_ROLE = {"tcache": "tcache", "fastbins": "fastbin", "unsorted": "unsorted", "smallbins": "unsorted",
            "largebins": "unsorted", "listHints": "unsorted"}
BIN_NAME = {"tcache": "tcache", "fastbins": "fastbin", "unsorted": "unsorted", "smallbins": "smallbin",
            "largebins": "largebin", "listHints": "ListHints"}
DOUBLY = {"unsorted", "smallbins", "largebins", "listHints"}


@dataclass
class BinList:
    key: str      # "tcache:24"
    kind: str     # "tcache"
    size: int     # bytes, or 8-byte units for ListHints
    nodes: list   # chunk addrs, head first

    @property
    def label(self) -> str:
        if self.kind == "unsorted":
            return "unsorted"
        return f"{BIN_NAME[self.kind]}[{self.size}]"

    @property
    def role(self) -> str:
        return BIN_ROLE[self.kind]


def bin_lists(snap: dict) -> list[BinList]:
    out = []
    fl = snap["freeLists"]
    for kind in ("tcache", "fastbins", "smallbins", "largebins", "listHints"):
        for size, addrs in (fl.get(kind) or {}).items():
            # HeapSim pushes new frees on the end, so the head is the last
            # element. WinHeapSim unshifts into ListHints, head is first.
            nodes = list(addrs) if kind == "listHints" else list(reversed(addrs))
            out.append(BinList(f"{kind}:{size}", kind, int(size), nodes))
    if "unsorted" in fl:
        out.append(BinList("unsorted:0", "unsorted", 0, list(reversed(fl["unsorted"]))))
    return out


def bin_of(snap: dict, addr: int) -> BinList | None:
    for b in bin_lists(snap):
        if addr in b.nodes:
            return b
    return None


# -- layout ------------------------------------------------------------------

class Layout:
    """Byte offset -> x. The top chunk is drawn capped, it's mostly empty."""

    def __init__(self, span: int, left: float = -6.5, right: float = 6.5, y: float = -1.85,
                 top_cap: int | None = None, height: float = 1.1):
        self.span = span
        self.top_cap = top_cap if top_cap is not None else max(32, span // 4)
        self.left, self.right, self.y, self.h = left, right, y, height
        self.scale = (right - left) / (span + self.top_cap)

    def x(self, off: int) -> float:
        return self.left + off * self.scale

    def w(self, nbytes: int) -> float:
        return nbytes * self.scale


def fit(mob: Mobject, width: float, min_scale: float = 0.45) -> Mobject | None:
    if mob.get_width() <= width:
        return mob
    k = width / mob.get_width()
    if k < min_scale:
        return None
    return mob.scale(k)


def text_on(role: str) -> str:
    # same rule ByteCell uses: dark text on light fills
    return T.background if _luma(getattr(T, role)) > 0.55 else T.text


# -- chunk strip -------------------------------------------------------------

class ChunkBlock(VGroup):
    """
    One chunk. Header part is always hdr bytes wide, so on small chunks you
    can see how much of the chunk is bookkeeping.
    """

    def __init__(self, chunk: dict, lay: Layout, hdr: int, name: str | None = None,
                 body: str | None = None, head: str | None = None, user_role: str | None = None,
                 show_addr: str | None = None):
        x0 = lay.x(chunk["addr"])
        wh, wu = lay.w(hdr), lay.w(chunk["size"] - hdr)
        role = user_role or ("chunk_user" if chunk["allocated"] else "freed_chunk")
        self.role = role
        self.header = Rectangle(wh, lay.h).set_fill(T.chunk_header, 0.9).set_stroke(T.background, 1.5)
        self.header.move_to([x0 + wh / 2, lay.y, 0])
        self.user = Rectangle(wu, lay.h).set_fill(getattr(T, role), 0.85).set_stroke(T.background, 1.5)
        self.user.move_to([x0 + wh + wu / 2, lay.y, 0])
        parts = [self.header, self.user]

        self.name = None
        if name:
            t = fit(mono(name, 21, text_on(role)), wu - 0.08, 0.45)
            if t is not None:
                t.move_to(self.user).shift(UP * (0.17 if body else 0) + LIFT)
                self.name = t
                parts.append(t)
        self.body = None
        if body and wu >= 0.6:
            t = fit(mono(body, 15, text_on(role)), wu - 0.08, 0.55)
            if t is not None:
                t.move_to(self.user).shift(DOWN * (0.18 if name else 0) + LIFT)
                self.body = t
                parts.append(t)
        self.head = None
        if head and wh >= 0.16:
            t = fit(mono(head, 14, text_on("chunk_header")), lay.h - 0.1, 0.5)
            if t is not None:
                t.rotate(90 * DEG).move_to(self.header).shift(LIFT)
                if t.get_height() > lay.h - 0.06:
                    t.set_height(lay.h - 0.06)
                self.head = t
                parts.append(t)
        self.addr_lab = None
        if show_addr:
            t = mono(show_addr, 14, T.text_dim)
            t.next_to(self.header, DOWN, buff=0.1, aligned_edge=LEFT)
            self.addr_lab = t
            parts.append(t)
        super().__init__(*parts)
        self.sig = (chunk["addr"], chunk["size"], role, name, body, head, show_addr, round(lay.scale, 5))


class TopBlock(VGroup):
    def __init__(self, top: dict, lay: Layout, label: str = "top", show_addr: str | None = None):
        x0 = lay.x(top["addr"])
        w = min(lay.right - x0, lay.w(min(top["size"], lay.top_cap)))
        w = max(w, 0.05)
        self.box = Rectangle(w, lay.h).set_fill(T.top_chunk, 0.55).set_stroke(T.top_chunk, 1.5)
        self.box.move_to([x0 + w / 2, lay.y, 0])
        parts = [self.box]
        lab = fit(mono(f"{label}\n{top['size']} B", 16, T.text), w - 0.08, 0.5)
        if lab is not None:
            lab.move_to(self.box).shift(LIFT)
            parts.append(lab)
        if show_addr and w > 0.9:
            a = mono(show_addr, 14, T.text_dim).next_to(self.box, DOWN, buff=0.1, aligned_edge=LEFT)
            parts.append(a)
        super().__init__(*parts)
        self.sig = (top["addr"], top["size"], label, show_addr, round(lay.scale, 5))


def fd_arc(a: np.ndarray, b: np.ndarray, role: str, height: float = 0.55) -> VMobject:
    """Pointer from one chunk to another, bowed up over the strip."""
    if np.allclose(a, b, atol=0.05):
        # self-loop (a chunk that points at itself after a double free)
        loop = Arc(radius=0.24, start_angle=-60 * DEG, angle=300 * DEG, arc_center=a + UP * 0.3)
        loop.set_stroke(getattr(T, role), 3)
        end, prev = loop.get_end(), loop.pfp(0.95)
        tip = ArrowTip(angle=angle_of_vector(end - prev)).scale(0.45).set_fill(getattr(T, role))
        tip.shift(end - tip.get_tip_point())
        return VGroup(loop, tip)
    d = b[0] - a[0]
    h = min(height + 0.1 * abs(d), 0.95)
    curve = ParametricCurve(lambda t: a + (b - a) * t + UP * h * 4 * t * (1 - t), t_range=(0, 1, 0.02))
    curve.set_stroke(getattr(T, role), 3)
    end = curve.get_end()
    prev = curve.pfp(0.97)
    tip = ArrowTip(angle=angle_of_vector(end - prev)).scale(0.45).set_fill(getattr(T, role))
    tip.shift(end - tip.get_tip_point())
    return VGroup(curve, tip)


class HeapStrip:
    """
    Builds a {key: mobject} dict for one snapshot. Scenes pass hooks to decide
    names, what goes in the user part, and the header text.
    """

    def __init__(self, trace: HeapTrace, lay: Layout, name_fn=None, body_fn=None, head_fn=None,
                 role_fn=None, arrows: bool = True, addrs: bool = True, top_label: str | None = None):
        self.tr, self.lay = trace, lay
        self.name_fn = name_fn or (lambda c, s: "/".join(c["names"]) or None)
        self.body_fn = body_fn or default_body(trace)
        self.head_fn = head_fn or default_head(trace)
        self.role_fn = role_fn or (lambda c, s: None)
        self.arrows = arrows
        self.addrs = addrs
        self.top_label = top_label or ("free" if trace.win else "top")

    def build(self, snap: dict) -> dict:
        lay, tr = self.lay, self.tr
        out = {}
        for c in snap["chunks"]:
            wide = lay.w(c["size"]) > 1.05
            out[f"chunk:{c['addr']}"] = ChunkBlock(
                c, lay, tr.hdr, self.name_fn(c, snap), self.body_fn(c, snap), self.head_fn(c, snap),
                self.role_fn(c, snap), tr.addr(c["addr"]) if (self.addrs and wide) else None)
        if snap["top"]["size"] > 0:
            out["top"] = TopBlock(snap["top"], lay, self.top_label,
                                  tr.addr(snap["top"]["addr"]) if self.addrs else None)
        if self.arrows:
            for b in bin_lists(snap):
                for i in range(len(b.nodes) - 1):
                    src, dst = b.nodes[i], b.nodes[i + 1]
                    out[f"fd:{b.key}:{src}:{dst}:{i}"] = self.arrow(src, dst, b, snap)
        return out

    def arrow(self, src: int, dst: int, b: BinList, snap: dict) -> VMobject:
        lay, tr = self.lay, self.tr
        sc = chunk_at(snap, src)
        a = np.array([lay.x(src + tr.hdr) + min(0.25, lay.w(sc["size"] - tr.hdr) / 3), lay.y + lay.h / 2, 0])
        # tcache and ListHints link user data to user data, fastbins link
        # chunk starts. Aim the tip where the pointer actually lands.
        land = dst if b.kind == "fastbins" else dst + tr.hdr
        tip = np.array([lay.x(land), lay.y + lay.h / 2, 0])
        if src == dst:
            tip = a  # chunk on its own list twice, draw the loop
        m = fd_arc(a, tip, b.role)
        m.sig = ("fd", src, dst, b.key, round(lay.scale, 5))
        return m


def default_body(tr: HeapTrace):
    def body(c, snap):
        if c["allocated"]:
            return None
        b = bin_of(snap, c["addr"])
        fd = c["fd"]
        if tr.win:
            return f"Flink {fd:#x}\nBlink {c['bk']:#x}"
        if b is not None and b.kind in DOUBLY:
            return f"fd {fd:#x}\nbk {c['bk']:#x}"
        return f"fd {fd:#x}"
    return body


def default_head(tr: HeapTrace):
    def head(c, snap):
        if tr.win:
            return f"Size {c['decoded']['sizeUnits']}"
        return f"{c['sizeField']:#x}"
    return head


# -- bins panel ----------------------------------------------------------------

NODE_W, NODE_H = 0.95, 0.46


class BinsPanel:
    """
    One row per free list that shows up anywhere in the trace, so rows never
    jump around. head -> node -> node -> NULL, doubly linked lists get
    two-way arrows.
    """

    def __init__(self, trace: HeapTrace, corner=UR, origin=None, snaps=None, name_fn=None,
                 row_gap: float = 0.62, max_nodes: int = 7, keys=None):
        self.tr = trace
        seen = []
        for s in snaps or trace.snaps():
            for b in bin_lists(s):
                if b.nodes and b.key not in seen:
                    seen.append(b.key)
        self.keys = keys or seen
        self.row_gap = row_gap
        self.max_nodes = max_nodes
        self.origin = np.array(origin if origin is not None else [0.5, 2.85, 0])
        self.name_fn = name_fn or (lambda addr, snap: "/".join(chunk_at(snap, addr)["names"]) or f"{addr:#x}")

    def row_y(self, key: str) -> float:
        return self.origin[1] - self.keys.index(key) * self.row_gap

    def build(self, snap: dict) -> dict:
        out = {}
        lists = {b.key: b for b in bin_lists(snap)}
        for key in self.keys:
            kind, size = key.split(":")
            b = lists.get(key) or BinList(key, kind, int(size), [])
            y = self.row_y(key)
            role = getattr(T, b.role)
            head = mono(b.label, 19, role)
            head.move_to([self.origin[0], y, 0], aligned_edge=LEFT)
            # 2.0 wide label column keeps every row's first node lined up
            x = self.origin[0] + 2.3
            head.sig = ("head", key)
            out[f"head:{key}"] = head
            seen = {}
            shown = b.nodes[:self.max_nodes]
            for i, addr in enumerate(shown):
                n = seen.get(addr, 0)
                seen[addr] = n + 1
                box = RoundedRectangle(NODE_W, NODE_H, corner_radius=0.06)
                box.set_fill(role, 0.18).set_stroke(role, 2)
                box.move_to([x + NODE_W / 2, y, 0])
                lab = fit(mono(self.name_fn(addr, snap), 17, T.text), NODE_W - 0.08, 0.45)
                g = VGroup(box, lab.move_to(box).shift(LIFT)) if lab is not None else VGroup(box)
                g.sig = ("node", key, addr, n, round(x, 2))
                out[f"node:{key}:{addr}:{n}"] = g
                x += NODE_W
                link = self.link(x, y, role, b.kind in DOUBLY)
                link.sig = ("link", key, i)
                out[f"link:{key}:{i}"] = link
                x += 0.34
            if len(b.nodes) > len(shown):
                more = mono(f"+{len(b.nodes) - len(shown)}", 17, role).move_to([x + 0.2, y, 0])
                more.sig = ("more", key, len(b.nodes))
                out[f"more:{key}"] = more
                x += 0.55
            null = mono("NULL" if b.kind not in DOUBLY else "head", 16, T.text_dim)
            null.move_to([x + 0.06, y, 0], aligned_edge=LEFT)
            if not b.nodes:
                # empty list: head points straight at NULL
                null.move_to([self.origin[0] + 2.3, y, 0], aligned_edge=LEFT)
            null.sig = ("null", key, round(null.get_x(), 2))
            out[f"null:{key}"] = null
        return out

    def link(self, x: float, y: float, role: str, doubly: bool) -> VMobject:
        a = Arrow([x + 0.02, y, 0], [x + 0.32, y, 0], buff=0, stroke_width=3, max_tip_length_to_length_ratio=0.45)
        a.set_color(role)
        if not doubly:
            return a
        back = Arrow([x + 0.32, y - 0.08, 0], [x + 0.02, y - 0.08, 0], buff=0, stroke_width=2,
                     max_tip_length_to_length_ratio=0.45).set_color(role).set_opacity(0.6)
        a.shift(UP * 0.06)
        return VGroup(a, back)

    def node_pos(self, key: str, i: int) -> np.ndarray:
        return np.array([self.origin[0] + 2.3 + NODE_W / 2 + i * (NODE_W + 0.34), self.row_y(key), 0])


# -- diffing stage -------------------------------------------------------------

class Stage:
    """
    Holds the keyed mobjects currently on screen and turns a new keyed dict
    into animations. Same key + same sig: left alone. Same key, new sig:
    FadeTransform. New chunk: grows out of the left edge, the way it gets
    carved off top. Gone: fades.
    """

    def __init__(self, scene, fixed: bool = False):
        self.scene = scene
        self.mobs: dict[str, Mobject] = {}
        self.fixed = fixed

    def goto(self, new: dict) -> list[Animation]:
        anims = []
        for key, mob in new.items():
            if self.fixed:
                mob.fix_in_frame()
            old = self.mobs.get(key)
            if old is None:
                if key.startswith("chunk:"):
                    anims.append(GrowFromEdge(mob, LEFT))
                elif key.startswith("fd:"):
                    anims.append(ShowCreation(mob))
                else:
                    anims.append(FadeIn(mob, shift=LEFT * 0.15))
                self.mobs[key] = mob
            elif getattr(old, "sig", None) != getattr(mob, "sig", None):
                anims.append(FadeTransform(old, mob))
                self.mobs[key] = mob
        for key in list(self.mobs):
            if key not in new:
                anims.append(FadeOut(self.mobs.pop(key)))
        return anims

    def get(self, key: str):
        return self.mobs.get(key)

    def group(self, prefix: str = "") -> Group:
        return Group(*(m for k, m in self.mobs.items() if k.startswith(prefix)))

    def clear(self) -> list[Animation]:
        anims = [FadeOut(m) for m in self.mobs.values()]
        self.mobs = {}
        return anims


# -- byte-level chunk ------------------------------------------------------------

class ChunkBytes(VGroup):
    """
    A chunk as byte cells: header bytes, then user bytes, one row, with field
    brackets underneath. `fields` is [(label, start, end, role)] in chunk
    offsets. Cells that aren't written yet show "--".
    """

    def __init__(self, snap: dict, addr: int, n: int, fields: list, trace: HeapTrace,
                 cell_roles: dict | None = None, show_addr: bool = True, glyphs: dict | None = None,
                 values: dict | None = None, mark=()):
        mem, wr = snap["memory"], snap["written"]
        self.addr = addr
        cell_roles = cell_roles or {}
        glyphs, values = glyphs or {}, values or {}
        cells = []
        for i in range(n):
            off = addr + i
            v = mem[off] if off < len(mem) else 0
            known = wr[off] or v
            if i in values:
                # bytes the scene supplies itself (program data the sim never stores)
                v, known = values[i], True
            role = cell_roles.get(i, "cell_fill")
            c = ByteCell(v if known else None, role, glyph=glyphs.get(i))
            if i in mark:
                c.box.set_stroke(T.highlight, 4)
            cells.append(c)
        self.cells = VGroup(*cells)
        # a hair of extra space between 4-byte words so fields read as words
        for i, c in enumerate(self.cells):
            c.shift(RIGHT * (i * (CELL + GAP) + (i // 4) * 0.08))
        self.cells.move_to(ORIGIN)
        self.brackets = VGroup()
        for label, a, b, role in fields:
            if b > n:
                continue
            l, r = self.cells[a].get_corner(DL), self.cells[b - 1].get_corner(DR)
            line = Line(l + DOWN * 0.08 + RIGHT * 0.03, r + DOWN * 0.08 + LEFT * 0.03).set_stroke(getattr(T, role), 4)
            lab = mono(label, 14, getattr(T, role)).next_to(line, DOWN, buff=0.08)
            fit(lab, max(line.get_length() + 0.2, 0.6), 0.5)
            self.brackets.add(VGroup(line, lab))
        parts = [self.cells, self.brackets]
        self.addr_lab = None
        if show_addr:
            self.addr_lab = mono(trace.addr(addr), 14, T.text_dim).next_to(self.cells, LEFT, buff=0.2)
            parts.append(self.addr_lab)
        super().__init__(*parts)

    def update_to(self, snap: dict, cell_roles: dict | None = None) -> list[Animation]:
        """Relabel cells whose byte changed. Returns animations, caller plays."""
        anims = []
        mem, wr = snap["memory"], snap["written"]
        for i, c in enumerate(self.cells):
            off = self.addr + i
            v = mem[off]
            if (wr[off] or v) and c.value != v:
                anims.append(Transform(c.label, c.relabel(v).set_color(T.highlight)))
        if cell_roles:
            for i, role in cell_roles.items():
                anims.append(self.cells[i].box.animate.set_fill(getattr(T, role), 0.85))
        return anims


def ascii_row(bs, color=None) -> VGroup:
    """Bytes as characters under a ChunkBytes row, '.' for anything unprintable."""
    return VGroup(*(mono(chr(b) if 32 <= b < 127 else ".", 16, color or T.text_dim) for b in bs))
