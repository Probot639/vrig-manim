// Heap traces for the glibc heap lessons (unit4, unit5, the heap CTFs, the two
// finals, adv-90, adv2-99, kern-105). Drives a real HeapSim through the same
// calls VRIG's page makes: the mount-time setup from ExercisePageClient, each
// guided Step from HeapStepEngine, then the Submit handler, and snapshots the
// whole heap after every malloc/free/write.
//
//   node dist/vrig-heap.mjs <outdir>            # every exercise below
//   node dist/vrig-heap.mjs <outdir> heap2-22   # just one
//
// Payloads are built from the sim's own layout and symbols, never typed in.
//
// House of Force/Spirit/Orange/Einherjar/Lore can't be won in VRIG: they go
// through heapGenericSubmit, which never touches heap.funcPtrs, so check()
// stays false. Those traces record solved:false, then carry on with "model"
// steps that act out the rest of the technique on the same HeapSim object.
// Every op says which engine produced it.

import { writeFileSync } from 'fs';
import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { HeapSim } from '@/engine/simulators/HeapSim';
import { hex8 } from '@/engine/helpers';
import {
  UAF_STEPS, DF_STEPS, TCP_STEPS, FBD_STEPS, USB_STEPS,
  HOF_STEPS, HOS_STEPS, HOO_STEPS, HOE_STEPS, HOL_STEPS,
  executeHeapGuidedStep, HeapGuidedStep,
  heapUafSubmit, heapDoubleFreeSubmit, heapOverflowSubmit,
  heapTcachePoisonSubmit, heapFastbinDupSubmit, heapUnsortedBinSubmit,
} from '@/engine/execution/HeapStepEngine';

const IDS = ['heap-16', 'heap-17', 'heap-18', 'heap2-19', 'heap2-20', 'heap2-21', 'heap2-22',
  'heap2-23', 'heap2-24', 'heap2-25', 'heap2-26', 'ctf-48', 'ctf-51', 'final-27', 'final-28',
  'adv-90', 'adv2-99', 'kern-105'];

const [outdir = 'traces', only] = process.argv.slice(2);

const strip = (s: string) => (s ?? '').replace(/<[^>]+>/g, '');
const le32 = (v: number) => [0, 8, 16, 24].map(s => (v >>> s) & 0xff);

// none of these exercises turn on ASLR, so computeSymbols() is just a copy
const symbols: Record<string, number> = { ...BASE_SYMBOLS };

// same switch as getStepsForMode() in HeapStepInput.tsx (not exported)
function stepsFor(mode: string): HeapGuidedStep[] {
  return ({
    'heap-uaf': UAF_STEPS, 'heap-double-free': DF_STEPS, 'heap-tcache-poison': TCP_STEPS,
    'heap-fastbin-dup': FBD_STEPS, 'heap-unsorted-bin': USB_STEPS, 'heap-house-force': HOF_STEPS,
    'heap-house-spirit': HOS_STEPS, 'heap-house-orange': HOO_STEPS, 'heap-house-einherjar': HOE_STEPS,
    'heap-house-lore': HOL_STEPS,
  } as Record<string, HeapGuidedStep[]>)[mode] ?? [];
}

class Rec {
  ops: any[] = [];
  group = 'init';
  engine = 'vrig';
  names: Record<string, number> = {};
  extra: any = {};
  quiet = false;
  constructor(public heap: any) {
    for (const m of ['malloc', 'free', 'write']) {
      const orig = heap[m].bind(heap);
      heap[m] = (...args: any[]) => {
        const ret = orig(...args);
        if (!this.quiet) this.snap(m, args, ret);
        return ret;
      };
    }
  }

