"""
glibc heap lessons: unit4, unit5, the heap CTFs, the finals, adv-90,
adv2-99, kern-105. Every state on screen is a snapshot from
tools/vrig-trace/heap-entry.ts, which runs VRIG's own HeapSim, guided steps
and submit handlers.

    manimgl scenes/heap.py Heap16 -w -l     # quick check
    manimgl scenes/heap.py Heap16 -p        # presenter

Each exercise is a HeapLesson with a `script()` of beats. `self.go(i, ...)`
moves the whole picture to the trace's op i.
"""
from manimlib import *

from vrig.mob.cpu import CodeListing
from vrig.mob.heap import BinPanel, FuncPtrPanel, HeapCfg, HeapTrace, HeapView, fit, h32, link, morph
from vrig.mob.memory import LIFT, mono, prose
from vrig.mob.space import arc3d, billboard
from vrig.scene import Vrig3DScene, VrigScene
from vrig.theme import T


class HeapLesson(VrigScene):
    trace_name = ""
    subtitle = ""
    heap_cfg: dict = {}
    names: dict = {}          # VRIG heap name -> label on screen
    fp_labels: dict = {}      # funcPtrs key -> label
    fp_at_table = False       # the pointer lives at funcPtrAddr, off the heap
    notes: dict = {}          # off-heap address -> what it is
    code_size = 16
    code_drop = ()            # substrings of source lines to leave out
    bins_x = 5.0
    heap_top = 2.9
    takeaway = ""

    def construct(self):
        self.tr = HeapTrace.load(self.trace_name)
        tr = self.tr
        self.cfg = fit(tr, HeapCfg(**{"labels": self.names, "x": 0.8, **self.heap_cfg}), top=self.heap_top)
        self.notes = {tr.fp_addr: "handler", **self.notes} if self.fp_at_table else dict(self.notes)
        self.parts = {}
        self.model_tag = None
        if isinstance(self, ThreeDScene):
            self.frame.reorient(0, 0)   # ThreeDScene starts tilted
        self.intro()
        self.script()
        self.outro()

    # -- framing -----------------------------------------------------------

    def intro(self):
        tr = self.tr
        title = prose(tr.title, 46).to_edge(UP, buff=0.45)
        sub = prose(self.subtitle, 24, T.text_dim).next_to(title, DOWN, buff=0.25)
        self.play(Write(title), FadeIn(sub, shift=UP * 0.2))
        self.beat()
        src = [l for l in tr.source if not l.startswith("#include") and l.strip()
               and not any(d in l for d in self.code_drop)]
        self.src = src
        code = CodeListing(src, size=self.code_size)
        if code.get_width() > 3.8:
            code.set_width(3.8)
        if code.get_height() > 5.9:
            code.set_height(5.9)
        code.to_corner(UL, buff=0.35).shift(DOWN * 0.5)
        self.code = code
        small = prose(tr.title, 22, T.text_dim).to_corner(UL, buff=0.3)
        self.play(FadeOut(sub), ReplacementTransform(title, small), FadeIn(code, shift=RIGHT * 0.3))
        self.title_mob = small

    def outro(self):
        tr = self.tr
        self.unsay()
        self.play(*(m.animate.set_opacity(0.12) for m in self.parts.values()),
                  self.code.animate.set_opacity(0.3), run_time=0.8)
        if tr.solved:
            head = mono(tr.raw["winTitle"], 30, T.win)
            body = prose("\n".join(_wrap(tr.raw["winMsg"], 64)), 19, T.label)
        else:
            head = prose(self.takeaway_head, 30, T.highlight)
            body = prose("\n".join(_wrap(self.takeaway, 64)), 19, T.label)
        card = VGroup(head, body).arrange(DOWN, buff=0.3).move_to(RIGHT * 1.6).shift(OUT * 0.06)
        # pushed back a hair so the 3d scene's depth test doesn't eat the text
        plate = BackgroundRectangle(card, buff=0.35).set_fill(T.background, 0.94).shift(IN * 0.02)
        frame = SurroundingRectangle(card, buff=0.35).set_stroke(T.win if tr.solved else T.grid, 2).shift(IN * 0.01)
        self.play(FadeIn(plate), ShowCreation(frame), FadeIn(card, shift=UP * 0.2), run_time=1.2)
        self.beat(pause=4.0)

    takeaway_head = "Takeaway"

    def say(self, text: str, **kw):
        # old caption out before the new one comes in, so two never overlap
        if self.cap is not None:
            self.play(FadeOut(self.cap, shift=UP * 0.1), run_time=0.25)
            self.cap = None
        # addresses in captions come from the trace, never typed in
        text = text.replace("{fp}", h32(self.tr.fp_addr))
        super().say(text, **kw)

    # -- moving between trace states -------------------------------------------

    def build(self, i: int, roles: dict | None = None) -> dict:
        tr = self.tr
        hv = HeapView(tr, i, self.cfg, roles)
        hv.fd_links()
        self.heapview = hv
        bp = BinPanel(tr, i, x=self.bins_x, y=self.bins_y(), notes=self.notes, labels=self.names, fmt=self.cfg.fmt)
        self.bins = bp
        fp = FuncPtrPanel(tr, i, labels=self.fp_labels,
                          addr={k: tr.fp_addr for k in tr.state(i)["funcPtrs"]} if self.fp_at_table else None)
        fp.place(np.array([7.0, 3.75, 0]), UR)
        self.fps = fp
        parts = {}
        for pre, src in (("h", hv.parts), ("b", bp.parts), ("f", fp.parts)):
            for k, m in src.items():
                parts[(pre, *k)] = m
        return parts

    def bins_y(self):
        st = self.tr.state(0)
        return 2.55

    def go(self, i: int, say: str | None = None, code: str | None = None, run_time: float = 1.0,
           roles: dict | None = None, also=()):
        new = self.build(i, roles)
        anims = morph(self.parts, new)
        if code is not None:
            anims.append(self.code.focus(self.line(code)))
        self.play(*anims, *also, run_time=run_time)
        self.remove(*self.parts.values())
        self.add(*new.values())
        self.parts = new
        self.cur = i
        self._model_tag(self.tr.ops[i]["engine"] == "model")
        if say:
            self.say(say)

    def line(self, needle: str) -> int:
        for k, l in enumerate(self.src):
            if needle in l:
                return k
        raise KeyError(f"no source line with {needle!r}")

    def focus(self, needle: str):
        self.play(self.code.focus(self.line(needle)), run_time=0.5)

    def _model_tag(self, on: bool):
        if on and self.model_tag is None:
            tag = mono("glibc model, past VRIG's sim", 13, T.text_dim)
            tag.next_to(self.title_mob, DOWN, buff=0.08, aligned_edge=LEFT)
            self.model_tag = tag
            self.play(FadeIn(tag), run_time=0.4)
        elif not on and self.model_tag is not None:
            self.play(FadeOut(self.model_tag), run_time=0.3)
            self.model_tag = None

    # -- the attacker's bytes ----------------------------------------------------

    def payload(self, i_write: int, say: str | None = None, code: str | None = None, label: str = "input"):
        """Show the bytes a write op puts in, fly them onto the cells, then go(i)."""
        off, data = self.tr.ops[i_write]["args"]
        words = VGroup()
        for k in range(0, len(data), 4):
            chunk = data[k:k + 4]
            words.add(mono(" ".join(f"{b:02x}" for b in chunk), 14, T.attacker_bytes))
        per = 3   # 4 words a row runs into the heap's name labels
        rows = VGroup(*(VGroup(*words[r:r + per]).arrange(RIGHT, buff=0.3) for r in range(0, len(words), per)))
        rows.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        lab = mono(label, 14, T.text_dim)
        strip = VGroup(lab, rows).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        plate = BackgroundRectangle(strip, buff=0.15).set_fill(T.background, 0.95).shift(IN * 0.01)
        strip = VGroup(plate, strip).next_to(self.code, DOWN, buff=0.3, aligned_edge=LEFT)
        # long listings: keep it above the caption, over the last code lines
        if strip.get_bottom()[1] < -2.7:
            strip.shift(UP * (-2.7 - strip.get_bottom()[1]))
        if code:
            self.focus(code)
        self.play(FadeIn(strip, shift=UP * 0.2))
        if say:
            self.say(say)
        self.beat()
        hv = self.heapview
        flights = []
        for k, w in enumerate(words):
            dst = off + 4 * k
            key = ("h", "txt", dst)
            target = self.parts.get(key)
            if target is None:
                # no cell there yet (Spirit's blank stack_buf): aim at where
                # the row will be once the write lands
                target = HeapView(self.tr, i_write, self.cfg).parts.get(("txt", dst))
            if target is None:
                continue
            flights.append(w.copy().animate.move_to(target).set_opacity(0))
        if flights:
            self.play(LaggedStart(*flights, lag_ratio=0.12), run_time=1.2)
        self.go(i_write)
        self.play(FadeOut(strip))

    def pulse(self, key, color=None):
        m = self.parts[key]
        self.play(Indicate(m, color=color or T.highlight, scale_factor=1.08))

    def note_at(self, key, text: str, color=None, side=RIGHT) -> Mobject:
        m = mono(text, 13, color or T.highlight).next_to(self.parts[key], side, buff=0.15)
        self.play(FadeIn(m, shift=-side * 0.1), run_time=0.5)
        return m

    def call(self, name: str, ok: bool = True, label: str | None = None):
        """The program calls through the pointer: an arrow from the pointer row
        to the symbol it names."""
        row = self.parts[("f", "fp", name)]
        color = T.win if ok else T.crash
        self.play(Indicate(row, color=color, scale_factor=1.06), run_time=0.8)
        self.play(Flash(row.get_right(), color=color, flash_radius=0.35))


