import json
from pathlib import Path

import pytest

from vrig.trace import TRACE_DIR

IDS = ["mit-79", "mit-83", "mit-86", "adv-91", "adv2-95", "adv2-97", "adv2-98", "adv2-100", "adv2-102",
       "kern-103", "gap-113"]


def load(i):
    return json.loads((TRACE_DIR / f"{i}.json").read_text())


@pytest.mark.parametrize("ex", IDS)
def test_trace_loads_and_vrig_accepts(ex):
    t = load(ex)
    assert t["exercise"] == ex
    assert t["solved"], [c for c in t["checks"] if not c["ok"]]
    assert all(q["correct"] for q in t["quiz"])


def test_mit83_lea_uses_next_rip():
    # VRIG's emulator adds the current rip and masks to 32 bits. The scene
    # shows the real value, and that has to be what the quiz wants.
    t = load("mit-83")
    lea = t["lea"]["run1"][0]
    assert lea["value"] == lea["next"] + lea["disp"] == t["quiz"][0]["answer"]
    assert t["emuLea"][0]["emu"] != lea["value"]


def test_mit86_emulator_stops_at_fs_operand():
    t = load("mit-86")
    assert "fs:0x28" in t["run"]["error"]


def test_spectre_branch_taken_and_spec_window():
    t = load("adv2-97")
    assert t["branchTaken"]
    assert t["spec"]["steps"][1]["regs"]["ebx"] == t["secret"] << 8
    assert t["run"]["steps"][-1]["regs"]["ebx"] == 0


def test_dop_secret_spells_password():
    # regression: the second word was once 0x0064726f, which reads "ord"
    t = load("adv2-102")
    raw = b"".join(v.to_bytes(4, "little") for v in t["outAfter"])
    assert raw == b"password"


def test_shellcode_runs_to_execve():
    t = load("gap-113")
    assert 0 not in t["shellcode"] and len(t["shellcode"]) == 23
    assert t["ebxString"] == "/bin//sh"
    assert [p["why"] for p in t["patched"]] == ["Unknown operand: al"]


def test_brop_tries_match_canary():
    t = load("adv2-98")
    assert t["canary"][0] == 0
    assert t["tries"] == [b + 1 for b in t["canary"]]