  state() {
    const h = this.heap;
    const fl = h.getFreeLists();
    const copyBins = (b: Record<number, number[]>) =>
      Object.fromEntries(Object.entries(b).filter(([, v]) => v.length).map(([k, v]) => [k, [...v]]));
    return {
      chunks: h.getChunksForDisplay().map((c: any) => ({
        addr: c.addr, size: c.size, allocated: c.allocated, prevInUse: c.prevInUse,
      })),
      top: { addr: h.topAddr, size: h.topSize },
      bins: {
        tcache: copyBins(fl.tcache), fastbins: copyBins(fl.fastbins),
        smallbins: copyBins(fl.smallbins), largebins: copyBins(fl.largebins), unsorted: [...fl.unsorted],
      },
      funcPtrs: JSON.parse(JSON.stringify(h.funcPtrs)),
      memory: Array.from(h.memory),
      written: Array.from(h.written),
      names: { ...this.names },
      lastError: h.lastError,
      extra: JSON.parse(JSON.stringify(this.extra)),
    };
  }

  snap(op: string, args: any[] = [], ret: any = null, logs: any[] = []) {
    this.ops.push({
      group: this.group, engine: this.engine, op,
      args: args.map(a => Array.isArray(a) ? [...a] : a), ret, logs, state: this.state(),
    });
  }

  // attach logs to the newest op of the current group, or a no-op record
  log(logs: any[], srcLine?: number, text?: string) {
    const last = this.ops[this.ops.length - 1];
    if (last && last.group === this.group && !last.logs.length) {
      last.logs = logs;
      if (srcLine !== undefined) last.srcLine = srcLine;
    } else {
      this.snap('step', [], null, logs);
      if (srcLine !== undefined) this.ops[this.ops.length - 1].srcLine = srcLine;
    }
  }
}

const L = (logs: any[]) => logs.map((l: any) => ({ cls: l.cls, msg: strip(l.msg) }));

// mount-time setup, copied from ExercisePageClient.tsx (it lives in a React effect)
function setup(ex: any, heap: any, rec: Rec, sourceOrder = false) {
  const name = (n: string, a: number) => { rec.names[n] = a; };
  switch (ex.mode) {
    case 'heap-uaf': {
      const u = heap.malloc(16);
      name('User', u.addr);
      heap._writeLE(u.dataAddr, symbols.normal, 4);
      heap.funcPtrs['action'] = { original: symbols.normal, current: symbols.normal };
      rec.snap('poke', [u.dataAddr, symbols.normal]);
      break;
    }
    case 'heap-double-free': {
      const a = heap.malloc(16);
      heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.normal };
      name('A', a.addr);
      rec.snap('name', ['A']);
      break;
    }
    case 'heap-overflow': {
      const a = heap.malloc(16);
      const b = heap.malloc(16);
      heap._writeLE(b.dataAddr, symbols.normal, 4);
      heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.normal };
      name('A', a.addr); name('B', b.addr);
      rec.snap('poke', [b.dataAddr, symbols.normal]);
      break;
    }
    case 'heap-tcache-poison': {
      const a = heap.malloc(16);
      const b = heap.malloc(16);
      name('A', a.addr); name('B', b.addr);
      rec.snap('name', ['A', 'B']);
      break;
    }
    case 'heap-fastbin-dup': {
      if (sourceOrder) {
        // The C source frees t[] and then mallocs a and b, which would pull
        // them straight back out of tcache. Allocate a and b before filling
        // tcache instead (how2heap's order), so free(a) really reaches a fastbin
        const t = [];
        for (let i = 0; i < 7; i++) { t.push(heap.malloc(16)); name('t' + i, t[i].addr); }
        const a = heap.malloc(16);
        const b = heap.malloc(16);
        name('A', a.addr); name('B', b.addr);
        for (let i = 0; i < 7; i++) heap.free(t[i].addr);
        rec.snap('name', ['A', 'B']);
        break;
      } else {
        // what the page does. Each malloc gets the chunk the last free just
        // put back, so tcache never holds more than one entry
        for (let i = 0; i < 7; i++) {
          const tmp = heap.malloc(16);
          if (tmp) heap.free(tmp.addr);
        }
      }
      const a = heap.malloc(16);
      const b = heap.malloc(16);
      name('A', a.addr); name('B', b.addr);
      rec.snap('name', ['A', 'B']);
      break;
    }
    case 'heap-unsorted-bin': {
      const a = heap.malloc(128);
      const g = heap.malloc(16);
      name('A', a.addr); name('guard', g.addr);
      rec.snap('name', ['A', 'guard']);
      break;
    }
    case 'heap-house-force':
    case 'heap-house-orange': {
      const a = heap.malloc(16);
      name('A', a.addr);
      rec.snap('name', ['A']);
      break;
    }
    case 'heap-house-einherjar': {
      for (const n of ['A', 'B', 'C', 'guard']) name(n, heap.malloc(16).addr);
      rec.snap('name', ['A', 'B', 'C', 'guard']);
      break;
    }
    case 'heap-house-lore': {
      name('A', heap.malloc(80).addr);
      name('guard', heap.malloc(16).addr);
      rec.snap('name', ['A', 'guard']);
      break;
    }
    case 'final-blind': {
      const ptrs = [];
      for (let i = 0; i < 4; i++) ptrs.push(heap.malloc(32));
      heap._writeLE(ptrs[0].dataAddr, symbols.normal, 4);
      heap.funcPtrs['fn'] = { original: symbols.normal, current: symbols.normal };
      rec.snap('poke', [ptrs[0].dataAddr, symbols.normal]);
      heap.free(ptrs[1].addr);
      heap.free(ptrs[2].addr);
      ptrs.forEach((p, i) => name('ptr' + i, p.addr));
      rec.snap('name', ['ptr0', 'ptr1', 'ptr2', 'ptr3']);
      break;
    }
    // heap-house-spirit has no branch at all, so the page starts on an empty heap
  }
}

