"""
Presenter back-stepping, without a window. Drives on_key_press by hand, since
there's no way to inject keys into a GL window from a test on Wayland anyway.
"""
from manimlib import Square, Circle, Triangle
from manimlib.event_keys import Keys

from vrig.scene import VrigScene


class Three(VrigScene):
    def construct(self):
        self.add(Square())
        self.beat(pause=0)
        self.add(Circle())
        self.beat(pause=0)
        self.add(Triangle())
        self.beat(pause=0)


def kinds(scene):
    return [type(m).__name__ for m in scene.mobjects if type(m).__name__ in ("Square", "Circle", "Triangle")]


def test_left_then_right_walks_beats():
    s = Three(skip_animations=True)
    s.run()
    assert kinds(s) == ["Square", "Circle", "Triangle"]

    # pretend we're parked on the last beat in presenter mode
    s.presenter_mode = True
    s.hold_on_wait = True

    s.on_key_press(Keys.LEFT, 0)
    assert kinds(s) == ["Square", "Circle"]
    s.on_key_press(Keys.LEFT, 0)
    assert kinds(s) == ["Square"]
    s.on_key_press(Keys.LEFT, 0)  # already at the first beat, stays put
    assert kinds(s) == ["Square"]

    s.on_key_press(Keys.RIGHT, 0)
    assert kinds(s) == ["Square", "Circle"]
    assert s.hold_on_wait, "replaying a saved beat must not release the hold"
    s.on_key_press(Keys.RIGHT, 0)
    assert kinds(s) == ["Square", "Circle", "Triangle"]

    # caught up: the next right is the real one, it lets construct() continue
    s.on_key_press(Keys.RIGHT, 0)
    assert not s.hold_on_wait