def _wrap(s: str, w: int):
    import textwrap
    return textwrap.wrap(s, w)


# -- use-after-free: heap-16, adv-90, kern-105 all run VRIG's UAF_STEPS ---------

class UafLesson(HeapLesson):
    alloc_line = free_line = realloc_line = read_line = call_line = ""

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "poke"), code=self.alloc_line, say=self.cap_alloc)
        self.beat()
        self.pulse(("h", "txt", tr.state(self.cur)["names"]["User"] + tr.H))
        self.say(self.cap_ptr)
        self.beat()
        self.go(tr.find("step2", "free"), code=self.free_line, say=self.cap_free)
        self.beat()
        self.go(tr.find("step3", "malloc"), code=self.realloc_line, say=self.cap_realloc)
        self.beat()
        self.payload(tr.find("submit", "write"), code=self.read_line, say=self.cap_write)
        self.go(tr.find("submit", "result"), code=self.call_line, say=self.cap_call)
        self.call(list(tr.state(self.cur)["funcPtrs"])[0])
        self.beat()


class Heap16(UafLesson):
    trace_name = "heap-16"
    subtitle = "A freed struct gets recycled, and the old pointer still uses it."
    names = {"User": "u", "Note": "note"}
    fp_labels = {"action": "u->action()"}
    alloc_line, free_line, realloc_line = "User *u = malloc(16)", "free(u)", "char *note"
    read_line, call_line = "read(0, note", "u->action();"
    cap_alloc = "malloc(16) carves a 24-byte chunk off the top. 8 bytes of header, 16 for the struct."
    cap_ptr = "Its first word is action, which holds the address of greet()."
    cap_free = "free(u) puts the chunk in tcache. Its first word becomes the fd link, and u still points here."
    cap_realloc = "note asks for the same size, so tcache hands back the same chunk. u and note now share it."
    cap_write = "read() puts four bytes into note. That's win()'s address, little-endian."
    cap_call = "u->action() reads the first word of the chunk. It finds win()."