function guided(ex: any, heap: any, rec: Rec) {
  const steps = stepsFor(ex.mode);
  steps.forEach((step, i) => {
    rec.group = 'step' + i;
    const r = executeHeapGuidedStep(step, heap, rec.names);
    rec.names = { ...r.heapNames };
    rec.log(L(r.logs), step.srcLine);
    rec.ops[rec.ops.length - 1].state.names = { ...rec.names };
  });
}

// heapGenericSubmit() from HeapStepInput.tsx, not exported. Same logic.
function genericSubmit(bytes: number[], heap: any, names: Record<string, number>, ex: any) {
  const result = { logs: [] as any[], completed: false };
  const a = names['A'];
  if (a !== undefined) {
    heap.write(a + heap.HEADER_SIZE, bytes);
    result.logs.push({ cls: 'action', msg: 'Wrote ' + bytes.length + ' bytes.' });
    if (ex.check(null, heap, symbols, {})) {
      result.logs.push({ cls: 'success', msg: 'Exercise completed!' });
      result.completed = true;
    }
  }
  return result;
}

// a constant out of the exercise's own C source, e.g. "*(size_t*)(a+20) = 0x81;"
function srcConst(ex: any, re: RegExp): number {
  for (const l of ex.source.c) {
    const m = l.text.match(re);
    if (m) return parseInt(m[1], 16) >>> 0;
  }
  throw new Error(ex.id + ': no source line matches ' + re);
}

// Filler for the data part of a chunk. Ordinary text a program would keep in
// a name buffer, so it reads like real heap contents and not like a marker.
const FILL = Array.from(Buffer.from('guest_session_01'));
const filler = (n: number, from = 0) => Array.from({ length: n }, (_, k) => FILL[(from + k) % FILL.length]);

// overflow from one chunk's data to the start of another's: keep every header
// byte in between as it is, fill the data, then drop the value on top
function overflowTo(heap: any, fromData: number, toData: number, value: number) {
  const out = [];
  let k = 0;
  for (let off = fromData; off < toData; off++) {
    const inHeader = [...heap.chunks.keys()].some((c: number) => off >= c && off < c + heap.HEADER_SIZE);
    if (inHeader) {
      out.push(heap.memory[off]);
      k = 0;
    } else {
      out.push(FILL[k++ % FILL.length]);
    }
  }
  return [...out, ...le32(value)];
}

