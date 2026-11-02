# vrig-manim

ManimGL with an RE and exploitation layer on top, for animating every concept
in 0xVRIG and then some. `manimlib/` is upstream 3b1b/manim and is left alone
except for one dependency fix. Our code is in `vrig/`, scenes are in `scenes/`.
`CURRICULUM.md` lists every concept that gets a scene.

## Setup

```sh
uv venv -p 3.12 .venv          # moderngl has no wheels for 3.15 yet
uv pip install -p .venv/bin/python -e .
```

Math goes through `Tex`, so you need `latex` and `dvisvgm` on the path. On
Arch that's `texlive-basic texlive-latex texlive-latexrecommended
texlive-latexextra texlive-fontsrecommended texlive-binextra texlive-science`.
`custom_config.yml` switches manimgl to its `basic` template. The default one
pulls in dsfont, calligra, tipa, and a pile of other packages from
texlive-fontsextra that we never use. Run manimgl from the repo root or it
won't see that file.

Prose and captions use `Text` with the theme's font. Code, bytes, and
addresses use the theme's mono font.

## Running a scene

```sh
.venv/bin/manimgl scenes/unit3_stack_ii.py RopBasics            # live window
.venv/bin/manimgl scenes/unit3_stack_ii.py RopBasics -p         # presenter mode
.venv/bin/manimgl scenes/unit3_stack_ii.py RopBasics -w --hd    # mp4 into videos/
.venv/bin/manimgl scenes/unit3_stack_ii.py RopBasics -w -l      # quick 480p check
```

The booth demo videos are in `scenes/demo.py` (`DemoOverflow`,
`DemoAddresses`, `DemoCounter`). Their trace comes from a second exporter
entry:

```sh
node tools/vrig-trace/dist/vrig-demo.mjs > traces/demo.json
```

In presenter mode, space or right arrow plays the next beat. Left arrow jumps
back to the previous beat. Right then cuts forward through saved beats until
you're back at the newest one, and plays from there.

## Unit overviews

One video per unit: a title card, the first few seconds of every lesson in the
unit, then a closing card. Good for showing a whole unit at a glance.

```sh
node tools/vrig-trace/dist/vrig-units.mjs > traces/units.json   # once
tools/overview.sh unit0-asm          # -> videos/overviews/unit0-asm.mp4
tools/overview.sh unit0-asm 8        # 8 seconds of each lesson instead of 5
```

`traces/units.json` holds VRIG's unit and lesson titles. The cards are
`scenes/overview.py` (`UnitIntro`, `UnitOutro`), driven by `VRIG_UNIT`.

## Themes

Scenes never name a color. They ask for a role (`T.saved_ret`, `T.gadget`,
`T.tcache`) and a preset in `vrig/themes/` maps roles to colors and fonts.

```sh
VRIG_THEME=vrig .venv/bin/manimgl ...     # VRIG deck palette
VRIG_THEME=3b1b .venv/bin/manimgl ...     # default
VRIG_THEME=~/my.toml .venv/bin/manimgl ...
```

To make a new one, copy a preset and change the values. Then check it:

```sh
.venv/bin/python -m vrig.theme my-preset
```

The checker compares every pair of roles that can share a scene. It checks
normal vision, deuteranopia, protanopia, and tritanopia, and also flags roles
that vanish into the background. `scenes/smoke.py ThemeSwatches` renders a
preset as a swatch sheet.

## Traces

Stack scenes don't hardcode addresses. They play back a trace of VRIG's own
`StepEngine` running a payload, so a scene can't drift from the exercise.

```sh
# once per VRIG checkout. needs esbuild on PATH, or ESBUILD=/path/to/esbuild
tools/vrig-trace/build.sh /path/to/0xVRIG-main

node tools/vrig-trace/dist/vrig-trace.mjs stack2-12 <payload hex> > traces/stack2-12.json
```

Traces are committed, so rendering never needs VRIG around.

## Making a video by hand

`scenes/example_by_hand.py` is the template, and `videos/examples/by-hand.mp4`
is what it renders. It plays back the ROP Basics trace that's already in
`traces/`, so you can run it without touching VRIG.

For a new stack exercise:

1. Solve it on VRIG and copy the payload hex out of the payload builder.
2. Export the trace and make sure the payload actually wins:
   ```sh
   node tools/vrig-trace/dist/vrig-trace.mjs <id> '<payload hex>' > traces/<id>.json
   .venv/bin/python -c "from vrig.trace import StackTrace; print(StackTrace.load('<id>').won())"
   ```
   `False` means VRIG doesn't accept it. The scene asserts on this, so it won't
   render a fake win.
3. Copy `scenes/example_by_hand.py`, set `TRACE` and `TITLE`, and rewrite the
   `self.say()` captions. `self.beat()` marks where presenter mode stops.
4. Look at it in 480p, then render the real one:
   ```sh
   .venv/bin/manimgl scenes/<file>.py <Scene> -w -l --video_dir /tmp/check
   .venv/bin/manimgl scenes/<file>.py <Scene> -w --hd --video_dir videos/<unit> --file_name <id>
   ```

The template stops once the input reaches the return address. If your
exercise keeps going (a ROP chain, a pivot), `RopBasics` in
`scenes/unit3_stack_ii.py` shows how the 3D chain half works.

`vrig-trace.mjs` drives the `input-hex` path with ASLR off. Format strings,
integer overflow, signedness, heap, and asm exercises go through other parts
of VRIG and need their own exporter entry. Copy `entry.ts` to
`tools/vrig-trace/<name>-entry.ts` and `build.sh` picks it up.

## Tests

```sh
.venv/bin/python -m pytest -q tests/test_vrig.py tests/test_beats.py
```

These cover the theme presets, trace consistency (each gadget's `ret` lands
on the next gadget and the chain ends in `win`), and presenter back-stepping.
