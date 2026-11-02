import pytest

from vrig.mob.arch import ArchTrace
from vrig.trace import StackTrace

ARM_QUIZ = ["arm-63", "arm-64", "arm-65", "arm-66", "arm-67", "arm-68"]
MIPS_QUIZ = ["mips-71", "mips-72", "mips-73", "mips-74", "mips-75", "mips-76"]
STACK = ["arm-69", "mips-77"]
ROP = ["arm-70", "mips-78"]


@pytest.mark.parametrize("ex", ARM_QUIZ + MIPS_QUIZ)
def test_quiz_trace_loads(ex):
    tr = ArchTrace.load(ex)
    assert tr.steps, ex
    assert len(tr.quiz) >= 2
    # every step ran a listed instruction, and memory snapshots cover memWords
    for s in tr.steps:
        assert s["fetched"] in tr.by_addr
        for a in tr.mem_words():
            assert f"0x{a:x}" in s["memory"]


@pytest.mark.parametrize("ex", MIPS_QUIZ)
def test_mips_quiz_matches_emulator(ex):
    # MIPS has no fetch bug, so every quiz answer agrees with the run
    tr = ArchTrace.load(ex)
    assert tr.raw["solved"], ex
    assert not tr.raw["pcFetchBug"]
    for q in tr.quiz:
        assert q["accepted"], q["question"]


@pytest.mark.parametrize("ex", ARM_QUIZ)
def test_arm_fetch_bug_is_recorded(ex):
    # the pc+8 fetch is real: every ARM step lands 8 bytes past pc, and the
    # run disagrees with the textbook answers. The video is honest about it.
    tr = ArchTrace.load(ex)
    assert tr.raw["pcFetchBug"], ex
    assert all(s["fetchSkew"] == 8 for s in tr.steps)
    assert not tr.raw["solved"], f"{ex} unexpectedly matches, the ARM core may be fixed"


def test_mips75_stops_at_hlt():
    # regression: the MIPS core has no hlt handler. mips-75 keeps real code
    # past its hlt and used to loop the body to the 500-step cap. The exporter
    # now ends the run at hlt.
    tr = ArchTrace.load("mips-75")
    assert tr.raw["endedAtHlt"]
    assert not tr.raw["hitStepCap"]
    assert tr.steps[-1]["mnemonic"].lower() == "hlt"


def test_arm_mem_words_are_unsigned():
    # regression: a stack addr like 0xbfff01f0 is past 2^31, and a signed
    # bitwise mask turned the watch key negative. memWords must stay positive.
    tr = ArchTrace.load("arm-68")
    assert all(a > 0 for a in tr.mem_words())


@pytest.mark.parametrize("ex", STACK)
def test_stack_overflow_wins(ex):
    tr = StackTrace.load(ex)
    assert tr.won(), ex
    assert tr.raw["check"] is True
    assert tr.raw["retAddr"] == tr.symbols["win"]


@pytest.mark.parametrize("ex", ROP)
def test_arch_rop_cannot_win(ex):
    # VRIG runs ARM/MIPS gadgets through its x86 ROP interpreter, which can't
    # read pop {r0, pc} or lw $a0, 0($sp). The chain desyncs and ropWin never
    # fires, so these exercises can't be solved as written. If this ever flips,
    # the engine was fixed and the videos need a new ending.
    tr = StackTrace.load(ex)
    assert not tr.won(), f"{ex} now wins, revisit the ROP video ending"
    assert tr.raw["check"] is False