function run(id: string) {
  const ex: any = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  const funcPtrAddr = ex.funcPtrAddr ?? 0x0804a040;  // HeapStepInput's default
  const sourceOrder = ex.mode === 'heap-fastbin-dup';

  const heap: any = new HeapSim(ex.heapSize ?? 256, ex.glibcVersion ?? '2.27');
  const rec = new Rec(heap);
  setup(ex, heap, rec, sourceOrder);
  guided(ex, heap, rec);

  rec.group = 'submit';
  const payloads: number[][] = [];
  let result: any = null;
  let count: number | null = null;
  const names = rec.names;

  switch (ex.mode) {
    case 'heap-uaf':
      payloads.push(le32(symbols.win));
      result = heapUafSubmit(payloads[0], heap, names, symbols);
      break;
    case 'heap-double-free':
      payloads.push(le32(funcPtrAddr));
      result = heapDoubleFreeSubmit(payloads[0], heap, names, symbols, funcPtrAddr);
      break;
    case 'heap-overflow': {
      const H = heap.HEADER_SIZE;
      payloads.push(overflowTo(heap, names.A + H, names.B + H, symbols.win));
      result = heapOverflowSubmit(payloads[0], heap, names, symbols);
      break;
    }
    case 'heap-tcache-poison':
      payloads.push(le32(funcPtrAddr));
      result = heapTcachePoisonSubmit(payloads[0], heap, names, symbols, funcPtrAddr);
      break;
    case 'heap-fastbin-dup':
      payloads.push(le32(funcPtrAddr));
      result = heapFastbinDupSubmit(payloads[0], heap, names, symbols, funcPtrAddr);
      break;
    case 'heap-unsorted-bin':
      // unlink writes to bk->fd, and fd sits 8 bytes into a chunk
      payloads.push(le32((funcPtrAddr - 8) >>> 0));
      result = heapUnsortedBinSubmit(payloads[0], heap, names, symbols, funcPtrAddr);
      break;
    case 'final-chain':
      result = finalChain(ex, heap, rec, payloads);
      count = result.count;
      break;
    case 'final-blind':
      result = finalBlind(ex, heap, rec, payloads);
      break;
    default:
      payloads.push(housePayload(ex, heap, names, funcPtrAddr));
      result = genericSubmit(payloads[0], heap, names, ex);
  }
  // submit handlers set funcPtrs after their last heap call, so snap once more
  rec.group = rec.group === 'submit2' ? 'submit2' : 'submit';
  rec.snap('result', [], null, L(result.logs));

  const check = !!ex.check(null, heap, symbols, {});
  const completed = !!result.completed;

  // the houses keep going on a model, see the header comment
  rec.engine = 'model';
  rec.group = 'model';
  const model = MODELS[ex.mode]?.(ex, heap, rec, funcPtrAddr);

  // fastbin-dup: also run the page's own setup so the trace shows both
  let pageSetup: any = null;
  if (sourceOrder) {
    const h2: any = new HeapSim(ex.heapSize ?? 256, ex.glibcVersion ?? '2.27');
    const r2 = new Rec(h2);
    setup(ex, h2, r2, false);
    guided(ex, h2, r2);
    const res2 = heapFastbinDupSubmit(le32(funcPtrAddr), h2, r2.names, symbols, funcPtrAddr);
    pageSetup = {
      completed: !!res2.completed, check: !!ex.check(null, h2, symbols, {}),
      afterGuided: r2.ops.filter(o => o.group.startsWith('step')).map(o => o.state.bins),
    };
  }

  const out = {
    exercise: ex.id, unit: ex.unitId, title: strip(ex.title), desc: strip(ex.desc),
    mode: ex.mode, vizMode: ex.vizMode, glibc: heap.glibcVersion, heapSize: heap.memorySize,
    base: heap.baseAddr, header: heap.HEADER_SIZE, mainArena: heap.mainArena,
    funcPtrAddr, symbols, source: ex.source.c.map((l: any) => l.text),
    guided: stepsFor(ex.mode).map(s => ({ srcLine: s.srcLine ?? null, log: (s.log ?? []).map(([c, m]) => [c, strip(m)]) })),
    payloads, count,
    // VRIG pops its success banner on result.completed. check() is only
    // consulted by heapGenericSubmit, so the two can disagree (ctf-48, kern-105)
    completed, check, solved: completed,
    sourceOrderSetup: sourceOrder, pageSetup,
    model: model ?? null,
    winTitle: strip(ex.winTitle), winMsg: strip(ex.winMsg),
    ops: rec.ops,
  };
  writeFileSync(`${outdir}/${id}.json`, JSON.stringify(out));
  console.error(`${id}: ${rec.ops.length} ops, completed=${completed} check=${check}`);
}

