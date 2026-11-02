import pytest

from vrig.mob.windows import HeapTrace, WinStackTrace, source_lines

STACK = ["win-37", "win-38", "win-39", "win-40", "win-41", "win-42"]
HEAP = ["win-43", "win-44", "win-45", "win-46"]


@pytest.mark.parametrize("name", STACK)
def test_stack_traces_win(name):
    tr = WinStackTrace.load(name)
    assert tr.solved
    # VRIG's jump step and ex.check() both have to agree
    assert tr.raw["stepWin"] and tr.raw["check"]
    assert tr.word_at(tr.ret_off) == tr.symbols["win"]
    assert len(tr.payload) == tr.ret_off + tr.word


@pytest.mark.parametrize("name", HEAP)
def test_heap_traces_win(name):
    tr = HeapTrace.load(name)
    assert tr.solved
    assert tr.raw["completed"] and tr.raw["check"]
    final = tr.snap("submit")
    assert any(p["current"] == tr.symbols["win"] for p in final["funcPtrs"].values())


def test_gs_cookie_is_kept_and_naive_run_aborts():
    tr = WinStackTrace.load("win-41")
    assert tr.word_at(tr.buf_size) == tr.canary
    naive = tr.attempts["noCookie"]
    assert naive["canaryFailed"] and not naive["stepWin"]


def test_win39_hint_distance_is_wrong_in_vrig():
    # desc says 20 bytes to ret, VRIG's frame is 24 + ebp. the scene says so out loud
    tr = WinStackTrace.load("win-39")
    assert tr.raw["descRetDistance"] == 20 and tr.ret_off == 28
    assert not tr.attempts["descHint"]["check"]


def test_win40_ppr_lands_on_nseh_then_past_handler():
    ppr = WinStackTrace.load("win-40").raw["ppr"]
    t = ppr["trace"]
    assert [s["insn"].split()[0] for s in t] == ["pop", "pop", "ret", "jmp"]
    assert t[2]["eip"] == ppr["recordAddr"] and t[3]["eip"] == ppr["recordAddr"] + 8


def test_cfg_probe_is_mid_function_and_win_slot_valid():
    cfg = WinStackTrace.load("win-42").raw["cfg"]
    assert not cfg["probe"]["valid"]
    assert cfg["slots"][cfg["retSlot"]]["fn"] == "win"


def test_win45_list_holds_a_twice_and_desc_payload_fails():
    tr = HeapTrace.load("win-45")
    second = next(s for s in tr.timeline if s.get("doubleFree"))
    a = tr.raw["timeline"][0]["names"]["A"]
    assert second["freeLists"]["listHints"]["3"] == [a, a]
    assert not tr.attempts["descHint"]["completed"]


def test_win44_overflow_breaks_b_header():
    tr = HeapTrace.load("win-44")
    b = tr.snap("submit")["chunks"][1]
    assert not b["headerOk"]


@pytest.mark.parametrize("name", ["win-43", "win-44"])
def test_lfh_win10_randomizes_but_spray_pins(name):
    lf = HeapTrace.load(name).lfh
    assert lf["threshold"] == 18
    assert lf["reuseRate"]["hits"] < lf["reuseRate"]["trials"] // 2
    assert lf["spray"]["reused"]


def test_lfh_win7_is_first_fit():
    lf = HeapTrace.load("win-46").lfh["win7"]
    assert [a["slot"] for a in lf["lfhAllocs"]] == list(range(len(lf["lfhAllocs"])))
    assert lf["reuseRate"]["hits"] == lf["reuseRate"]["trials"]


def test_source_lines_maps_vrig_line_numbers():
    # regression: the ret highlight used VRIG's srcLine on the filtered listing
    src = ["#include <windows.h>", "", "void win() {", "}", "", "", "void vuln() {", "}"]
    lines, where = source_lines(src)
    assert lines[where[6]] == "void vuln() {"
    assert "#include" not in " ".join(lines)
