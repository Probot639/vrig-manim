"""
Heap walkthrough traces (tools/vrig-trace/walk_heap-entry.ts) and the
captions in scenes/walk_heap.py. Captions carry hex values and sizes typed
into the scene, so check every one of them against what VRIG computed.
"""
import json
import re

import pytest

from vrig.mob.walk_heap import HeapTrace, bin_lists
from vrig.trace import TRACE_DIR

IDS = ["c-06", "heap-15", "hint-53", "hint-54", "hint-55", "hint-56", "hint-57", "hint-58",
       "whint-59", "whint-60", "whint-61", "whint-62", "adv-87", "adv2-96", "kern-107",
       "glibc-108", "glibc-109", "glibc-110"]


@pytest.fixture(scope="module", params=IDS)
def tr(request):
    return HeapTrace.load(request.param)


def test_trace_loads_and_completes(tr):
    # walkthroughs win by running every step, StepControls fires
    # EXERCISE_COMPLETED on the last one
    assert tr.raw["completed"] and tr.raw["solved"]
    assert len(tr.steps) > 0


def test_glibc_bypass_check_passes():
    for i in ("glibc-108", "glibc-109", "glibc-110"):
        assert HeapTrace.load(i).raw["check"] is True


def test_bins_are_per_step_not_final():
    # regression: getFreeLists() shares its bin arrays, so a naive dump showed
    # the final bins on every step. heap-15 has B on tcache only at step 4.
    t = HeapTrace.load("heap-15")
    heads = [[b.nodes for b in bin_lists(s) if b.kind == "tcache"] for s in t.steps]
    assert heads[3] == [[0]]
    assert heads[4] == [[24, 0]]
    assert heads[5] == [[0]]


def test_chunks_tile_the_heap(tr):
    # chunks + top cover the heap with no gaps. glibc-110's freeC extra is the
    # one place they overlap, on purpose, so it isn't in steps.
    for s in tr.snaps():
        end = 0
        for c in s["chunks"]:
            if c["addr"] < end:
                continue
            assert c["addr"] == end, (tr.id, c["addr"], end)
            end = c["addr"] + c["size"]
        if not tr.win or s["top"]["size"]:
            assert s["top"]["addr"] >= end


def test_extras():
    p = HeapTrace.load("glibc-108").extra["doubleFreeProbe"]
    assert p["returned"] is False and p["memoryUnchanged"]
    assert "double free" in p["lastError"]
    x = HeapTrace.load("glibc-110").extra["freeC"]
    a = next(c for c in x["chunks"] if "A" in c["names"])
    b = next(c for c in x["chunks"] if "B" in c["names"])
    assert not a["allocated"] and b["allocated"]
    assert a["addr"] <= b["addr"] < a["addr"] + a["size"], "merged chunk should cover live B"
    w = HeapTrace.load("whint-60").extra
    assert w["lfhInExerciseHeap"] is False
    assert any(c["lfh"] for c in w["bigHeap"]["steps"][6]["chunks"])
    k = HeapTrace.load("kern-107").extra["slab"]
    assert k["sameAddr"]
    assert HeapTrace.load("whint-62").extra["corrupt"]["validAfter"] is False


def trace_numbers(raw) -> set[int]:
    nums = set()

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, int):
            nums.add(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list) and not (len(o) > 64 and all(isinstance(x, int) for x in o)):
            for v in o:
                walk(v)
    walk(raw)
    return nums


def scene_captions():
    # scenes/ isn't a package and tests/scenes.py would shadow it anyway
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parent.parent / "scenes" / "walk_heap.py"
    spec = importlib.util.spec_from_file_location("walk_heap_scenes", path)
    wh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wh)
    out = {}
    for name in dir(wh):
        cls = getattr(wh, name)
        if isinstance(cls, type) and issubclass(cls, wh.HeapWalk) and getattr(cls, "trace_id", ""):
            out[cls.trace_id] = (cls, list(cls.captions.values()) + [cls.subtitle, cls.outro])
    return out


def test_every_exercise_has_a_scene():
    assert set(scene_captions()) == set(IDS)


@pytest.mark.parametrize("tid", IDS)
def test_caption_hex_values_come_from_trace(tid):
    cls, caps = scene_captions()[tid]
    raw = json.loads((TRACE_DIR / f"{tid}.json").read_text())
    nums = trace_numbers(raw)
    # derived values the captions use: flag-or'd sizes and chunk sizes
    for n in list(nums):
        if n < 0x10000:
            nums |= {n | 4, n & ~7}
    for cap in caps:
        for h in re.findall(r"0x[0-9a-fA-F]+", cap):
            assert int(h, 16) in nums, f"{tid}: {h} in {cap!r} isn't in the trace"


@pytest.mark.parametrize("tid", IDS)
def test_caption_byte_sizes_come_from_trace(tid):
    cls, caps = scene_captions()[tid]
    t = HeapTrace.load(tid)
    sizes = {t.heap_size}
    for s in t.snaps():
        for c in s["chunks"]:
            sizes |= {c["size"], c["size"] - t.hdr}
    for s in t.steps:
        if s["size"]:
            sizes.add(s["size"])
    sizes |= {8, t.hdr}
    for cap in caps:
        for m in re.findall(r"(?<![0-9a-fA-Fx])(\d[\d,]*)-byte|(?<![0-9a-fA-Fx])(\d[\d,]*) bytes", cap):
            n = int((m[0] or m[1]).replace(",", ""))
            assert n in sizes, f"{tid}: {n} bytes in {cap!r} isn't a size VRIG produced"