class Adv90(UafLesson):
    trace_name = "adv-90"
    subtitle = "Free a C++ object, reclaim its memory, and the next virtual call is yours."
    names = {"User": "w", "Note": "buf"}
    fp_labels = {"action": "w->action()"}
    alloc_line, free_line, realloc_line = "new Widget()", "delete w;", "char *buf"
    read_line, call_line = "read(0, buf", "UAF: reads"
    cap_alloc = "new Widget() takes a 24-byte chunk. The object's first word is its vptr."
    cap_ptr = "A virtual call goes through that first word. VRIG models it as the call target itself."
    cap_free = "delete w frees the chunk into tcache, but w still points at it."
    cap_realloc = "buf is the same size, so it lands on the old Widget."
    cap_write = "read() fills buf. The first four bytes sit where the vptr was."
    cap_call = "w->action() reads that word and jumps to win(). A real vptr points at a table, so a real exploit points it at a fake one."


class Kern105(UafLesson):
    trace_name = "kern-105"
    subtitle = "The kernel frees an object and keeps the pointer. A spray reclaims the slot."
    names = {"User": "obj", "Note": "spray"}
    fp_labels = {"action": "obj->callback()"}
    alloc_line, free_line, realloc_line = "obj = kmalloc", "kfree(obj);", "msgsnd()"
    read_line, call_line = "msgsnd()", "obj->callback();"
    cap_alloc = "vuln_open() kmallocs a 16-byte object. VRIG draws the slab with its glibc heap."
    cap_ptr = "The first word is callback, set to default_handler. VRIG's symbol for it is normal()."
    cap_free = "vuln_release() frees obj and never clears the pointer."
    cap_realloc = "A msgsnd() spray of the same size gets the freed slot back."
    cap_write = "The spray's first four bytes are win()'s address."
    cap_call = "The ioctl calls obj->callback(), which now reads win()."


# -- double free and tcache poisoning ------------------------------------------

class Heap17(HeapLesson):
    trace_name = "heap-17"
    subtitle = "Free the same chunk twice and the allocator hands it out twice."
    names = {"A": "a", "B": "b"}
    fp_at_table = True
    fp_labels = {"handler": "handler()"}

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "name"), code="char *a = malloc", say="a is one 24-byte chunk. handler() is a function pointer out in .data.")
        self.beat()
        self.go(tr.find("step1", "free"), code="free(a);", say="free(a) puts it in tcache[24]. The list ends at NULL.")
        self.beat()
        self.go(tr.find("step2", "free"), code="double free", say="free(a) again. glibc 2.27's tcache doesn't check, so A goes on the list twice and its fd points at itself.")
        self.beat()
        self.go(tr.find("step3", "malloc"), code="char *b = malloc", say="b = malloc(16) gets A back. A is in use and still on the free list.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="TARGET;", say="Writing through b rewrites the fd of a chunk tcache still holds. It now names the handler table.")
        self.go(tr.find("submit", "malloc"), code="returns a again", say="The next malloc returns A one more time. tcache's head is now {fp}.")
        self.beat()
        self.go(tr.find("submit", "result"), code="char *c = malloc", say="The malloc after that returns the handler table, and win() gets written there.")
        self.call("handler")
        self.beat()


class TcachePoison(HeapLesson):
    fp_at_table = True
    fp_labels = {"handler": "handler()"}
    names = {"A": "a", "B": "b"}
    free_line = "free(b);"
    write_line = "*(void**)b"
    c_line = "char *c"
    d_line = "char *d"
    init_line = "char *b = malloc"

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "name"), code=self.init_line, say=self.cap_init)
        self.beat()
        self.go(tr.find("step2", "free"), code=self.free_line, say=self.cap_free)
        self.beat()
        self.payload(tr.find("submit", "write"), code=self.write_line, say=self.cap_write)
        self.beat()
        self.go(tr.find("submit", "malloc"), code=self.c_line, say=self.cap_c)
        self.beat()
        self.go(tr.find("submit", "result"), code=self.d_line, say=self.cap_d)
        self.call("handler")
        self.beat()


class Heap2_19(TcachePoison):
    trace_name = "heap2-19"
    subtitle = "Overwrite a freed chunk's fd, and malloc returns any address you like."
    cap_init = "Two 24-byte chunks, a and b, side by side."
    cap_free = "free(b) puts b in tcache[24]. Its fd is NULL, the end of the list."
    cap_write = "b is freed, but the program still writes through it. The fd now says {fp}."
    cap_c = "c = malloc(16) takes b off the list. tcache follows b's fd, so the head is now the handler table."
    cap_d = "d = malloc(16) returns {fp} without a single check. *d = win overwrites handler."