function housePayload(ex: any, heap: any, names: Record<string, number>, fp: number): number[] {
  const H = heap.HEADER_SIZE;
  switch (ex.mode) {
    case 'heap-house-force':
    case 'heap-house-orange': {
      // fill a, then the top chunk's header: prev_size 0, size from the source
      const size = srcConst(ex, /\(a\+20\) = (0x[0-9a-f]+)/i);
      const dataSize = heap.chunks.get(names.A).size - H;
      return [...filler(dataSize), ...le32(0), ...le32(size)];
    }
    case 'heap-house-einherjar': {
      // from a's data up to and including the low byte of c's size: keep b's
      // header, set c's prev_size from the source, null the size's low byte
      const prev = srcConst(ex, /\(c-8\) = (0x[0-9a-f]+)/i);
      const bytes = overflowTo(heap, names.A + H, names.C, prev);
      bytes.push(0x00);
      return bytes;
    }
    case 'heap-house-lore': {
      // a is freed, so its data starts with fd. bk is the next word
      return [...heap.read(names.A + H, 4), ...le32((fp - 8) >>> 0)];
    }
    case 'heap-house-spirit': {
      // prev_size 0, size = malloc(16)'s chunk size with PREV_INUSE
      return [...le32(0), ...le32(heap._alignSize(16) | 1)];
    }
  }
  return [];
}

// FinalChainInput.tsx, doCount() then doSubmit(). Same arithmetic.
function finalChain(ex: any, heap: any, rec: Rec, payloads: number[][]) {
  const logs: any[] = [];
  // smallest count whose count*4 wraps the 16 bits VRIG keeps
  const count = 0x10000 / 4;
  const allocSize = (count * 4) & 0xFFFF;
  logs.push({ cls: 'action', msg: 'count = ' + count + ', count * 4 = ' + (count * 4) });
  rec.group = 'count';
  const buf = heap.malloc(allocSize || 8);
  rec.names.buf = buf.addr;
  const cfg = heap.malloc(16);
  rec.names.cfg = cfg.addr;
  heap._writeLE(cfg.dataAddr, symbols.normal, 4);
  heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.normal };
  const leak = heap.baseAddr + cfg.dataAddr;
  rec.extra.leak = leak;
  rec.snap('poke', [cfg.dataAddr, symbols.normal]);
  rec.log([...logs, { cls: 'action', msg: 'malloc(' + allocSize + ')' }, { cls: 'action', msg: 'cfg at ' + hex8(leak) }]);

  rec.group = 'submit';
  const H = heap.HEADER_SIZE;
  const bytes = overflowTo(heap, buf.addr + H, cfg.addr + H, symbols.win);
  payloads.push(bytes);
  heap.write(buf.addr + H, bytes);
  const handler = heap._readLE(cfg.dataAddr, 4);
  heap.funcPtrs['handler'] = { original: symbols.normal, current: handler };
  rec.snap('call', ['handler']);
  return {
    count, allocSize, leak, completed: handler === symbols.win,
    logs: [{ cls: 'action', msg: 'cfg->handler() is now ' + hex8(handler) }],
  };
}

