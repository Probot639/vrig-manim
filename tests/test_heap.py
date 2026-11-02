"""Heap traces from tools/vrig-trace/heap-entry.ts and the bits of
vrig/mob/heap.py that read them."""
import json

import pytest

from vrig.mob.heap import HeapTrace, TRACE_DIR

SOLVED = ["heap-16", "heap-17", "heap-18", "heap2-19", "heap2-20", "heap2-21", "ctf-48", "ctf-51",
          "final-27", "final-28", "adv-90", "adv2-99", "kern-105"]
# generic submit never sets heap.funcPtrs, so VRIG can't pass these
UNSOLVABLE = ["heap2-22", "heap2-23", "heap2-24", "heap2-25", "heap2-26"]


@pytest.mark.parametrize("name", SOLVED + UNSOLVABLE)
def test_trace_loads(name):
    tr = HeapTrace.load(name)
    assert tr.ops, name
    assert tr.title


@pytest.mark.parametrize("name", SOLVED)
def test_solved(name):
    tr = HeapTrace.load(name)
    assert tr.solved
    # nothing VRIG calls a win should lean on a modeled step
    assert all(o["engine"] == "vrig" for o in tr.ops)


@pytest.mark.parametrize("name", UNSOLVABLE)
def test_houses_stay_unsolved(name):
    raw = json.loads((TRACE_DIR / f"{name}.json").read_text())
    assert raw["solved"] is False and raw["check"] is False
    assert any(o["engine"] == "model" for o in raw["ops"])


def test_check_disagrees_where_expected():
    # banner fires on result.completed, but check() looks at a funcPtrs key
    # the submit handler never sets
    for name in ("ctf-48", "kern-105"):
        raw = json.loads((TRACE_DIR / f"{name}.json").read_text())
        assert raw["completed"] and not raw["check"]


def test_win_pointer_is_win():
    for name in ("heap-16", "heap-18", "final-27"):
        tr = HeapTrace.load(name)
        fps = tr.state(len(tr.ops) - 1)["funcPtrs"]
        assert any(fp["current"] == tr.symbols["win"] for fp in fps.values())


def test_fastbin_dup_reaches_fastbin():
    # regression: the C source's order pulls a and b back out of tcache, so
    # the exporter allocates them first. free(a) must land in a fastbin
    tr = HeapTrace.load("heap2-20")
    st = tr.state(tr.find("step1", "free"))
    assert st["bins"]["fastbins"], "free(a) went to tcache again"
    assert len(st["bins"]["tcache"]["24"]) == 7


def test_carried_head_after_poison():
    # regression: once malloc pops a poisoned chunk, the head must follow its
    # fd even when VRIG's array still has another entry (final-28)
    tr = HeapTrace.load("final-28")
    i = tr.find("submit", "malloc")
    head = tr.heads(i)[("tcache", "40")]
    assert head == ("chunk", tr.state(i)["names"]["ptr0"])

    tr = HeapTrace.load("heap2-19")
    i = tr.find("submit", "malloc")
    assert tr.heads(i)[("tcache", "24")] == ("ext", tr.fp_addr)


def test_attacker_bytes_follow_payload():
    tr = HeapTrace.load("heap-18")
    i = tr.find("submit", "write")
    off, data = tr.ops[i]["args"]
    assert set(range(off, off + len(data))) <= tr.attacker(i)
    assert not tr.attacker(0)


def test_payload_derived_from_layout():
    # 16 bytes of a, b's header unchanged, then win()
    tr = HeapTrace.load("heap-18")
    p = tr.payloads[0]
    assert len(p) == 28
    assert int.from_bytes(bytes(p[-4:]), "little") == tr.symbols["win"]
