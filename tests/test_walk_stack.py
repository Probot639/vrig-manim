"""Traces for the guided step lessons (tools/vrig-trace/walk_stack-entry.ts)."""
import json
from pathlib import Path

import pytest


def _scenes():
    # tests/scenes.py shadows the scenes/ dir, so load the file directly
    import importlib.util
    path = Path(__file__).parent.parent / "scenes" / "walk_stack.py"
    spec = importlib.util.spec_from_file_location("walk_stack_scenes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

from vrig.mob.walk_stack import TRACE_DIR, WalkTrace

IDS = ["rit-00", "rit-01", "c-01", "c-02", "c-03", "c-04", "c-05", "c-07", "c-08", "stack-01",
       "mit-80", "mit-82", "mit-84", "mit-85", "kern-106", "gap-111", "gap-112", "gap-114", "gap-115"]
# these four have check: () => true. The rest return false and only complete.
CHECK_TRUE = {"gap-111", "gap-112", "gap-114", "gap-115"}


@pytest.mark.parametrize("ex", IDS)
def test_trace_loads(ex):
    tr = WalkTrace.load(ex)
    assert tr.id == ex
    assert tr.raw["completed"]
    assert tr.raw["checkResult"] == (ex in CHECK_TRUE)
    for st in tr.steps:
        assert len(st["memory"]) == tr.total
        if st["hl"]:
            assert st["hl"][0] < st["hl"][1]


def test_gap111_stage3_holds():
    t = json.loads((TRACE_DIR / "gap-111.json").read_text())
    s3 = t["stage3"]
    assert s3["solved"] and s3["canaryIntact"]
    assert s3["retAddr"] == t["symbols"]["system"]
    # the pinned seed is picked so libc doesn't wrap under 4G. A wrapped
    # system() at 0x0387e200 is what the first seed gave.
    assert t["symbols"]["system"] >= 0xf0000000


def test_gap114_brute_force_hits_once():
    p = json.loads((TRACE_DIR / "gap-114.json").read_text())["partial"]
    assert p["solved"]
    assert not p["oneByte"]["hit"]
    assert [t["nibble"] for t in p["tries"] if t["hit"]] == [p["hitNibble"]]
    assert p["tries"][p["hitNibble"]]["ret"] == p["target"]


def test_kern106_has_room_for_the_chain():
    # regression: with VRIG's own frame size writeInput drops everything past
    # ret, so the chain never showed up. The exporter adds room.
    tr = WalkTrace.load("kern-106")
    assert tr.raw["vrigExtraSize"] == 0 and tr.raw["extraSize"] == 16
    assert tr.word(80, 4) == 0xc00a0000  # commit_creds
    assert tr.word(72, 3) == 0x000406f0


def test_c02_pointer_disagrees_with_sim_base():
    # VRIG writes 0xbfff0010 into p but StackSim puts x at 0xbfff0100.
    # C02 rebases its rows onto p. If VRIG fixes this the rebase can go.
    tr = WalkTrace.load("c-02")
    assert tr.word(4, 1) == 0xbfff0010 != tr.base


def test_line_fixes_point_at_the_logged_line():
    sc = _scenes()
    C05, Mit82 = sc.C05, sc.Mit82
    c05 = WalkTrace.load("c-05")
    assert "int hp" in c05.source[C05.line_fix[1]]
    assert "int score" in c05.source[C05.line_fix[2]]
    assert "name[8]" in c05.source[C05.line_fix[3]]
    mit = WalkTrace.load("mit-82")
    assert "Partial RELRO" in mit.source[Mit82.line_fix[4]]
