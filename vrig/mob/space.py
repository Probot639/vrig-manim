"""3D helpers. Memory sits on the xy floor, z is "up out of memory"."""
from __future__ import annotations

from manimlib import *

from vrig.theme import T


def arc3d(a, b, lift: float = 2.2, color: str | None = None, width: float = 5) -> VMobject:
    """
    Parabola from a to b peaking `lift` above the floor. Height means "control
    went somewhere else". Cubic beziers looked better on paper but manimgl
    turns them into quadratics with near-180 joints at the ends, and the
    miters spike right off the screen.
    """
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    curve = ParametricCurve(lambda t: a + (b - a) * t + OUT * lift * 4 * t * (1 - t), t_range=(0, 1, 0.02))
    return curve.set_stroke(color or T.highlight, width)


def billboard(mob: Mobject, frame, about=None) -> Mobject:
    """Stand a flat label up so it faces the camera at the frame's current angles."""
    theta, phi, _ = frame.get_euler_angles()
    c = mob.get_center() if about is None else about
    mob.rotate(phi, RIGHT, about_point=c)
    mob.rotate(theta, OUT, about_point=c)
    return mob