class Ctf51(TcachePoison):
    trace_name = "ctf-51"
    subtitle = "Tcache poisoning into a function pointer hijack."
    init_line = "Obj *b"
    free_line = "free(b);"
    write_line = "next ptr"
    c_line = "malloc returns b"
    d_line = "Write win()"
    cap_init = "Two 16-byte objects, a and b. VRIG allocates both and frees only b."
    cap_free = "b goes into tcache[24] with fd NULL."
    cap_write = "Write the target address over b's next pointer."
    cap_c = "The first malloc returns b. The list head moves to the target."
    cap_d = "The second malloc returns {fp}. Writing win() there takes over handler()."


# -- overflow into the next chunk: heap-18, ctf-48, adv2-99 ------------------------

class OverflowLesson(HeapLesson):
    fp_labels = {"handler": "(*b)()"}
    names = {"A": "a", "B": "b"}
    init_line = read_line = call_line = ""

    def pre(self):
        pass

    def script(self):
        tr = self.tr
        self.pre()
        self.go(tr.find("init", "poke"), code=self.init_line, say=self.cap_init)
        self.beat()
        b = tr.state(self.cur)["names"]["B"]
        self.pulse(("h", "txt", b + tr.H))
        self.say(self.cap_ptr)
        self.beat()
        self.payload(tr.find("submit", "write"), code=self.read_line, say=self.cap_write)
        self.say(self.cap_after)
        self.beat()
        self.go(tr.find("submit", "result"), code=self.call_line, say=self.cap_call)
        self.call("handler")
        self.beat()


class Heap18(OverflowLesson):
    trace_name = "heap-18"
    subtitle = "Write past the end of one chunk and you're writing into the next."
    init_line, read_line, call_line = "void (**b)() = malloc", "read(0, a, 64)", "(*b)();"
    cap_init = "a and b are 24-byte chunks next to each other. Nothing sits between them."
    cap_ptr = "b's first word is a function pointer to normal()."
    cap_write = "read() takes up to 64 bytes into a's 16. The payload is 28."
    cap_after = "16 bytes fill a. The next 8 cover b's header, copied as it was. The last 4 are win()."
    cap_call = "(*b)() loads that word and calls win()."


class Ctf48(OverflowLesson):
    trace_name = "ctf-48"
    subtitle = "Free-form heap sandbox. Chunk a holds data, chunk b holds a function pointer."
    fp_labels = {"handler": "b->action()"}
    init_line, read_line, call_line = "b->action = normal", "Write to c", "b->action();"
    cap_init = "a holds a name, b holds action. They're adjacent 24-byte chunks."
    cap_ptr = "b->action points at normal()."
    cap_write = "VRIG plays this one as an overflow. The bytes go in at a and keep going."
    cap_after = "Fill a's 16 bytes, keep b's header, then win()."
    cap_call = "b->action() now calls win()."


class Adv2_99(OverflowLesson):
    trace_name = "adv2-99"
    subtitle = "Shape the heap first, so the buffer you overflow sits right below your target."
    names = {"A": "vuln_buf", "B": "handler"}
    fp_labels = {"handler": "(*handler)()"}
    init_line, read_line, call_line = "*handler = normal", "read(0, vuln_buf", "(*handler)();"
    cap_init = "VRIG skips the spray and starts from its result. vuln_buf sits directly below handler."
    cap_ptr = "handler's first word points at normal()."
    cap_write = "read() takes up to 128 bytes. VRIG sizes both chunks at 24 bytes, so 28 are enough."
    cap_after = "Fill vuln_buf, step over handler's header, then win()."
    cap_call = "(*handler)() calls win()."

    def pre(self):
        # a sketch of spray and holes, no addresses: VRIG doesn't simulate it
        slots = VGroup(*(Rectangle(0.42, 0.42).set_stroke(T.grid, 1.5).set_fill(T.chunk_user, 0.7) for _ in range(14)))
        slots.arrange(RIGHT, buff=0.06).move_to(RIGHT * 1.9 + UP * 0.3)
        tag = mono("sketch, not VRIG state", 14, T.text_dim).next_to(slots, UP, buff=0.3)
        self.play(LaggedStartMap(FadeIn, slots, lag_ratio=0.05), FadeIn(tag))
        self.say("Spray first. Many same-sized allocations make the layout predictable.")
        self.beat()
        holes = slots[1::2]
        self.play(*(h.animate.set_fill(T.freed_chunk, 0.3) for h in holes))
        self.say("Free every other one to punch holes of exactly that size.")
        self.beat()
        a, b = slots[9], slots[10]
        self.play(a.animate.set_fill(T.attacker_bytes, 0.9), b.animate.set_fill(T.chunk_user, 1).set_stroke(T.highlight, 3))
        self.say("The goal is a buffer you control landing right below the object you want to hit.")
        self.beat()
        self.play(FadeOut(slots), FadeOut(tag))


# -- fastbin dup ---------------------------------------------------------------------

