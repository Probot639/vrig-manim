import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from vrig.trace import TRACE_DIR, StackTrace

IDS = ["ctf-47", "ctf-49", "ctf-50", "ctf-52", "mit-81", "adv-88", "adv-89",
       "adv-92", "adv-93", "adv-94", "adv2-101", "kern-104"]


def _scenes():
    spec = importlib.util.spec_from_file_location("stack_adv_scenes", Path(__file__).parent.parent / "scenes/stack_adv.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("tid", IDS)
def test_trace_loads_and_solves(tid):
    tr = StackTrace.load(tid)
    assert tr.raw["solved"]
    # the overflow walk in the scene keys off these labels
    assert any("(): write" in s["label"] for s in tr.steps)


@pytest.mark.parametrize("tid", [i for i in IDS if i != "adv2-101"])
def test_ret_lands_on_win(tid):
    tr = StackTrace.load(tid)
    assert tr.word_at(tr.ret_off) == tr.symbols["win"] == tr.raw["retAfter"]
    assert tr.raw["stepWin"]
    assert "Jumped to win()" in tr.steps[-1]["logs"][-1]["msg"]


@pytest.mark.parametrize("tid", ["ctf-50", "mit-81"])
def test_canary_put_back(tid):
    tr = StackTrace.load(tid)
    assert tr.canary_size == 4
    assert tr.word_at(tr.buf_size) == tr.raw["canaryValue"]
    assert tr.raw["canaryIntact"] and not tr.raw["canaryFailed"]


@pytest.mark.parametrize("tid", ["ctf-47", "ctf-49", "ctf-50", "ctf-52"])
def test_ctf_checks_throw_in_vrig(tid):
    # VRIG bug: these checks call sim.readWord/retOffset, which StackSim
    # doesn't have. The exporter records the throw and the shimmed result.
    raw = StackTrace.load(tid).raw
    assert "readWord" in raw["check"]["error"]
    assert raw["checkAdapted"]["result"] is True


def test_data_only_leaves_ret_alone():
    tr = StackTrace.load("adv2-101")
    assert tr.raw["check"]["result"] and not tr.raw["stepWin"]
    assert tr.raw["retAfter"] == tr.raw["origRet"]
    assert tr.word_at(tr.ebp_off) != 0
    assert len(tr.payload) == tr.buf_size + 4


def test_kernel_alt_commit_creds_crashes():
    raw = StackTrace.load("kern-104").raw
    alt = raw["alt"]
    assert not alt["stepWin"] and not alt["check"]["result"]
    assert "CRASH" in alt["jumpLogs"][0]["msg"]


def test_adv88_fake_vtable_in_buf():
    tr = StackTrace.load("adv-88")
    assert tr.word_at(0) == tr.symbols["win"]


def test_every_trace_has_a_scene():
    mod = _scenes()
    assert sorted(mod.SCENES) == sorted(IDS)
    for tid, cls in mod.SCENES.items():
        assert cls.trace_name == tid
        assert json.loads((TRACE_DIR / f"{tid}.json").read_text())["exercise"] == tid


def test_on_floor_keeps_slab_above_floor():
    # regression: CodeBlock.move_to() centered the billboarded label too, so
    # slabs sank below z=0 and vanished under kern-104's floor planes
    from manimlib import RIGHT
    mod = _scenes()

    class Frame:
        def get_euler_angles(self):
            return np.array([-6, 40, 0]) * np.pi / 180

    blk = mod.CodeBlock("win()", 0x08048150, "text_section", Frame())
    mod.on_floor(blk, RIGHT * 2)
    assert blk.slab.get_z(-1 * np.array([0, 0, 1])) >= -1e-6


def test_structview_blank_fields_dont_nan():
    # regression: Text("") has zero height and moving it went NaN
    from vrig.mob.stack_adv import StructView
    sv = StructView("STRTAB", [("", '"gets\\0"', "")])
    assert np.isfinite(sv.get_center()).all()


def test_frameview_fold_offsets():
    from vrig.mob.stack_adv import FrameView
    tr = StackTrace.load("kern-104")
    v = FrameView(tr, tr.step_index("Make room"), start=tr.buf_size - tr.word, show_addr=False, offset_labels=True)
    assert len(v.words) == (tr.total - v.start) // tr.word
    assert v.at(tr.ret_off) is v.words[-1]
    assert v.fold is not None
