"""
Trace checks for the stack family (imagine-rit, unit1-stack, unit2-logic, and
the three new unit3-stack-ii lessons). These guard that every trace loads, that
VRIG's own engine actually won each exercise that has a goal, and that the few
derived values the scenes depend on are what VRIG produced.

    .venv/bin/python -m pytest -q tests/test_stack.py
"""
import json

import pytest

from vrig.trace import StackTrace, TRACE_DIR

# step-engine traces: StackTrace.load works and VRIG reports a win
STEP_WIN = [
    "rit-02", "rit-03", "rit-04", "rit-rop",
    "stack-02", "stack-03", "stack-04", "stack-05",
    "logic-06", "logic-09", "logic-10",
    "stack2-11", "stack2-13",
]
FMT = ["logic-07", "logic-08"]


def raw(name):
    return json.loads((TRACE_DIR / f"{name}.json").read_text())


@pytest.mark.parametrize("name", STEP_WIN)
def test_step_trace_wins(name):
    tr = StackTrace.load(name)
    assert tr.won(), f"{name}: VRIG's engine did not win this payload"
    assert raw(name)["solved"] is True


@pytest.mark.parametrize("name", FMT)
def test_fmt_trace_solved(name):
    d = raw(name)
    assert d["solved"] is True, f"{name}: fmt exercise not solved"
    assert d["stack"], "fmt trace has no reconstructed stack slots"


@pytest.mark.parametrize("name", STEP_WIN + ["stack2-14"])
def test_write_offsets_fit_stack(name):
    # regression: a scene builds total//word stack words and feeds every write
    # step onto them. If a write landed past that, StackView.at() blew up
    # (the bug that first broke the SROP scene). Guard the invariant here.
    tr = StackTrace.load(name)
    n_words = tr.total // tr.word
    for step in tr.steps:
        hl = step["hl"]
        if hl and any(step["label"].startswith(p) for p in ("gets", "memcpy", "read_byte")):
            assert hl[1] <= n_words * tr.word, f"{name}: write ends past the stack"


def test_aslr_slide_applied():
    # the leaked main must be slid, and win must stay a fixed 0x150 above it
    for name in ("rit-04", "stack-04"):
        tr = StackTrace.load(name)
        assert tr.symbols["main"] != 0x08048000, f"{name}: main not slid"
        assert tr.symbols["win"] - tr.symbols["main"] == 0x150
        assert tr.word_at(tr.ret_off) == tr.symbols["win"]


def test_canary_low_byte_is_null():
    # VRIG builds canaries with a zero LSB, which is what makes them hard to
    # leak with string functions. The payload must replant the exact value.
    tr = StackTrace.load("stack-05")
    canary = raw("stack-05")["canaryValue"]
    assert canary & 0xff == 0
    assert tr.word_at(tr.buf_size) == canary
    assert tr.won()


def test_ret2libc_frame():
    tr = StackTrace.load("stack2-11")
    assert tr.word_at(tr.ret_off) == tr.symbols["system"]
    arg_off = tr.ret_off + 2 * tr.word
    assert tr.word_at(arg_off) == tr.symbols["binsh"]


def test_rop_chains_write_magic_then_win():
    for name in ("rit-rop", "stack2-13"):
        tr = StackTrace.load(name)
        events = tr.rop_events()
        writes = [ev.write for ev in events if ev.write]
        assert writes, f"{name}: no memory write in the chain"
        val, addr = writes[-1]
        assert addr == tr.flag_addr and val == tr.magic
        assert events[-1].next_eip == tr.symbols["win"]


def test_pivot_lands_on_staged_chain():
    # stack2-13: the xchg gadget moves esp to an address we popped into eax,
    # and that address is inside our own controlled stack data.
    tr = StackTrace.load("stack2-13")
    events = tr.rop_events()
    pivot = next(ev for ev in events if "xchg eax, esp" in ev.text)
    # the value loaded just before the pivot is the staged-chain address
    eax = None
    for ev in events:
        for reg, v in ev.pops:
            if reg == "eax":
                eax = v
        if ev is pivot:
            break
    assert eax is not None
    assert tr.base <= eax < tr.base + tr.total, "pivot target is outside our data"


def test_srop_unsolvable_in_vrig():
    # Known VRIG bug: SROP reserves extraSize=44, so totalSize=68, but sropExec
    # needs frameStart(24)+60 <= totalSize, i.e. >= 84. sigreturn is reached but
    # the frame never fits, so the win can't register. The video shows this
    # honestly instead of faking a win.
    tr = StackTrace.load("stack2-14")
    assert not tr.won()
    assert raw("stack2-14")["solved"] is False
    srop = next(s for s in tr.steps if s["label"].startswith("SROP"))
    msgs = [l["msg"] for l in srop["logs"]]
    assert any("Calling sigreturn" in m for m in msgs)
    assert any("doesn't fit" in m for m in msgs)
    assert tr.word_at(tr.ret_off) == tr.symbols["sigreturn"]