// FinalBlindInput.tsx, doUafWrite() then doFinalWrite()
function finalBlind(ex: any, heap: any, rec: Rec, payloads: number[][]) {
  const H = heap.HEADER_SIZE;
  // aim the freed ptrs[2]'s fd at ptrs[0]'s data, where fn lives
  const target = heap.baseAddr + rec.names.ptr0 + H;
  payloads.push(le32(target));
  heap.write(rec.names.ptr2 + H, payloads[0]);
  const fd = heap._readLE(rec.names.ptr2 + H, 4);
  heap.malloc(32);
  rec.names.y_target = fd;
  rec.snap('name', ['y_target']);
  rec.log([{ cls: 'action', msg: 'void *y = malloc(32) follows poisoned fd to ' + hex8(fd) }]);

  rec.group = 'submit2';
  payloads.push(le32(symbols.win));
  const b = payloads[1];
  const val = (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0;
  // VRIG never writes y into the heap, it sets fn directly
  heap.funcPtrs['fn'] = { original: symbols.normal, current: val };
  rec.snap('call', ['fn']);
  return { completed: val === symbols.win, logs: [{ cls: 'action', msg: 'read(0, y, 4) writing ' + hex8(val) }] };
}

// -- model continuations ----------------------------------------------------
// None of this is VRIG's engine. It's glibc's behavior acted out on the same
// HeapSim object, so the view can keep using one state format.

const MODELS: Record<string, (ex: any, heap: any, rec: Rec, fp: number) => any> = {
  'heap-house-force'(ex, heap, rec, fp) {
    const H = heap.HEADER_SIZE;
    const top = heap.baseAddr + heap.topAddr;        // top chunk's header, absolute
    const target = fp;
    // want the next chunk's header at target - 8 so its data lands on target
    const evil = ((target - H) - top - H) >>> 0;
    const newTop = (top + evil + H) >>> 0;
    rec.extra = { topAbs: top, evil, newTop, sizeField: heap._readLE(heap.topAddr + 4, 4) };
    rec.snap('malloc-evil', [evil]);
    const d = (newTop + H) >>> 0;
    rec.extra = { ...rec.extra, topAbs: (newTop + 24) >>> 0, d };
    rec.snap('malloc', [16], { dataAbs: d });
    heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.win };
    rec.snap('call', ['handler']);
    return { top, target, evil, newTop, d, reachesHandler: d === target };
  },

  'heap-house-spirit'(ex, heap, rec) {
    // stack_buf is 64 bytes off the heap entirely. The fake header goes at +0
    const buf = new Array(64).fill(0);
    const hdr = [...le32(0), ...le32(heap._alignSize(16) | 1)];
    hdr.forEach((b, i) => { buf[i] = b; });
    rec.extra = { stackBuf: [...buf], fake: { off: 0, size: heap._alignSize(16), inTcache: false } };
    rec.snap('write-fake', [hdr]);
    rec.extra.fake.inTcache = true;
    rec.extra.tcache = { [heap._alignSize(16)]: ['stack_buf'] };
    rec.snap('free', ['stack_buf+8']);
    rec.extra.fake.inTcache = false;
    rec.extra.tcache = {};
    rec.extra.p = 'stack_buf+8';
    rec.snap('malloc', [16], 'stack_buf+8');
    return { fakeSize: heap._alignSize(16) | 1, reachesHandler: false };
  },

  'heap-house-orange'(ex, heap, rec, fp) {
    const H = heap.HEADER_SIZE;
    const oldTop = heap.topAddr;
    const shrunk = heap._readLE(oldTop + 4, 4);
    const oldSize = shrunk & ~7;
    // sysmalloc: the request doesn't fit, old top is freed, top moves on
    heap.topSize = oldSize;
    heap.chunks.set(oldTop, { size: oldSize, allocated: false, dataStart: oldTop + H, prevInUse: true });
    heap.unsorted.push(oldTop);
    heap._writeLE(oldTop + H, heap.mainArena, 4);
    heap._writeLE(oldTop + H + 4, heap.mainArena, 4);
    heap.topAddr = oldTop + oldSize;
    heap.topSize = heap.memorySize - heap.topAddr;
    rec.extra = { request: 256, oldSize, newTopNote: 'fresh pages from brk' };
    rec.snap('sysmalloc', [256]);
    // corrupt the freed top's bk, then malloc(96) unlinks it
    heap._writeLE(oldTop + H + 4, (fp - 8) >>> 0, 4);
    for (let i = 0; i < 4; i++) heap.written[oldTop + H + 4 + i] = 1;
    rec.snap('write-bk', [(fp - 8) >>> 0]);
    heap.unsorted = [];
    heap.chunks.get(oldTop).allocated = true;
    heap.funcPtrs['handler'] = { original: symbols.normal, current: heap.mainArena };
    rec.extra.wrote = { at: fp, value: heap.mainArena };
    rec.snap('malloc', [96]);
    const check = !!ex.check(null, heap, symbols, {});
    return { oldTop, oldSize, wrote: heap.mainArena, at: fp, checkOnModel: check };
  },

  'heap-house-einherjar'(ex, heap, rec) {
    const H = heap.HEADER_SIZE;
    const c = rec.names.C;
    const prev = heap._readLE(c, 4);
    const merged = c - prev;
    const size = prev + heap.chunks.get(c).size;
    // free(c): PREV_INUSE is clear, so glibc walks back prev_size bytes and merges
    heap.chunks.delete(rec.names.B);
    heap.chunks.delete(c);
    heap.chunks.set(merged, { size, allocated: false, dataStart: merged + H, prevInUse: true });
    heap.unsorted.push(merged);
    heap._writeLE(merged + 4, size | 1, 4);
    heap._writeLE(merged + H, 0, 4);
    heap._writeLE(merged + H + 4, heap.mainArena, 4);
    heap._writeLE(merged + size, size, 4);
    rec.extra = { prev, merged, size, swallowed: ['A', 'B', 'C'] };
    rec.snap('free', ['C']);
    heap.unsorted = [];
    heap.chunks.get(merged).allocated = true;
    heap._writeLE(merged + 4, size | 1, 4);
    rec.names.d = merged;
    rec.extra.d = merged;
    rec.snap('malloc', [64], { addr: merged });
    return { prev, merged, size, request: 64, fits: heap._alignSize(64) === size, reachesHandler: false };
  },

  'heap-house-lore'(ex, heap, rec, fp) {
    // VRIG's own sim on 2.27 drops a into tcache[88], not a smallbin. Replay the
    // binning on a 2.23 HeapSim (real VRIG code, no tcache) and copy its bins
    const h23: any = new HeapSim(heap.memorySize, '2.23');
    const a = h23.malloc(80);
    h23.malloc(16);
    h23.free(a.addr);
    h23.malloc(120);
    const H = heap.HEADER_SIZE;
    rec.extra = { replay: '2.23', smallbins: JSON.parse(JSON.stringify(h23.smallbins)) };
    // mirror that onto the trace's heap
    for (const k of Object.keys(heap.tcache)) heap.tcache[k] = [];
    heap.smallbins = JSON.parse(JSON.stringify(h23.smallbins));
    heap.chunks = new Map([...h23.chunks.entries()].map(([k, v]: any) => [k, { ...v }]));
    heap.topAddr = h23.topAddr; heap.topSize = h23.topSize;
    const bk = heap._readLE(a.addr + H + 4, 4);
    for (let i = 0; i < heap.memorySize; i++) {
      // keep the submit's bk write, take everything else from the replay
      if (i < a.addr + H + 4 || i >= a.addr + H + 8) heap.memory[i] = h23.memory[i];
    }
    heap.written.set(h23.written);
    rec.snap('replay-2.23', ['malloc(80)', 'malloc(16)', 'free(a)', 'malloc(120)']);
    const fake = (fp - 8) >>> 0;
    rec.extra.fake = { addr: fake, fd: heap.baseAddr + a.addr, bk: null };
    rec.snap('fake-fd', [fake]);
    heap.smallbins[heap.chunks.get(a.addr).size] = [];
    heap.chunks.get(a.addr).allocated = true;
    rec.extra.binAfter = fake;
    rec.snap('malloc', [80], { addr: a.addr });
    heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.win };
    rec.extra.p2 = (fake + H) >>> 0;
    rec.snap('malloc', [80], { dataAbs: (fake + H) >>> 0 });
    return { bk, fake, p2: (fake + H) >>> 0, reachesHandler: ((fake + H) >>> 0) === fp };
  },
};

for (const id of only ? [only] : IDS) run(id);
