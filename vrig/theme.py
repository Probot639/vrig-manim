"""
Role-based colors. Scenes never name a hue, they ask for what a thing *is*:

    from vrig.theme import T
    Rectangle(fill_color=T.saved_ret)

The preset comes from $VRIG_THEME (a name in vrig/themes/ or a path to a .toml),
defaulting to 3b1b. To make a new palette, copy a preset and change values.

    python -m vrig.theme            # check the active preset
    python -m vrig.theme vrig       # check a named one
"""
from __future__ import annotations

import os
import sys
import tomllib
from itertools import combinations
from pathlib import Path

THEME_DIR = Path(__file__).parent / "themes"
DEFAULT = "3b1b"

# Roles that show up on screen at the same time. Only these pairs need to be
# told apart, a tcache bin and a canary never share a frame.
SCENE_GROUPS = {
    "stack": ["saved_ret", "saved_fp", "canary", "local_var", "buffer", "arg", "attacker_bytes"],
    "code reuse": ["gadget", "text_section", "libc", "saved_ret", "attacker_bytes"],
    "heap": ["chunk_header", "chunk_user", "freed_chunk", "tcache", "fastbin", "unsorted", "top_chunk",
             "attacker_bytes"],
    "privilege": ["kernel_space", "user_space", "attacker_bytes"],
    "outcome": ["win", "crash", "mitigation"],
}


class Theme:
    def __init__(self, name: str, background: str, swatches: dict, roles: dict, path: Path,
                 fonts: dict | None = None):
        self.name = name
        self.background = background
        fonts = fonts or {}
        self.mono = fonts.get("mono", "Noto Sans Mono")
        self.prose = fonts.get("prose", "Noto Sans")
        self.swatches = swatches
        self.roles = {}
        self.path = path
        for role, val in roles.items():
            hexval = swatches.get(val, val)
            if not str(hexval).startswith("#"):
                raise ValueError(f"{path.name}: role {role!r} points at unknown swatch {val!r}")
            self.roles[role] = hexval.upper()

    def __getattr__(self, role: str) -> str:
        # __getattr__ only fires for misses, so self.roles etc. don't recurse
        try:
            return self.__dict__["roles"][role]
        except KeyError:
            raise AttributeError(f"theme {self.__dict__.get('name')!r} has no role {role!r}") from None

    def __repr__(self):
        return f"<Theme {self.name} ({len(self.roles)} roles)>"


def _resolve(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.suffix == ".toml" and p.exists():
        return p
    p = THEME_DIR / f"{name_or_path}.toml"
    if not p.exists():
        have = ", ".join(sorted(x.stem for x in THEME_DIR.glob("*.toml")))
        raise FileNotFoundError(f"no theme {name_or_path!r} (have: {have})")
    return p


def load_theme(name_or_path: str | None = None) -> Theme:
    path = _resolve(name_or_path or os.environ.get("VRIG_THEME", DEFAULT))
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # every preset has to cover every role the default does, otherwise a scene
    # renders fine in one theme and dies halfway through in another
    base = DEFAULT_ROLES
    missing = [r for r in base if r not in raw.get("roles", {})] if base else []
    if missing:
        raise ValueError(f"{path.name} is missing roles: {', '.join(missing)}")

    return Theme(raw.get("name", path.stem), raw["background"], raw.get("swatches", {}),
                 raw.get("roles", {}), path, raw.get("fonts"))


# --- color distance, for the checker ----------------------------------------

def _hex_to_lin(h: str):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def _lin_to_lab(rgb):
    r, g, b = rgb
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


# Machado, Oliveira & Fernandes 2009, severity 1.0, applied in linear RGB
CVD = {
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                     [-0.011820, 0.042940, 0.968881]],
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                   [-0.003882, -0.048116, 1.051998]],
    "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                   [0.004733, 0.691367, 0.303900]],
}


def _sim(rgb, m):
    return [max(0.0, min(1.0, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3)]


def delta_e(a: str, b: str, vision: str | None = None) -> float:
    la, lb = _hex_to_lin(a), _hex_to_lin(b)
    if vision:
        la, lb = _sim(la, CVD[vision]), _sim(lb, CVD[vision])
    return sum((p - q) ** 2 for p, q in zip(_lin_to_lab(la), _lin_to_lab(lb))) ** 0.5


# Under ~10 two fills next to each other start reading as "the same thing".
# Picked by eyeballing the stack scene, not from any standard.
TOO_CLOSE = 10.0
CVD_TOO_CLOSE = 7.0


def check(theme: Theme) -> list[str]:
    problems = []
    for group, roles in SCENE_GROUPS.items():
        roles = [r for r in roles if r in theme.roles]
        for a, b in combinations(roles, 2):
            ca, cb = theme.roles[a], theme.roles[b]
            d = delta_e(ca, cb)
            if d < TOO_CLOSE:
                why = "identical" if ca == cb else f"dE {d:.1f}"
                problems.append(f"[{group}] {a} / {b}: {why}")
                continue
            for vision in CVD:
                d = delta_e(ca, cb, vision)
                if d < CVD_TOO_CLOSE:
                    problems.append(f"[{group}] {a} / {b}: dE {d:.1f} under {vision}")
    for role, c in theme.roles.items():
        if role != "cell_fill" and delta_e(c, theme.background) < 15:
            problems.append(f"{role} disappears into the background")
    return problems


DEFAULT_ROLES = None
with open(_resolve(DEFAULT), "rb") as _f:
    DEFAULT_ROLES = list(tomllib.load(_f)["roles"])

T = load_theme()


if __name__ == "__main__":
    th = load_theme(sys.argv[1] if len(sys.argv) > 1 else None)
    issues = check(th)
    print(f"{th.name}: {len(th.roles)} roles, {len(issues)} issue(s)")
    for line in issues:
        print("  " + line)
    sys.exit(1 if issues else 0)
