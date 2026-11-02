from pathlib import Path

import pytest

from vrig.theme import THEME_DIR, check, load_theme
from vrig.trace import TRACE_DIR, StackTrace


@pytest.mark.parametrize("preset", sorted(p.stem for p in THEME_DIR.glob("*.toml")))
def test_theme_presets_pass_checker(preset):
    assert check(load_theme(preset)) == []


def test_rop_basics_trace_chains_into_win():
    tr = StackTrace.load("stack2-12")
    assert tr.won()
    evs = tr.rop_events()
    # each gadget's ret has to land on the next gadget, and the last one on win
    for a, b in zip(evs, evs[1:]):
        assert a.next_eip == b.addr
    assert evs[-1].next_eip == tr.symbols["win"]
    assert any(e.write == (tr.magic, tr.flag_addr) for e in evs)


def _stack_traces():
    # only StepEngine stack traces fit StackTrace. heap, asm, and demo traces
    # have their own shapes and their own tests
    import json
    def is_stack(d):
        return {"layout", "payload", "gadgets"} <= d.keys()  # entry.ts shape
    return sorted(p for p in TRACE_DIR.glob("*.json") if is_stack(json.loads(p.read_text())))


@pytest.mark.parametrize("path", _stack_traces(), ids=lambda p: p.stem)
def test_traces_load(path: Path):
    StackTrace.load(path.stem)


def test_demo_trace_outcomes():
    # what each demo video claims has to be what VRIG's demo logic says
    import json
    d = json.loads((TRACE_DIR / "demo.json").read_text())
    st = d["overflow"]["states"]
    assert [st[k]["outcome"] for k in ("name", "spill", "crash", "admin")] == ["normal", "normal", "crash", "success"]
    assert d["addresses"]["states"]["oldAim"]["outcome"] == "crash"
    assert d["addresses"]["states"]["leakAim"]["outcome"] == "success"
    runs = {r["requested"]: r for r in d["counter"]["runs"]}
    assert not runs[247]["wrapped"] and runs[248]["allocated"] == 0 and runs[250]["allocated"] == 2


def test_demo_strip_types_every_letter():
    # regression: per-letter morph used to compare against the last *target*
    # state, so typing "Taylor" one cell at a time only ever showed the T
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("demo_scenes", Path(__file__).parent.parent / "scenes/demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)

    st = demo.DEMO["overflow"]["states"]
    strip = demo.DemoStrip(st["empty"])
    for target in (st["name"], st["crash"], st["admin"]):
        for i in range(demo.RET):
            strip.morph(target, only=[i])
        assert strip.shown == [(demo.glyph_for(target, i), demo.role_for(target, i)) for i in range(demo.RET)]