class Heap2_20(HeapLesson):
    trace_name = "heap2-20"
    subtitle = "Get the same chunk into a fastbin twice, then point it anywhere."
    names = {"A": "a", "B": "b", **{f"t{i}": f"t[{i}]" for i in range(7)}}
    heap_cfg = {"mini": {f"t[{i}]" for i in range(7)}}
    fp_at_table = True
    fp_labels = {"handler": "handler()"}

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "name"), code="free(t[i])", say="Seven frees fill tcache[24]. That's as many as it holds. a and b were allocated before that.")
        self.beat()
        self.go(tr.find("step1", "free"), code="free(a);", say="tcache is full, so free(a) sends a to fastbin[24].")
        self.beat()
        self.go(tr.find("step2", "free"), code="free(b);", say="free(b) goes on top. fastbin[24] is b, then a.")
        self.beat()
        self.go(tr.find("step3", "free"), code="double free", say="free(a) again. fastbin only compares a with the head, which is b. So a goes in twice, and the list loops.")
        self.beat()
        self.go(tr.find("step4", "malloc", nth=6), code="Drain", say="Seven mallocs empty tcache. The next ones come from the fastbin.", run_time=1.5)
        self.beat()
        self.go(tr.find("submit", "malloc"), code="char *c", say="c = malloc(16) returns a. a is also still in the fastbin.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="*(void**)c", say="c writes the target over a's fd. The loop now leads out of the heap.")
        self.go(tr.find("submit", "malloc", nth=1), code="gets B", say="malloc returns b.")
        self.go(tr.find("submit", "malloc", nth=2), code="gets A again", say="malloc returns a again. The fastbin head is now {fp}.")
        self.beat()
        self.go(tr.find("submit", "result"), code="char *d", say="d = malloc(16) returns the handler table, and *d = win.")
        self.call("handler")
        self.beat()


# -- unsorted bin attack -------------------------------------------------------------

class Heap2_21(HeapLesson):
    trace_name = "heap2-21"
    subtitle = "Corrupt bk on an unsorted chunk, and malloc writes a pointer wherever bk says."
    names = {"A": "a", "guard": "guard"}
    fp_at_table = True
    fp_labels = {"handler": "handler()"}

    def script(self):
        tr = self.tr
        self.notes[tr.fp_addr - 8] = "handler - 8"
        self.go(tr.find("init", "name"), code="char *guard", say="a is 136 bytes, too big for a fastbin. guard keeps it from merging into top. This is glibc 2.23, no tcache.")
        self.beat()
        self.go(tr.find("step2", "free"), code="free(a);", say="free(a) puts a in the unsorted bin, a doubly linked list. bk points back at main_arena.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="TARGET - 8", say="Use after free on a's bk. Point it 8 bytes below handler, because fd sits 8 bytes into a chunk.")
        self.beat()
        self.go(tr.find("submit", "result"), code="char *b = malloc(128)", say="malloc(128) takes a off the list and writes main_arena into bk->fd. That's handler.")
        self.call("handler")
        self.say(f"The value written is main_arena, {h32(tr.main_arena)}. This exercise accepts any nonzero value.")
        self.beat()


# -- the houses. VRIG's generic submit never sets funcPtrs, so these end on a model ----

class HouseLesson(HeapLesson):
    fp_at_table = True
    fp_labels = {"handler": "handler()"}
    takeaway_head = "Takeaway"
    footnote = "VRIG's checker can't pass this one. Its submit only writes the bytes, and the steps tagged glibc model act out the rest."

    def outro(self):
        super().outro()
        note = prose("\n".join(_wrap(self.footnote, 90)), 15, T.text_dim).to_edge(DOWN, buff=0.35)
        self.play(FadeIn(note))
        self.beat(pause=2.0)


class Heap2_22(HouseLesson, Vrig3DScene):
    trace_name = "heap2-22"
    subtitle = "Make the top chunk huge, then one malloc moves it onto your target."
    names = {"A": "a"}
    takeaway_head = "House of Force"
    takeaway = ("Top's size is the only thing between malloc and every address. Set it to 0xffffffff and one "
                "request of the right size walks top all the way around the address space to the target.")

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "name"), code="char *a", say="a is 24 bytes. The top chunk starts right after it.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="0xFFFFFFFF", say="Overflow a into top's header. prev_size 0, size 0xffffffff.")
        self.say("Top now claims to cover all of memory, so no request is too big.")
        self.beat()
        self.race()
        self.go(tr.find("model", "call"), code="(*handler)()", say="*d = win, and handler() now calls win().")
        self.call("handler")
        self.beat()

    def race(self):
        tr = self.tr
        m = tr.raw["model"]
        top, target, evil, new_top = m["top"], m["target"], m["evil"], m["newTop"]
        self.focus("size_t evil")
        calc = VGroup(
            mono(f"top    = {h32(top)}", 18, T.top_chunk),
            mono(f"target = {h32(target)}", 18, T.attacker_bytes),
            mono(f"evil   = target - 8 - top - 8", 18, T.label),
            mono(f"       = {h32(evil)}", 18, T.highlight),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        plate = BackgroundRectangle(calc, buff=0.2).set_fill(T.background, 0.95)
        box = VGroup(plate, calc).to_edge(RIGHT, buff=0.4).shift(UP * 0.6).fix_in_frame()
        self.play(FadeIn(box))
        self.say("The target is below the heap, so evil is negative. As a size_t it's just under 4 GiB.")
        self.beat()

        # the 32-bit address space as a ring, viewed tilted
        self.unsay()
        others = [m_ for m_ in self.mobjects if m_ is not box]
        self.play(*(FadeOut(m_) for m_ in others), FadeOut(box))
        frame = self.frame
        R = 2.6
        ring = Circle(radius=R).set_stroke(T.grid, 6)
        ticks = VGroup()
        for k in range(16):
            a = k / 16 * TAU
            ticks.add(Line(R * 0.93 * np.array([np.cos(a), np.sin(a), 0]), R * 1.07 * np.array([np.cos(a), np.sin(a), 0])).set_stroke(T.grid, 2))
        self.play(frame.animate.reorient(0, 55, 0, center=(0, -0.9, 0), height=8.5), ShowCreation(ring), FadeIn(ticks), run_time=2)

        # address 0 at the bottom of the ring, counting up counterclockwise
        def ang(addr):
            return addr / 2 ** 32 * TAU - PI / 2

        def at(addr, r=R, nudge=0.0):
            a = ang(addr) + nudge
            return r * np.array([np.cos(a), np.sin(a), 0])

        # heap, handler and 0 sit within a few degrees of each other, so the
        # labels get pushed apart by hand: in, out, and along the ring
        def label(text, addr, color, r=R + 0.7, dz=0.0, nudge=0.0):
            t = mono(text, 20, color)
            t.move_to(at(addr, r, nudge) + OUT * dz)
            billboard(t, frame)
            return t

        zero = label("0x00000000 / 0xffffffff", 0, T.text_dim, r=R + 0.55, nudge=-12 * DEG)
        hi = VGroup()
        heap_dot = Dot(at(top), radius=0.11).set_fill(T.top_chunk)
        tgt_dot = Dot(at(target), radius=0.11).set_fill(T.attacker_bytes)
        heap_lab = label(f"top {h32(top)}", top, T.top_chunk, r=R + 1.1, nudge=16 * DEG)
        tgt_lab = label(f"handler {h32(target)}", target, T.attacker_bytes, r=R - 1.25, nudge=4 * DEG)
        self.play(FadeIn(zero), FadeIn(heap_dot), FadeIn(tgt_dot), FadeIn(heap_lab), FadeIn(tgt_lab))
        self.say(f"All 4 GiB as a ring. handler sits only {top - target:#x} bytes below the heap.")
        self.beat()

        # malloc(evil): top walks forward by evil, wrapping past 0xffffffff
        racer = Dot(at(top), radius=0.14).set_fill(T.top_chunk).set_stroke(T.highlight, 2)
        trail = TracedPath(racer.get_center, stroke_color=T.top_chunk, stroke_width=6)
        self.add(trail, racer)
        t = ValueTracker(0)
        racer.add_updater(lambda d: d.move_to(at((top + t.get_value() * (evil + 8)) % 2 ** 32, R)))
        self.say(f"malloc(evil) carves {h32(evil + 8)} bytes off top. Top walks the whole ring and stops just before handler.")
        self.play(t.animate.set_value(1), frame.animate.increment_theta(25 * DEG), run_time=5, rate_func=smooth)
        racer.clear_updaters()
        trail.clear_updaters()
        new_lab = label(f"new top {h32(new_top)}", new_top, T.highlight, r=R - 2.0, nudge=4 * DEG)
        self.play(Flash(racer.get_center(), color=T.highlight), FadeIn(new_lab))
        self.beat()
        self.say(f"Top's header is now at {h32(new_top)}. The next chunk's data starts 8 bytes later, on handler.")
        self.beat()
        ring_all = Group(ring, ticks, zero, hi, heap_dot, tgt_dot, heap_lab, tgt_lab, racer, trail, new_lab)
        self.play(FadeOut(ring_all), frame.animate.reorient(0, 0, 0, center=ORIGIN, height=FRAME_HEIGHT), run_time=1.5)
        self.play(*(FadeIn(m_) for m_ in others))


class Heap2_23(HouseLesson):
    trace_name = "heap2-23"
    subtitle = "Write a fake chunk header anywhere, free it, and malloc hands it back."
    takeaway_head = "House of Spirit"
    takeaway = ("free() trusts the size field it's given. A fake header in memory you control turns that memory "
                "into a chunk, and the next malloc of that size returns it.")
    footnote = ("VRIG never sets up a heap for this one, so its checker can't pass. The fake chunk and the tcache "
                "steps are a glibc model. In this exercise p ends up on the stack and never reaches handler.")

    def construct(self):
        tr = HeapTrace.load(self.trace_name)
        raw = dict(tr.raw)
        # stack_buf as its own 64-byte "heap", built from the model steps
        ops = []
        for o in tr.ops:
            if o["engine"] != "model":
                continue
            ex = o["state"]["extra"]
            fake = ex["fake"]
            st = {
                "chunks": [{"addr": 0, "size": fake["size"], "allocated": not fake["inTcache"], "prevInUse": True}],
                "top": {"addr": fake["size"], "size": 64 - fake["size"]},
                "bins": {"tcache": {k: [0] for k in ex.get("tcache", {})}, "fastbins": {}, "smallbins": {},
                         "largebins": {}, "unsorted": []},
                "funcPtrs": {}, "memory": ex["stackBuf"],
                "written": [1 if i < 8 else 0 for i in range(64)],
                "names": {"fake": 0}, "lastError": None, "extra": ex,
            }
            if o["op"] == "write-fake":
                o = {**o, "op": "write", "args": [0, o["args"][0]]}
            ops.append({**o, "state": st})
        blank = json.loads(json.dumps(ops[0]))
        blank["state"]["memory"] = [0] * 64
        blank["state"]["written"] = [0] * 64
        # before the header goes in there is no chunk at all, just stack
        blank["state"]["chunks"] = []
        blank["state"]["top"] = {"addr": 0, "size": 64}
        blank["state"]["names"] = {}
        blank["op"] = "start"
        blank["args"] = []
        ops.insert(0, blank)
        raw.update(ops=ops, base=0, heapSize=64)
        self.spirit_raw = raw
        super().construct()

    def script(self):
        tr = self.tr = HeapTrace(self.spirit_raw)
        tr.raw["solved"] = False
        self.cfg = fit(tr, HeapCfg(x=0.6, labels={"fake": "fake chunk"}, top_header=False,
                                   top_label="stack_buf, {size} B outside any chunk",
                                   fmt=lambda a: f"stack_buf+{a:#04x}"), top=self.heap_top)
        self.go(0, code="char stack_buf[64]", say="stack_buf is 64 bytes on the stack. malloc has never seen it.")
        self.beat()
        self.payload(1, code="= 0x19", say="Two words make it look like a chunk. prev_size 0, size 0x19, which is 24 with PREV_INUSE set.")
        self.beat()
        self.go(2, code="free(stack_buf + 8)", say="free(stack_buf + 8) reads that header, sees 24 bytes, and files it in tcache[24]. On 2.27 that path checks nothing else.")
        self.beat()
        self.go(3, code="char *p = malloc(16)", say="malloc(16) pops tcache[24] and returns stack_buf + 8. The allocator is now handing out stack memory.")
        self.beat()



class Heap2_24(HouseLesson):
    trace_name = "heap2-24"
    subtitle = "No free() anywhere. Shrink the top chunk and malloc frees it for you."
    names = {"A": "a"}
    takeaway_head = "House of Orange"
    takeaway = ("A request that doesn't fit makes sysmalloc retire the old top through the normal free path. "
                "Shrinking top's size is enough to get a free chunk out of a program that never calls free().")
    footnote = ("VRIG's checker can't pass this one. Its submit only writes the bytes, and the steps tagged glibc model "
                "act out the rest, including a bk write the exercise mentions but doesn't take as input.")

    def script(self):
        tr = self.tr
        self.notes[tr.fp_addr - 8] = "handler - 8"
        self.go(tr.find("init", "name"), code="char *a", say="One chunk, a, and the top chunk after it. There's no free() in this program.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="= 0x81", say="Overflow a into top's header. size becomes 0x81, a 0x80-byte top with PREV_INUSE set.")
        self.beat()
        self.go(tr.find("model", "sysmalloc"), code="char *b = malloc(256)", say="malloc(256) doesn't fit in 0x80. sysmalloc gets fresh memory and frees the old top. It lands in the unsorted bin.")
        self.beat()
        self.go(tr.find("model", "write-bk"), code="corrupt old top", say="The old top is a normal free chunk now. Point its bk 8 bytes below handler.")
        self.beat()
        self.go(tr.find("model", "malloc"), code="char *c = malloc(96)", say="malloc(96) takes it off the unsorted bin and writes main_arena into bk->fd, which is handler.")
        self.call("handler")
        self.beat()


class Heap2_25(HouseLesson):
    trace_name = "heap2-25"
    subtitle = "One null byte clears PREV_INUSE, and free() merges chunks that are still in use."
    names = {"A": "a", "B": "b", "C": "c", "guard": "guard", "d": "d"}
    heap_cfg = {"fold": 8}
    takeaway_head = "House of Einherjar"
    takeaway = ("free() decides whether to merge from PREV_INUSE and prev_size, both in the next chunk's header. "
                "An off-by-one null byte and a forged prev_size make it swallow live chunks, and the next malloc "
                "returns memory that overlaps them.")
    footnote = ("VRIG's checker can't pass this one. The merge and the malloc are a simplified glibc model. Real "
                "glibc also checks the merged chunk's fd and bk, and on 2.27 a 24-byte free goes to tcache first.")

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "name"), code="char *guard", say="a, b, c, and guard, four 24-byte chunks in a row.")
        self.beat()
        c = tr.state(self.cur)["names"]["C"]
        before = _le32(tr.state(self.cur)["memory"], c + 4)
        w = tr.find("submit", "write")
        self.payload(w, code="b[16] = 0x00", say="VRIG takes the bytes at a. They run through b and stop on the low byte of c's size.")
        after = _le32(tr.state(w)["memory"], c + 4)
        prev = _le32(tr.state(w)["memory"], c)
        # the source comment says 0x19 becomes 0x18. Nulling the low byte of
        # 0x19 actually leaves 0, which is what VRIG's memory shows
        self.pulse(("h", "txt", c + 4))
        self.say(f"The null byte turns c's size from {before:#x} into {after:#x}. PREV_INUSE is clear, and so is the size itself.")
        self.beat()
        self.say("Real attacks use sizes like 0x101, where the null byte only takes the flag.")
        self.beat()
        self.pulse(("h", "txt", c))
        self.say(f"prev_size says the free chunk behind c is {prev:#x} bytes. That reaches back to a.")
        self.beat()
        self.go(tr.find("model", "free"), code="free(c);", say="free(c) walks back 0x30 bytes to a and merges. One 72-byte free chunk now covers a, b, and c.")
        self.beat()
        self.go(tr.find("model", "malloc"), code="char *d = malloc(64)", say="d = malloc(64) gets that chunk. d overlaps a and b, which the program still uses.")
        self.beat()


class Heap2_26(HouseLesson):
    trace_name = "heap2-26"
    subtitle = "Fake a smallbin entry well enough to pass the bk->fd check."
    names = {"A": "a", "guard": "guard"}
    takeaway_head = "House of Lore"
    takeaway = ("Smallbin removal only checks that victim->bk->fd points back at the victim. Forge a fake chunk "
                "whose fd names the real one, link it in through bk, and malloc returns the fake.")
    footnote = ("VRIG's checker can't pass this one. On 2.27 its sim puts a in tcache, so the smallbin part is "
                "replayed on VRIG's HeapSim with glibc 2.23, and the last steps are a glibc model.")

    def script(self):
        tr = self.tr
        fake = tr.raw["model"]["fake"]
        self.notes[fake] = "fake chunk"
        self.go(tr.find("init", "name"), code="char *guard", say="a is 88 bytes, guard keeps it off the top.")
        self.beat()
        self.go(tr.find("step3", "malloc"), code="malloc(120)", say="On glibc 2.27, free(a) puts a in tcache[88]. VRIG's sim shows exactly that, though the comments say unsorted bin.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="a->bk = &fake_chunk", say="The use after free writes a's bk. It points at a fake chunk 8 bytes below handler.")
        self.beat()
        self.go(tr.find("model", "replay-2.23"), code="a is now in smallbin", say="Replayed on glibc 2.23, where tcache doesn't exist. free(a) and malloc(120) sort a into smallbin[88].")
        self.beat()
        lab = self.fake_chunk(fake, tr.raw["model"]["fake"])
        self.say("The fake chunk's fd points back at a. That's the one check smallbin removal does.")
        self.beat()
        self.go(tr.find("model", "malloc"), code="char *p1", say="p1 = malloc(80) takes a. The bin's next entry is now the fake chunk.")
        self.beat()
        self.go(tr.find("model", "malloc", nth=1), code="char *p2", say="p2 = malloc(80) returns the fake chunk's data, which is handler. *p2 = win.", also=[FadeOut(lab)])
        self.call("handler")
        self.beat()

    def fake_chunk(self, fake, _):
        tr = self.tr
        a = tr.state(self.cur)["names"]["A"]
        box = VGroup(
            mono(f"fake @ {h32(fake)}", 15, T.attacker_bytes),
            mono(f"fd = {h32(tr.base + a)}  (a)", 15, T.attacker_bytes),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
        plate = SurroundingRectangle(box, buff=0.12).set_stroke(T.attacker_bytes, 2).set_fill(T.background, 0.95)
        g = VGroup(plate, box).to_corner(DR, buff=0.4).shift(UP * 1.0)
        self.play(FadeIn(g, shift=LEFT * 0.2))
        return g


# -- the finals ------------------------------------------------------------------------

class Final27(HeapLesson):
    trace_name = "final-27"
    subtitle = "Four bugs in a row. Each one is harmless alone."
    names = {"buf": "buf", "cfg": "cfg"}
    fp_labels = {"handler": "cfg->handler()"}

    def script(self):
        tr = self.tr
        n = tr.raw["count"]
        self.focus("scanf")
        math = VGroup(
            mono(f"count     = {n}", 20, T.attacker_bytes),
            mono(f"count * 4 = {n * 4} = {n * 4:#x}", 20, T.label),
            mono(f"& 0xffff  = {(n * 4) & 0xffff}", 20, T.crash),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        math.move_to(RIGHT * 1.8 + UP * 1.0)
        self.play(FadeIn(math[0]))
        self.say(f"Bug one. VRIG keeps count * 4 in 16 bits, so {n} times 4 wraps to zero.")
        self.play(FadeIn(math[1], shift=DOWN * 0.1))
        self.play(FadeIn(math[2], shift=DOWN * 0.1))
        self.beat()
        self.play(FadeOut(math))
        self.go(tr.find("count", "malloc"), code="malloc(count * 4)", say="malloc of almost nothing still returns the smallest chunk, 16 bytes with 8 for data.")
        self.beat()
        self.go(tr.find("count", "poke"), code="Config *cfg", say="cfg lands right after buf. Its first word is handler, set to normal().")
        self.beat()
        leak = tr.state(self.cur)["extra"]["leak"]
        self.focus("DEBUG")
        self.say(f"Bug two. printf leaks cfg's address, {h32(leak)}. Now you know exactly where handler is.")
        self.beat()
        self.payload(tr.find("submit", "write"), code="read(0, buf, 256)", say="Bug three. read() takes 256 bytes into 8. Fill buf, keep cfg's header, then win().")
        self.beat()
        self.go(tr.find("submit", "result"), code="cfg->handler();", say="Bug four. cfg->handler() calls whatever is there.")
        self.call("handler")
        self.beat()


class Final28(HeapLesson):
    trace_name = "final-28"
    subtitle = "No labels, no hints. Find the bug and the target yourself."
    names = {f"ptr{i}": f"ptrs[{i}]" for i in range(4)}
    heap_cfg = {"fold": 2}
    fp_labels = {"fn": "ptrs[0]->fn()"}

    def script(self):
        tr = self.tr
        self.go(tr.find("init", "malloc", nth=3), code="ptrs[i] = malloc(32)", say="Four 40-byte chunks in a row.")
        self.beat()
        self.go(tr.find("init", "poke"), code="ptrs[0]->fn = normal", say="ptrs[0] holds fn, the pointer called at the end.")
        self.go(tr.find("init", "name"), code="free(ptrs[2])", say="ptrs[1] and ptrs[2] get freed. tcache[40] is ptrs[2], then ptrs[1].")
        self.beat()
        self.say("ptrs[2] is freed but the program still reads into it. That's the bug.")
        self.payload(tr.find("submit", "write"), code="read(0, ptrs[2], 32)", say="Aim its fd at ptrs[0]'s data, where fn lives. That address is the heap base plus 8.")
        self.beat()
        self.go(tr.find("submit", "malloc"), code="void *x", say="x = malloc(32) takes ptrs[2]. tcache's head follows the fd to ptrs[0].")
        self.beat()
        self.go(tr.find("submit2", "call"), code="read(0, y, 4)", say="y = malloc(32) is ptrs[0]'s data. read(0, y, 4) writes win() over fn. VRIG sets fn directly here.")
        self.call("fn")
        self.beat()


import json  # noqa: E402  (Heap2_23 rebuilds its own trace)


def _le32(mem, off):
    return int.from_bytes(bytes(mem[off:off + 4]), "little")
