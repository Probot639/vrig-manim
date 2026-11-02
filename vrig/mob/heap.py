"""
The glibc heap as VRIG's HeapSim sees it, drawn from traces written by
tools/vrig-trace/heap-entry.ts.

Same rule as memory.py: low addresses at the bottom. One row is 8 bytes, so a
chunk header (prev_size, size) is exactly one row and a 24-byte chunk is three.
Freed chunks show their links in place ("fd 00000020") and the side panel walks
the same pointers out of memory, so a poisoned fd shows up in both.

Views are rebuilt from scratch for every state and swapped in with
`morph(old, new)`, which pairs pieces up by key (a word's heap offset, a
chunk's address, a bin's name) and only animates what changed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from manimlib import *

from vrig.mob.memory import LIFT, _luma, mono, prose
from vrig.theme import T

TRACE_DIR = Path(__file__).parent.parent.parent / "traces"


def h32(v: int) -> str:
    return f"0x{v & 0xffffffff:08x}"


# -- trace -------------------------------------------------------------------

class HeapTrace:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["exercise"]
        self.title = raw["title"]
        self.mode = raw["mode"]
        self.base = raw["base"]
        self.H = raw["header"]
        self.size = raw["heapSize"]
        self.symbols = raw["symbols"]
        self.fp_addr = raw["funcPtrAddr"]
        self.main_arena = raw["mainArena"]
        self.source = raw["source"]
        self.ops = raw["ops"]
        self.payloads = raw["payloads"]
        self.solved = raw["solved"]
        self._attacker = self._attacker_bytes()
        self._heads = self._bin_heads()

    @classmethod
    def load(cls, name: str) -> "HeapTrace":
        with open(TRACE_DIR / f"{name}.json") as f:
            return cls(json.load(f))

    def find(self, group: str | None = None, op: str | None = None, nth: int = 0, after: int = -1) -> int:
        hits = [i for i, o in enumerate(self.ops)
                if i > after and (group is None or o["group"] == group) and (op is None or o["op"] == op)]
        if nth >= len(hits):
            raise KeyError(f"{self.id}: no op group={group} op={op} nth={nth}")
        return hits[nth]

    def state(self, i: int) -> dict:
        return self.ops[i]["state"]

    def sym_name(self, v: int) -> str | None:
        for k, a in self.symbols.items():
            if a == v:
                return k
        return None

    def attacker(self, i: int) -> set[int]:
        return self._attacker[i]

    def _attacker_bytes(self) -> list[set[int]]:
        # bytes a payload put there and nothing has rewritten since
        out, mine = [], {}
        for o in self.ops:
            if o["op"] == "write":
                off, data = o["args"]
                for k, b in enumerate(data):
                    mine[off + k] = b
            mem = o["state"]["memory"]
            out.append({a for a, b in mine.items() if a < len(mem) and mem[a] == b})
        return out

    def _bin_heads(self) -> list[dict]:
        """
        Where each tcache/fastbin head points after each op. VRIG keeps bins as
        JS arrays, so once malloc pops a chunk whose fd was poisoned, the array
        is just empty. glibc would load the popped chunk's fd into the head,
        and VRIG's own log says the next malloc "follows the poisoned fd". So
        when the array empties that way, carry the fd forward as the head.
        """
        heads, carried = [], {}
        prev = None
        for o in self.ops:
            st = o["state"]
            cur = {}
            for kind in ("tcache", "fastbins"):
                for size, arr in st["bins"][kind].items():
                    cur[(kind, size)] = ("chunk", arr[-1])
            if prev is not None:
                for kind in ("tcache", "fastbins"):
                    for size, arr in prev["bins"][kind].items():
                        key = (kind, size)
                        now = st["bins"][kind].get(size, [])
                        if len(now) >= len(arr):
                            continue
                        popped = arr[-1]
                        fd = _le(st["memory"], popped + self.H)
                        if not fd:
                            continue
                        dst = self.resolve(fd)
                        if dst is None:
                            carried[key] = ("ext", fd)
                        else:
                            ch = self.chunk_at(dst, st)
                            carried[key] = ("chunk", ch["addr"] if ch else dst)
            for key in list(carried):
                if key in cur and cur[key] == carried[key]:
                    del carried[key]
                elif o["op"] == "malloc" and prev is not None and key not in self._keys(prev):
                    # the malloc after the carry is the one that took it
                    del carried[key]
            heads.append({**cur, **carried})
            prev = st
        return heads

    def _keys(self, st):
        return {(k, s) for k in ("tcache", "fastbins") for s in st["bins"][k]}

    def heads(self, i: int) -> dict:
        return self._heads[i]

    def resolve(self, ptr: int, st: dict | None = None) -> int | None:
        """A pointer as stored in memory -> heap offset, or None if it's off-heap.
        VRIG mixes conventions: tcache fd is offset+8, fastbin fd is the chunk
        offset, the finals print base+offset. Accept all three."""
        if ptr == 0:
            return None
        if self.base <= ptr < self.base + self.size:
            return ptr - self.base
        if ptr < self.size:
            return ptr
        return None

    def chunk_at(self, off: int, st: dict) -> dict | None:
        for c in st["chunks"]:
            if c["addr"] <= off < c["addr"] + c["size"]:
                return c
        return None


def _le(mem, off, n=4) -> int:
    return int.from_bytes(bytes(mem[off:off + n]), "little")


# -- drawing helpers ---------------------------------------------------------

def link(a, b, bulge: float = 0.6, color: str | None = None, width: float = 3, tip: float = 0.13) -> VGroup:
    """Side-bulging parabola from a to b with a tip. Parabola for the same reason
    as arc3d: cubic beziers with near-180 joints spike."""
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = b - a
    n = np.array([d[1], -d[0], 0.0])
    if np.linalg.norm(n) < 1e-6:
        n = RIGHT
    n = n / np.linalg.norm(n)
    curve = ParametricCurve(lambda t: a + d * t + n * bulge * 4 * t * (1 - t), t_range=(0, 1, 0.02))
    curve.set_stroke(color or T.pointer, width)
    end_dir = d - n * bulge * 4
    ang = np.arctan2(end_dir[1], end_dir[0])
    head = Triangle().set_height(tip).rotate(ang - PI / 2)
    head.set_fill(color or T.pointer, 1).set_stroke(width=0).move_to(b - end_dir / np.linalg.norm(end_dir) * tip * 0.4)
    return VGroup(curve, head)


def _ink(fill: str) -> str:
    return T.background if _luma(fill) > 0.55 else T.text


@dataclass
class HeapCfg:
    row: float = 0.34
    cell_w: float = 1.3
    font: int = 13
    x: float = -1.0          # center of the two word cells
    y0: float = -2.4         # bottom of the lowest row
    fold: int = 4            # data rows past this get folded
    mini: set = field(default_factory=set)     # chunk names drawn as one row
    labels: dict = field(default_factory=dict)  # VRIG name -> on-screen name
    hide_names: bool = False
    show_top: bool = True
    top_label: str = "top chunk  {size} B free"
    top_header: bool = True
    fmt: object = h32         # address -> label


def rows_needed(tr: HeapTrace, i: int, cfg: "HeapCfg") -> float:
    st = tr.state(i)
    names = {v: cfg.labels.get(k, k) for k, v in st["names"].items()}
    n = 0.0
    for ch in st["chunks"]:
        if names.get(ch["addr"]) in cfg.mini:
            n += 1
            continue
        rows = ch["size"] // 8
        n += 4 if rows - 1 > cfg.fold else rows
    if cfg.show_top and st["top"]["size"] > 0:
        n += 2.3
    return n


def fit(tr: HeapTrace, cfg: "HeapCfg", ops=None, avail: float = 5.6, top: float = 3.0,
        center: float = 0.15) -> "HeapCfg":
    """Pick one row height for the whole video from the tallest state, so
    nothing jumps between beats, and hang the column from `top`."""
    ops = range(len(tr.ops)) if ops is None else ops
    most = max(rows_needed(tr, i, cfg) for i in ops)
    cfg.row = min(0.6, avail / most)
    cfg.font = int(min(17, max(11, 13 + (cfg.row - 0.34) * 18)))
    cfg.cell_w = 1.3 * max(1.0, cfg.font / 13)
    cfg.y0 = min(top, center + most * cfg.row / 2) - most * cfg.row
    return cfg


class HeapView(VGroup):
    """One heap state. `parts` maps a stable key to each piece for morph()."""

    def __init__(self, tr: HeapTrace, i: int, cfg: HeapCfg, roles: dict | None = None):
        super().__init__()
        self.tr, self.i, self.cfg = tr, i, cfg
        st = tr.state(i)
        self.st = st
        self.parts: dict = {}
        self.anchor: dict = {}       # heap offset -> point on the right edge of that word's row
        self.row_y: dict = {}
        self.roles = roles or {}     # word offset -> forced role
        atk = tr.attacker(i)
        names = {}
        for k, v in st["names"].items():
            if k != "y_target":
                shown_k = cfg.labels.get(k, k)
                if shown_k and shown_k not in names.get(v, []):
                    names.setdefault(v, []).append(shown_k)
        names = {v: ", ".join(ks) for v, ks in names.items()}
        binned = self._bin_roles(st)
        c = cfg
        y = c.y0
        mem, written = st["memory"], st["written"]

        for ch in st["chunks"]:
            shown = names.get(ch["addr"])
            if shown in c.mini:
                y = self._mini(ch, shown, y)
                continue
            rows = ch["size"] // 8
            data_rows = rows - 1
            visible = list(range(rows))
            folded = None
            if data_rows > c.fold:
                visible = [0, 1, 2]
                folded = (3, rows)
            top_y = y
            for r in visible:
                self._row(ch, r, y, mem, written, atk, binned)
                y += c.row
            if folded:
                hidden = (folded[1] - folded[0]) * 8
                box = Rectangle(2 * c.cell_w + 0.04, c.row * 0.86).set_stroke(T.grid, 1)
                fill = T.chunk_user if ch["allocated"] else T.freed_chunk
                box.set_fill(fill, 0.35).move_to([c.x, y + c.row / 2, 0])
                txt = mono(f"... {hidden} more bytes", c.font - 1, T.text_dim).move_to(box).shift(LIFT)
                self._put(("fold", ch["addr"]), box)
                self._put(("foldtxt", ch["addr"]), txt, f"{hidden}")
                y += c.row
            self._frame(ch, top_y, y, shown)
        self.top_y = y
        if c.show_top and st["top"]["size"] > 0:
            self._top(st["top"], y, mem, written, atk)

    # ---- pieces

    def _put(self, key, mob, sig: str = ""):
        mob.vrig_sig = sig
        self.parts[key] = mob
        self.add(mob)

    def _bin_roles(self, st) -> dict:
        roles = {}
        for kind, role in (("tcache", "tcache"), ("fastbins", "fastbin")):
            for arr in st["bins"][kind].values():
                for a in arr:
                    roles[a] = (role, 1)
        for arr in [st["bins"]["unsorted"], *st["bins"]["smallbins"].values(), *st["bins"]["largebins"].values()]:
            for a in arr:
                roles[a] = ("unsorted", 2)
        return roles

    def _row(self, ch, r, y, mem, written, atk, binned):
        c = self.cfg
        for k in range(2):
            off = ch["addr"] + r * 8 + k * 4
            val = _le(mem, off)
            touched = any(written[off:off + 4])
            mine = any((off + j) in atk for j in range(4))
            if r == 0:
                role = "chunk_header"
                txt = ("prev " if k == 0 else "size ") + f"{val:x}"
            else:
                role = "chunk_user" if ch["allocated"] else "freed_chunk"
                txt = f"{val:08x}"
                if not ch["allocated"] and r == 1 and ch["addr"] in binned:
                    brole, nlinks = binned[ch["addr"]]
                    if k < nlinks:
                        role = brole
                        txt = ("fd " if k == 0 else "bk ") + txt
            if mine:
                role = "attacker_bytes"
            role = self.roles.get(off, role)
            fill = getattr(T, role)
            box = Rectangle(c.cell_w, c.row * 0.86).set_stroke(T.grid, 1)
            box.set_fill(fill, 0.85 if role != "freed_chunk" else 0.55)
            box.move_to([c.x + (k - 0.5) * (c.cell_w + 0.04), y + c.row / 2, 0])
            # VRIG's setup pokes values in without marking them written, so
            # treat any nonzero word as live too
            live = touched or val != 0 or r == 0
            ink = _ink(fill)
            t = mono(txt, c.font, ink).move_to(box).shift(LIFT)
            if not live:
                t.set_opacity(0.35)
                ink += "-"
            self._put(("cell", off), box, role)
            self._put(("txt", off), t, txt + ink)
            self.anchor[off] = box.get_right()
            self.row_y[off] = y + c.row / 2

    def _frame(self, ch, y_lo, y_hi, shown):
        c = self.cfg
        role = "chunk_user" if ch["allocated"] else "freed_chunk"
        w = 2 * c.cell_w + 0.04 + 0.08
        fr = Rectangle(w, y_hi - y_lo - c.row * 0.14 + 0.06).set_stroke(getattr(T, role), 2.5).set_fill(opacity=0)
        fr.move_to([c.x, (y_lo + y_hi) / 2 - c.row * 0.07, 0])
        self._put(("frame", ch["addr"]), fr, role)
        left = c.x - w / 2 - 0.12
        a = mono(c.fmt(self.tr.base + ch["addr"]), c.font, T.text_dim)
        a.move_to([left, y_lo + c.row / 2, 0], aligned_edge=RIGHT)
        self._put(("addr", ch["addr"]), a, h32(ch["addr"]))
        size = mono(f"{ch['size']} B", c.font - 1, T.text_dim).next_to(a, UP, buff=0.06, aligned_edge=RIGHT)
        if y_hi - y_lo > c.row * 1.5:
            self._put(("sz", ch["addr"]), size, f"{ch['size']}")
        if shown and not c.hide_names:
            n = prose(shown, c.font + 5, T.label if ch["allocated"] else T.text_dim)
            n.next_to(a, LEFT, buff=0.2)
            self._put(("name", ch["addr"]), n, shown + str(ch["allocated"]))
        self.anchor[("chunk", ch["addr"])] = fr.get_right()
        self.anchor[("chunk_l", ch["addr"])] = fr.get_left()
        self.anchor[("chunk_y", ch["addr"])] = (y_lo, y_hi)

    def _mini(self, ch, shown, y):
        c = self.cfg
        role = "chunk_user" if ch["allocated"] else "tcache"
        for arr in self.st["bins"]["fastbins"].values():
            if ch["addr"] in arr:
                role = "fastbin"
        box = Rectangle(2 * c.cell_w + 0.04, c.row * 0.86).set_stroke(T.grid, 1)
        box.set_fill(getattr(T, role), 0.85 if role != "chunk_user" else 0.55).move_to([c.x, y + c.row / 2, 0])
        state = "in use" if ch["allocated"] else "free"
        t = mono(f"{shown}  {ch['size']} B  {state}", c.font - 1, _ink(getattr(T, role))).move_to(box).shift(LIFT)
        self._put(("mini", ch["addr"]), box, role)
        self._put(("minitxt", ch["addr"]), t, t.text if hasattr(t, "text") else state)
        a = mono(c.fmt(self.tr.base + ch["addr"]), c.font - 1, T.text_dim)
        a.move_to([c.x - c.cell_w - 0.2, y + c.row / 2, 0], aligned_edge=RIGHT)
        self._put(("addr", ch["addr"]), a, "")
        self.anchor[("chunk", ch["addr"])] = box.get_right()
        self.anchor[("chunk_l", ch["addr"])] = box.get_left()
        self.anchor[("chunk_y", ch["addr"])] = (y, y + c.row)
        self.anchor[ch["addr"] + 8] = box.get_right()
        self.row_y[ch["addr"] + 8] = y + c.row / 2
        return y + c.row

    def _top(self, top, y, mem, written, atk):
        c = self.cfg
        addr = top["addr"]
        for k in range(2 if c.top_header else 0):
            off = addr + k * 4
            val = _le(mem, off) if off + 4 <= len(mem) else 0
            mine = any((off + j) in atk for j in range(4))
            role = "attacker_bytes" if mine else "chunk_header"
            box = Rectangle(c.cell_w, c.row * 0.86).set_stroke(T.grid, 1).set_fill(getattr(T, role), 0.85)
            box.move_to([c.x + (k - 0.5) * (c.cell_w + 0.04), y + c.row / 2, 0])
            # VRIG doesn't keep the top's size in memory until something writes
            # it, so show the field from memory and the real size in the body
            txt = ("prev " if k == 0 else "size ") + f"{val:x}"
            t = mono(txt, c.font, _ink(getattr(T, role))).move_to(box).shift(LIFT)
            self._put(("cell", off), box, role)
            self._put(("txt", off), t, txt + role)
            self.anchor[off] = box.get_right()
        body = Rectangle(2 * c.cell_w + 0.04, c.row * 1.3).set_stroke(T.top_chunk, 1.5)
        lift = c.row if c.top_header else 0.0
        body.set_fill(T.top_chunk, 0.45).move_to([c.x, y + lift + c.row * 0.65, 0])
        bt = mono(c.top_label.format(size=top["size"]), c.font, T.text).move_to(body).shift(LIFT)
        self._put(("top",), body, "")
        self._put(("toptxt",), bt, str(top["size"]))
        a = mono(c.fmt(self.tr.base + addr), c.font, T.text_dim)
        a.move_to([c.x - c.cell_w - 0.2, y + c.row / 2, 0], aligned_edge=RIGHT)
        self._put(("topaddr",), a, h32(addr))
        self.anchor[("top",)] = body.get_right()
        self.anchor[("chunk_y", "top")] = (y, y + c.row * 2.3)

    # ---- links drawn on the heap itself

    def fd_links(self, color_for=None) -> VGroup:
        """Arrows from each freed chunk's fd word to the chunk it names, when
        that chunk is on the heap. Added to parts so morph() sees them."""
        tr, st = self.tr, self.st
        out = VGroup()
        for ch in st["chunks"]:
            if ch["allocated"]:
                continue
            fdoff = ch["addr"] + tr.H
            if fdoff not in self.anchor:
                continue
            fd = _le(st["memory"], fdoff)
            dst = tr.resolve(fd)
            if dst is None:
                continue
            tgt = tr.chunk_at(dst, st)
            if tgt is None or ("chunk", tgt["addr"]) not in self.anchor:
                continue
            a = self.anchor[fdoff] + RIGHT * 0.05
            lo, hi = self.anchor[("chunk_y", tgt["addr"])]
            b = np.array([self.anchor[("chunk", tgt["addr"])][0] + 0.05, (lo + hi) / 2, 0])
            role = self._link_role(ch["addr"])
            if tgt["addr"] == ch["addr"]:
                # a chunk whose fd names itself, the tcache double free
                loop = Arc(start_angle=-PI / 2, angle=PI * 1.6, radius=c_r(self.cfg))
                loop.set_stroke(getattr(T, role), 3).move_to(a + RIGHT * c_r(self.cfg))
                arr = VGroup(loop)
            else:
                bulge = 0.35 + 0.12 * abs(lo - self.row_y.get(fdoff, lo))
                arr = link(a, b, bulge=-min(bulge, 1.4), color=getattr(T, role))
            self._put(("fd", ch["addr"], dst), arr, role)
            out.add(arr)
        return out

    def _link_role(self, addr):
        st = self.st
        for arr in st["bins"]["tcache"].values():
            if addr in arr:
                return "tcache"
        for arr in st["bins"]["fastbins"].values():
            if addr in arr:
                return "fastbin"
        return "unsorted"

    def word_point(self, off: int):
        return self.anchor[off]


def c_r(cfg):
    return cfg.row * 0.6


# -- the side panel: bins as linked lists, and the function pointers ----------

class BinPanel(VGroup):
    """
    Every non-empty bin as a vertical list, head at the top. Links are walked
    out of heap memory, so whatever a payload wrote into an fd is what the
    list shows next. Off-heap nodes are drawn in the attacker's color.
    """

    def __init__(self, tr: HeapTrace, i: int, x: float = 4.4, y: float = 2.2, col_w: float = 2.4,
                 node_w: float = 1.75, node_h: float = 0.4, font: int = 15, max_nodes: int = 4,
                 notes: dict | None = None, labels: dict | None = None, fmt=h32):
        super().__init__()
        self.fmt = fmt
        self.tr, self.i = tr, i
        self.labels = labels or {}
        self.parts = {}
        self.node_pt = {}
        st = tr.state(i)
        heads = tr.heads(i)
        self.font, self.node_w, self.node_h = font, node_w, node_h
        notes = notes or {}
        cols = []
        for kind, role, label in (("tcache", "tcache", "tcache"), ("fastbins", "fastbin", "fastbin")):
            sizes = sorted({*st["bins"][kind].keys(), *(s for (k, s) in heads if k == kind)}, key=int)
            for size in sizes:
                head = heads.get((kind, size))
                if head is None:
                    continue
                cols.append((kind, size, role, f"{label}[{size}]", self._walk_single(st, head, kind)))
        for kind, label in (("unsorted", "unsorted"), ("smallbins", "smallbin")):
            lists = [("", st["bins"]["unsorted"])] if kind == "unsorted" else list(st["bins"][kind].items())
            for size, arr in lists:
                if arr:
                    cols.append((kind, size, "unsorted", f"{label}[{size}]" if size else label, [("chunk", a) for a in reversed(arr)]))
        self.cols = cols
        for ci, (kind, size, role, label, nodes) in enumerate(cols):
            cx = x + (ci - (len(cols) - 1) / 2) * col_w
            self._column(st, ci, kind, size, role, label, nodes, cx, y, max_nodes, notes)

    def _put(self, key, mob, sig=""):
        mob.vrig_sig = sig
        self.parts[key] = mob
        self.add(mob)

    def _walk_single(self, st, head, kind):
        tr = self.tr
        nodes, seen = [], []
        cur = head
        for _ in range(9):
            if cur[0] == "ext":
                nodes.append(cur)
                break
            addr = cur[1]
            if addr in seen:
                nodes.append(("cycle", addr))
                break
            seen.append(addr)
            nodes.append(cur)
            fd = _le(st["memory"], addr + tr.H)
            dst = tr.resolve(fd)
            if fd == 0:
                break
            if dst is None:
                cur = ("ext", fd)
                continue
            # tcache stores the user pointer, fastbin the chunk. Either way
            # land on the chunk that contains it
            ch = tr.chunk_at(dst, st)
            cur = ("chunk", ch["addr"] if ch else dst)
        return nodes

    def _label_for(self, node):
        tr = self.tr
        kind, v = node
        if kind == "ext":
            return h32(v)
        return self.fmt(tr.base + v)

    def _column(self, st, ci, kind, size, role, label, nodes, cx, y, max_nodes, notes):
        tr = self.tr
        color = getattr(T, role)
        lab = mono(label, self.font + 2, color).move_to([cx, y, 0])
        self._put(("binlab", kind, size), lab, label)
        head = Rectangle(self.node_w * 0.7, self.node_h * 0.9).set_stroke(color, 2).set_fill(color, 0.2)
        head.next_to(lab, DOWN, buff=0.12)
        ht = mono("head", self.font, color).move_to(head).shift(LIFT)
        self._put(("binhead", kind, size), head, "")
        self._put(("binheadt", kind, size), ht, "")
        prev = head
        shown = nodes
        extra = 0
        if len(nodes) > max_nodes:
            shown = nodes[:max_nodes - 1]
            extra = len(nodes) - len(shown)
        for k, node in enumerate(shown):
            nk, v = node
            if nk == "cycle":
                # point back up at the earlier node with the same address
                first = next(j for j, n in enumerate(shown) if n == ("chunk", v))
                tgt = self.parts[("node", kind, size, first)]
                if tgt is prev:
                    # fd names the node itself: a loop off its right side
                    r = self.node_h * 0.45
                    arr = Arc(start_angle=PI * 0.8, angle=-PI * 1.6, radius=r).set_stroke(T.crash, 3)
                    arr.move_to(prev.get_right() + RIGHT * r * 0.9)
                    tipm = Triangle().set_height(0.12).rotate(PI / 2).set_fill(T.crash, 1).set_stroke(width=0)
                    tipm.move_to(prev.get_right() + UP * r * 0.55 + RIGHT * 0.04)
                    arr = VGroup(arr, tipm)
                else:
                    a = prev.get_right() + RIGHT * 0.03
                    b = tgt.get_right() + RIGHT * 0.03
                    arr = link(a, b, bulge=-0.45, color=T.crash)
                self._put(("cyc", kind, size, k), arr, f"{v}")
                tag = mono("cycle", self.font - 1, T.crash).next_to(arr, RIGHT, buff=0.08)
                self._put(("cyct", kind, size, k), tag, "")
                break
            ext = nk == "ext"
            ncolor = T.attacker_bytes if ext else color
            box = Rectangle(self.node_w, self.node_h).set_stroke(ncolor, 2).set_fill(ncolor, 0.85 if ext else 0.25)
            box.next_to(prev, DOWN, buff=0.28)
            t = mono(self._label_for(node), self.font, _ink(ncolor) if ext else T.text).move_to(box).shift(LIFT)
            nm = self._name(st, node, notes)
            self._put(("node", kind, size, k), box, f"{node}")
            self._put(("nodet", kind, size, k), t, f"{node}{ext}")
            if nm:
                n = mono(nm, self.font - 1, ncolor if ext else T.label).next_to(box, RIGHT, buff=0.1)
                self._put(("noden", kind, size, k), n, nm)
            ar = Arrow(prev.get_bottom(), box.get_top(), buff=0.03, thickness=2.2).set_fill(ncolor if ext else color)
            self._put(("nodea", kind, size, k), ar, f"{ext}")
            self.node_pt[node] = box
            prev = box
        else:
            if extra:
                more = mono(f"+ {extra} more", self.font - 1, T.text_dim).next_to(prev, DOWN, buff=0.18)
                self._put(("more", kind, size), more, str(extra))
                prev = more
            elif kind in ("tcache", "fastbins") and shown and shown[-1][0] != "ext":
                null = mono("NULL", self.font, T.text_dim).next_to(prev, DOWN, buff=0.28)
                ar = Arrow(prev.get_bottom(), null.get_top(), buff=0.03, thickness=2.2).set_fill(T.text_dim)
                self._put(("null", kind, size), null, "")
                self._put(("nulla", kind, size), ar, "")
        if kind in ("unsorted", "smallbins"):
            self._doubly(st, kind, size, nodes, head, notes)

    def _doubly(self, st, kind, size, nodes, head, notes):
        # fd and bk as words under each node, bk pointing at wherever it says
        tr = self.tr
        for k, (nk, v) in enumerate(nodes):
            box = self.parts.get(("node", kind, size, k))
            if box is None:
                continue
            fd = _le(st["memory"], v + tr.H)
            bk = _le(st["memory"], v + tr.H + 4)
            rows = VGroup(mono(f"fd {fd:08x}", self.font - 1, T.label), mono(f"bk {bk:08x}", self.font - 1, T.label))
            rows.arrange(DOWN, buff=0.06, aligned_edge=LEFT).next_to(box, DOWN, buff=0.12)
            self._put(("dl", kind, size, k), rows, f"{fd}{bk}")
            if bk == tr.main_arena:
                tgt_text = "main_arena"
                c = T.label
            else:
                tgt_text = notes.get(bk, h32(bk))
                c = T.attacker_bytes
            dest = Rectangle(self.node_w, self.node_h).set_stroke(c, 2).set_fill(c, 0.85 if c == T.attacker_bytes else 0.15)
            dest.next_to(rows, DOWN, buff=0.35)
            dt = mono(tgt_text if bk == tr.main_arena else h32(bk), self.font, _ink(c) if c == T.attacker_bytes else T.label)
            dt.move_to(dest).shift(LIFT)
            ar = Arrow(rows[1].get_bottom(), dest.get_top(), buff=0.03, thickness=2.2).set_fill(c)
            self._put(("bkbox", kind, size, k), dest, f"{bk}")
            self._put(("bkt", kind, size, k), dt, f"{bk}")
            self._put(("bka", kind, size, k), ar, f"{bk}")
            if bk != tr.main_arena and bk in notes:
                n = mono(notes[bk], self.font - 1, c).next_to(dest, DOWN, buff=0.08)
                self._put(("bkn", kind, size, k), n, notes[bk])
            self.node_pt[("bk", kind, size, k)] = dest

    def _name(self, st, node, notes):
        nk, v = node
        if nk == "ext":
            return notes.get(v, "")
        for n, a in st["names"].items():
            if a == v and n != "y_target":
                return self.labels.get(n, n)
        return ""


class FuncPtrPanel(VGroup):
    """The function pointers VRIG tracks (heap.funcPtrs), with what they point at."""

    def __init__(self, tr: HeapTrace, i: int, labels: dict | None = None, font: int = 17,
                 addr: dict | None = None):
        super().__init__()
        self.parts = {}
        st = tr.state(i)
        labels = labels or {}
        addr = addr or {}
        rows = VGroup()
        for name, fp in st["funcPtrs"].items():
            cur = fp["current"]
            sym = tr.sym_name(cur)
            if cur == tr.main_arena:
                sym = "main_arena"
            hijacked = cur != fp["original"]
            color = (T.win if sym == "win" else T.attacker_bytes) if hijacked else T.text
            where = addr.get(name)
            parts = [mono(labels.get(name, f"{name}()"), font, T.label)]
            if where is not None:
                parts.append(mono(f"@ {h32(where)}", font - 1, T.text_dim))
            parts += [mono(f"{cur:08x}", font, color), mono(sym + "()" if sym and sym != "main_arena" else (sym or "??"), font, color)]
            row = VGroup(*parts).arrange(RIGHT, buff=0.22)
            row.vrig_sig = f"{cur}"
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        self.rows = rows
        if len(rows):
            bg = SurroundingRectangle(rows, buff=0.16).set_stroke(T.grid, 1.5).set_fill(T.cell_fill, 0.9).shift(-LIFT)
            bg.vrig_sig = f"{len(rows)}"
            # bg first: parts get added in dict order and it would cover the text
            self.parts[("fpbg",)] = bg
            for name, row in zip(st["funcPtrs"], rows):
                self.parts[("fp", name)] = row
            self.add(bg, rows)
        self.bg = bg if len(rows) else None

    def place(self, point, edge=UR):
        if self.bg is not None:
            shift = point - self.bg.get_corner(edge)
            for m in self.parts.values():
                m.shift(shift)
        return self


# -- swapping one view for the next --------------------------------------------

def morph(old: dict, new: dict, create: tuple = ("fd", "cyc", "nodea", "bka", "nulla")) -> list[Animation]:
    """Pair pieces by key. Same text: Transform (moves, recolors). New text:
    cross-fade in place, glyph morphs between hex strings read as noise.
    Links that appear get drawn on."""
    anims = []
    for k in old.keys() | new.keys():
        o, n = old.get(k), new.get(k)
        kind = k[1] if len(k) > 1 and k[0] in ("h", "b", "f") else k[0]
        if o is not None and n is not None:
            if isinstance(n, Text) or isinstance(n, VGroup) and any(isinstance(s, Text) for s in n.submobjects):
                if getattr(o, "vrig_sig", "") == getattr(n, "vrig_sig", "") and np.allclose(o.get_center(), n.get_center(), atol=0.02):
                    anims.append(Transform(o, n))
                else:
                    anims += [FadeOut(o), FadeIn(n)]
            elif kind in create and getattr(o, "vrig_sig", "") != getattr(n, "vrig_sig", ""):
                anims += [FadeOut(o), ShowCreation(n) if not isinstance(n, Arrow) else GrowArrow(n)]
            else:
                anims.append(Transform(o, n))
        elif n is not None:
            if kind in create:
                anims.append(GrowArrow(n) if isinstance(n, Arrow) else ShowCreation(n))
            else:
                anims.append(FadeIn(n))
        else:
            anims.append(FadeOut(o))
    return anims
