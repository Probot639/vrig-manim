import textwrap

from manimlib import DOWN, UP, BackgroundRectangle, FadeIn, FadeOut, IN, Scene, ThreeDScene, VGroup
from manimlib.event_keys import Keys

from vrig.mob.memory import prose

from vrig.theme import T


class BeatMixin:
    """
    Beats are the places a presenter stops. In a render, beat() is just a
    pause. With `-p` (presenter mode) it holds until space/right, and left
    steps back to the previous beat.

    Going back restores a snapshot, it doesn't run anything in reverse. Going
    forward again cuts straight to each saved beat until you're back at the
    newest one, then the next right plays the real animation. Ctrl-z/undo in
    manimlib uses the same SceneState snapshots.
    """
    default_camera_config = dict(background_color=T.background)
    beat_pause = 0.8

    def setup(self):
        super().setup()
        self._beats = []
        self._cursor = -1
        self.cap = None

    def say(self, text: str, width: int = 72, size: int = 26, **kw):
        """Swap the bottom caption. Fade, don't Transform: morphing one
        sentence's glyphs into another's turns to soup halfway through."""
        words = prose("\n".join(textwrap.wrap(text, width)), size, T.label)
        plate = BackgroundRectangle(words, buff=0.14).set_fill(T.background, 0.85).shift(IN * 0.01)
        new = VGroup(plate, words).to_edge(DOWN, buff=0.25).fix_in_frame()
        anims = [FadeIn(new, shift=UP * 0.1)]
        if self.cap is not None:
            anims.append(FadeOut(self.cap, shift=UP * 0.1))
        self.cap = new
        self.play(*anims, **kw)

    def unsay(self, **kw):
        if self.cap is not None:
            self.play(FadeOut(self.cap), **kw)
            self.cap = None

    def beat(self, note: str | None = None, pause: float | None = None):
        self._beats.append(self.get_state())
        self._cursor = len(self._beats) - 1
        self.wait(self.beat_pause if pause is None else pause, note=note)

    def on_key_press(self, symbol, modifiers):
        holding = self.presenter_mode and self.hold_on_wait and self._beats
        if holding and symbol == Keys.LEFT:
            if self._cursor > 0:
                self._cursor -= 1
                self.restore_state(self._beats[self._cursor])
            return
        if holding and (symbol == Keys.RIGHT or symbol == ord(" ")):
            if self._cursor < len(self._beats) - 1:
                self._cursor += 1
                self.restore_state(self._beats[self._cursor])
                return
        super().on_key_press(symbol, modifiers)


class VrigScene(BeatMixin, Scene):
    pass


class Vrig3DScene(BeatMixin, ThreeDScene):
    pass
