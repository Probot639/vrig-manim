// Heap walkthrough exercises (mode 'step', vizMode 'heap'). Replays each
// exercise's guided steps the way StepControls.handleStep does and dumps the
// whole heap after every click: chunks, raw headers, bins, top, logs.
//
//   node dist/vrig-walk_heap.mjs            # writes every id below to traces/
//   node dist/vrig-walk_heap.mjs heap-15    # one id, to stdout

import { writeFileSync } from 'node:fs';
import { getExercise } from '@/exercises/registry';
import { HeapSim } from '@/engine/simulators/HeapSim';
import { WinHeapSim } from '@/engine/simulators/WinHeapSim';
import { KernelSim } from '@/engine/simulators/KernelSim';
import { AuxViz } from '@/engine/simulators/AuxViz';

const IDS = [
  'c-06', 'heap-15',
  'hint-53', 'hint-54', 'hint-55', 'hint-56', 'hint-57', 'hint-58',
  'whint-59', 'whint-60', 'whint-61', 'whint-62',
  'adv-87', 'adv2-96', 'kern-107',
  'glibc-108', 'glibc-109', 'glibc-110',
];

// WinHeapSim takes its encoding key and LFH slot order from Math.random.
// Pin it so the video and the trace agree run to run.
const SEED = 0x3a7d90e5;  // arbitrary, just has to stay fixed
function seedRandom(seed: number) {
  let s = seed >>> 0;
  Math.random = () => {
    // mulberry32
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const strip = (s: string) => s.replace(/<[^>]+>/g, '');

// Exercises call heap.highlightChunk?.(), annotateField?.(), writeData?.() and
// friends. Neither sim has them, so in the app they do nothing. Record what
// was asked for anyway, the annotation strings are useful labels.
const WISHES = ['clear', 'highlightChunk', 'highlightField', 'annotateField', 'writeData'];

function recorder(heap: any, wishes: any[]) {
  return new Proxy(heap, {
    get(target, prop, recv) {
      if (typeof prop === 'string' && WISHES.includes(prop) && !(prop in target)) {
        return (...args: any[]) => { wishes.push([prop, ...args]); };
      }
      return Reflect.get(target, prop, recv);
    },
    set(target, prop, value) {
      return Reflect.set(target, prop, value);
    },
  });
}

function makeHeap(ex: any, sizeOverride?: number) {
  const size = sizeOverride ?? ex.heapSize ?? 256;
  return ex.winVersion
    ? new WinHeapSim(size, ex.winVersion)
    : new HeapSim(size, ex.glibcVersion ?? '2.27');
}

function snap(heap: any, names: Record<string, number>) {
  const win = heap instanceof WinHeapSim;
  const chunks = heap.getChunksForDisplay().map((c: any) => {
    const raw = heap.read(c.addr, Math.min(c.size, heap.memorySize - c.addr));
    const out: any = {
      ...c,
      prevSizeField: heap._readLE(c.addr, 4),
      sizeField: heap._readLE(c.addr + 4, 4),
      fd: heap._readLE(c.dataStart, 4),
      bk: heap._readLE(c.dataStart + 4, 4),
      names: Object.entries(names).filter(([, a]) => a === c.addr).map(([n]) => n),
      bytes: raw,
    };
    if (win) {
      out.decoded = heap._readHeapEntry(c.addr);
      out.valid = heap.validateHeader(c.addr);
      out.lfh = heap.chunks.get(c.addr)?.lfh ?? false;
    } else {
      out.prevInUse = heap.chunks.get(c.addr)?.prevInUse;
      if (heap.hasSafeLinking) out.fdRevealed = heap._revealPtr(c.dataStart, out.fd);
    }
    return out;
  });
  const s: any = {
    chunks,
    // getFreeLists() copies the record but shares the bin arrays, which keep
    // mutating. Deep copy or every step ends up showing the final bins.
    freeLists: JSON.parse(JSON.stringify(heap.getFreeLists())),
    top: { addr: heap.topAddr, size: heap.topSize },
    highlight: heap.highlight,
    memory: Array.from(heap.memory),
    written: Array.from(heap.written),
    lastError: heap.lastError,
    names: { ...names },
  };
  if (win) s.activationCounts = { ...heap.activationCounts };
  return s;
}

// StepControls.handleStep, minus React. stackSim is null for these (vizMode
// heap, mode step), auxViz is a fresh AuxViz like ExerciseContext makes.
function walk(ex: any, heap: any) {
  const names: Record<string, number> = {};
  const aux = new AuxViz();
  const steps: any[] = [];
  const allWishes: any[] = [];
  const h = recorder(heap, allWishes);

  for (let i = 0; i < ex.steps.length; i++) {
    const step = ex.steps[i];
    const wishes: any[] = [];
    allWishes.length = 0;
    let ret: any = null;

    if (step.action === 'malloc') {
      if (step.size != null) {
        ret = heap.malloc(step.size);
        if (ret && step.name) names[step.name] = ret.addr;
      }
    } else if (step.action === 'free') {
      if (step.name) {
        const addr = names[step.name];
        if (addr !== undefined) ret = heap.free(addr);
      }
    }
    const logs = [{ cls: step.log[0], msg: strip(step.log[1]) }];
    if (step.vizAction) step.vizAction(null, h, aux);
    wishes.push(...allWishes);

    // some exercises keep their names on heap._nameMap instead of heapNames
    const merged = { ...(heap._nameMap ?? {}), ...names };
    steps.push({
      index: i,
      action: step.action ?? null,
      name: step.name ?? null,
      size: step.size ?? null,
      srcLine: step.srcLine ?? null,
      done: !!step.done,
      result: ret,
      logs,
      wishes,
      ...snap(heap, merged),
    });
  }
  return steps;
}

function exportOne(id: string) {
  seedRandom(SEED);
  const ex: any = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  const heap: any = makeHeap(ex);
  const initial = snap(heap, {});
  const steps = walk(ex, heap);

  // StepControls dispatches EXERCISE_COMPLETED once the last step runs, and
  // these exercises have nothing else to win. check() is recorded too, it's
  // `() => true` for the glibc-bypass ones and `false` for the rest.
  const completed = steps.length === ex.steps.length;
  const checkResult = !!ex.check(null, heap, {}, {});

  const out: any = {
    exercise: ex.id,
    unit: ex.unitId,
    title: ex.title,
    desc: strip(ex.desc),
    source: ex.source.c.map((l: any) => l.text),
    sim: ex.winVersion ? 'WinHeapSim' : 'HeapSim',
    heapSize: heap.memorySize,
    glibcVersion: ex.winVersion ? null : heap.glibcVersion,
    winVersion: ex.winVersion ?? null,
    baseAddr: heap.baseAddr,
    headerSize: heap.HEADER_SIZE,
    mainArena: heap.mainArena ?? null,
    tcacheKeyAddr: heap.tcacheKeyAddr ?? null,
    encodingKey: heap.encodingKey ?? null,
    seed: ex.winVersion ? SEED : null,
    showLabels: ex.showLabels !== false,
    initial,
    steps,
    completed,
    check: checkResult,
    solved: completed,
    winTitle: ex.winTitle,
    winMsg: strip(ex.winMsg),
    extra: {},
  };
  out.extra = extras(ex, out);
  return out;
}

// Things the exercise talks about but never clicks. Each one runs VRIG's own
// sim code, on a separate instance unless noted, and is kept apart from steps.
function extras(ex: any, out: any): any {
  const x: any = {};
  const nameAddr = (step: any, n: string) => step.names[n];

  if (ex.id === 'c-06') {
    // the strcpy step has no vizAction, so the sim never holds "hello"
    const line = out.source.find((l: string) => l.includes('strcpy('));
    const m = line && line.match(/"([^"]*)"/);
    x.strcpy = { text: m ? m[1] : null, simWrote: false };
  }

  if (ex.id === 'glibc-108') {
    // step 3 only logs "attempting free(a) again". Ask the sim for real, on a
    // replay up to that point: it refuses and sets lastError.
    seedRandom(SEED);
    const heap: any = makeHeap(ex);
    walkUntil(ex, heap, 3);
    const a = heap._nameMap.A;
    const before = Array.from(heap.memory);
    const ok = heap.free(a);
    x.doubleFreeProbe = {
      returned: ok,
      lastError: heap.lastError,
      memoryUnchanged: before.every((b, i) => b === heap.memory[i]),
      tcache: JSON.parse(JSON.stringify(heap.getFreeLists().tcache)),
    };
  }

  if (ex.id === 'glibc-109') {
    const last = out.steps[out.steps.length - 1];
    const heap: any = makeHeap(ex);
    const pos = (n: string) => nameAddr(last, n) + heap.HEADER_SIZE;
    const a = last.chunks.find((c: any) => c.addr === nameAddr(last, 'A'));
    const b = last.chunks.find((c: any) => c.addr === nameAddr(last, 'B'));
    x.safeLinking = {
      aData: pos('A'), bData: pos('B'),
      aVaddr: heap.baseAddr + pos('A'), bVaddr: heap.baseAddr + pos('B'),
      aKey: ((heap.baseAddr + pos('A')) >>> 12) >>> 0,
      bKey: ((heap.baseAddr + pos('B')) >>> 12) >>> 0,
      aFdStored: a.fd, bFdStored: b.fd,
      aFdRevealed: heap._revealPtr(pos('A'), a.fd),
      bFdRevealed: heap._revealPtr(pos('B'), b.fd),
    };
  }

  if (ex.id === 'glibc-110') {
    // the last step describes free(C) but never calls it. Call it.
    seedRandom(SEED);
    const heap: any = makeHeap(ex);
    walkUntil(ex, heap, ex.steps.length);
    const c = heap._nameMap.C;
    const ok = heap.free(c);
    const names = { ...heap._nameMap };
    x.freeC = { returned: ok, ...snap(heap, names) };
  }

  if (ex.id === 'whint-60') {
    // UserBlocks for 40-byte slots is 32 * 40 = 1280 bytes. After 17 back-end
    // allocs a 1024-byte heap has 344 left, so _activateLfhBucket bails and
    // alloc #18 comes off the top like the rest. Same steps on 2 KB shows the
    // activation the exercise describes.
    const first = out.steps.find((s: any) => s.name === 'A18');
    x.lfhInExerciseHeap = first.chunks.some((c: any) => c.lfh);
    seedRandom(SEED);
    const heap: any = makeHeap(ex, 2048);
    x.bigHeap = { heapSize: 2048, encodingKey: heap.encodingKey, steps: walk(ex, heap) };
  }

  if (ex.id === 'whint-62') {
    // corrupt A's header the naive way (plain bytes, no XOR) and ask the sim
    // if it still validates. Separate instance, same seed, so same key.
    seedRandom(SEED);
    const heap: any = makeHeap(ex);
    walkUntil(ex, heap, 2);
    const a = heap._nameMap?.A ?? 0;
    const before = heap.read(a, 8);
    const validBefore = heap.validateHeader(a);
    // what an overflow writes if it doesn't know the key: a plaintext header
    // that would be valid unencoded. Size 2 units, BUSY, tag = 2 ^ 0 ^ 1,
    // PreviousSize 3 (A's real neighbour size)
    const naive = [0x02, 0x00, 0x01, 0x03, 0x03, 0x00, 0x00, 0x00];
    heap.write(a, naive);
    x.corrupt = {
      encodingKey: heap.encodingKey,
      before, validBefore,
      naive, decodedNaive: heap._readHeapEntry(a), validAfter: heap.validateHeader(a),
    };
  }

  if (ex.id === 'kern-107') {
    // The exercise runs on HeapSim and never frees anything. KernelSim has the
    // slab allocator the UAF story needs, so show the reuse there.
    const k = new KernelSim();
    const note = k.kmalloc(16)!;
    const freed = k.kfree(note.addr);
    const spray = k.kmalloc(16)!;
    x.slab = {
      note, freed, spray, sameAddr: note.addr === spray.addr,
      modprobePath: k.modprobePath,
      cacheObjects: k.slabs[note.slabClass].objects.length,
    };
  }

  return x;
}

function walkUntil(ex: any, heap: any, n: number) {
  walk({ ...ex, steps: ex.steps.slice(0, n) }, heap);
}

const only = process.argv[2];
if (only) {
  console.log(JSON.stringify(exportOne(only)));
} else {
  const dir = process.argv[3] ?? 'traces';
  for (const id of IDS) {
    const t = exportOne(id);
    writeFileSync(`${dir}/${id}.json`, JSON.stringify(t));
    console.error(`${id}: ${t.steps.length} steps, completed=${t.completed} check=${t.check}`);
  }
}
