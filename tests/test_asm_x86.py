import pytest

from vrig.mob.asm_x86 import AsmTrace, WordColumn, choices, labels_from_source, vhex

IDS = [f"asm-{n:02d}" for n in range(1, 11)] + [f"x64-{n}" for n in range(29, 37)]


@pytest.mark.parametrize("ex", IDS)
def test_trace_solves_quiz(ex):
    tr = AsmTrace.load(ex)
    assert tr.raw["solved"]
    for q in tr.quiz:
        assert q["correct"], q["question"]
        assert 0 <= q["probe"]["step"] < len(tr.steps)


@pytest.mark.parametrize("ex", IDS)
def test_steps_follow_the_listing(ex):
    # every step ran an instruction VRIG listed, and eip/rip after a step is
    # where the next step starts (unless the exporter had to patch fall-through)
    tr = AsmTrace.load(ex)
    for i, s in enumerate(tr.steps):
        assert tr.ins[s["idx"]]["addr"] == s["addr"]
        if i + 1 < len(tr.steps) and not tr.steps[i + 1]["patched"] and not s.get("error"):
            assert tr.next_ip(i) == tr.steps[i + 1]["addr"]


def test_patched_runs_are_flagged():
    # the movabs exercises halt after one line in VRIG itself. the trace has to say so
    for ex in ("x64-33", "x64-34", "x64-35", "x64-36"):
        tr = AsmTrace.load(ex)
        assert tr.raw["patched"] and tr.raw["vrigRun"]["steps"] == 1
    for ex in ("asm-01", "asm-06", "x64-29", "x64-31"):
        assert not AsmTrace.load(ex).raw["patched"]


def test_stalls_are_worked_by_hand():
    tr = AsmTrace.load("x64-32")
    assert "r15d" in tr.steps[-1]["error"]
    assert tr.raw["stall"]["edi"] == tr.regs(len(tr.steps) - 1)["r15"] & 0xFFFFFFFF
    tr = AsmTrace.load("x64-35")
    assert tr.raw["stall"]["matches"]


def test_labels_land_on_distinct_lines():
    # regression: the matcher used to restart at the label it just placed, so
    # add_nums: overwrote main: on instruction 0
    lab = labels_from_source(AsmTrace.load("asm-10"))
    assert sorted(lab.values()) == ["add_nums", "main"]
    assert AsmTrace.load("asm-10").ins[min(k for k, v in lab.items() if v == "add_nums")]["addr"] == 0x08048014
    # x64-30's source starts main: after the prologue. snap back to the entry
    lab = labels_from_source(AsmTrace.load("x64-30"))
    assert lab[0] == "main"


def test_marker_side_survives_copy():
    # regression: side used to be the LEFT array, copy() deep-copied it and
    # `is LEFT` went false, so moved esp markers jumped to the right edge
    tr = AsmTrace.load("asm-03")
    col = WordColumn(tr, tr.stack_words())
    m = col.marker("esp")
    assert m.copy().side == "L"


def test_choices_parse():
    tr = AsmTrace.load("x64-36")
    assert choices(tr.quiz[1])[1].startswith("GOT")
    assert choices(AsmTrace.load("asm-10").quiz[1]) == {1: "caller", 2: "callee"}


def test_vhex_matches_asmviz():
    assert vhex(-1, 8) == "0xffffffff"
    assert vhex(0x7FFFF7A4526A, 16) == "0x00000000f7a4526a"


@pytest.mark.parametrize("ex", IDS)
def test_stack_column_has_no_holes(ex):
    # regression: only touched words were watched, so asm-09 and x64-29 drew
    # 0xbfff01f0 / 0xbfff01e0 as missing rows between their neighbours
    tr = AsmTrace.load(ex)
    w = tr.stack_words()
    assert all(b - a == tr.word for a, b in zip(w, w[1:]))
