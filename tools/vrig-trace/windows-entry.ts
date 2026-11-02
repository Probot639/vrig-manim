// Traces for the Windows units: unit8 (win-37..42, input-hex on the stack)
// and unit9 (win-43..46, the NT heap through WinHeapSim). Stack traces keep
// entry.ts's shape so vrig/trace.py's StackTrace loads them. Heap traces are
// their own shape (no "layout" key, so the stack-trace test skips them).
//
//   node dist/vrig-windows.mjs <outdir>           # all ten
//   node dist/vrig-windows.mjs <outdir> win-45    # one
//
// Payloads are built from the sim's layout and the exercise's symbols here,
// never pasted in. `solved` is only true when VRIG's own win path fires AND
// ex.check() agrees.

import { writeFileSync } from 'fs';
import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { StackSim } from '@/engine/simulators/StackSim';
import { WinHeapSim } from '@/engine/simulators/WinHeapSim';
import { generateExecSteps, execCurrentStep } from '@/engine/execution/StepEngine';
import {
  UAF_STEPS, DF_STEPS, executeHeapGuidedStep,
  heapUafSubmit, heapDoubleFreeSubmit, heapOverflowSubmit,
} from '@/engine/execution/HeapStepEngine';
import { X86Emulator } from '@/engine/x86/emulator';
import { hexStrToBytes } from '@/engine/helpers';

const STACK_IDS = ['win-37', 'win-38', 'win-39', 'win-40', 'win-41', 'win-42'];
const HEAP_IDS = ['win-43', 'win-44', 'win-45', 'win-46'];

const [outdir = 'traces', only] = process.argv.slice(2);

// canary, the heap's header key, and LFH slot picks all come from Math.random
function seeded(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const seedFor = (id: string) => 0x57a7 + parseInt(id.split('-')[1], 10);

const le = (v: number, n = 4) => Array.from({ length: n }, (_, i) => (v >>> (i * 8)) & 0xff);
// Padding is a value that belongs where it lands, not AAAA: the stack gets
// VRIG's own saved ebp over and over, the heap gets a heap pointer
const fillWith = (v: number, n: number) => Array.from({ length: n }, (_, i) => (v >>> ((i % 4) * 8)) & 0xff);
const toHex = (b: number[]) => b.map(x => x.toString(16).padStart(2, '0')).join(' ');
const strip = (s: string) => s.replace(/<[^>]+>/g, '');

// none of unit8/9 turn on aslr, so this is computeSymbols() minus its aslr branch
function symbolsFor(ex: any) {
  if (ex.aslr) throw new Error(ex.id + ' has aslr, computeSymbols needs porting');
  return { ...BASE_SYMBOLS };
}

function common(ex: any) {
  return {
    exercise: ex.id,
    unit: ex.unitId,
    title: ex.title,
    desc: strip(ex.desc),
    mode: ex.mode,
    vizMode: ex.vizMode,
    winTitle: ex.winTitle,
    winMsg: strip(ex.winMsg),
    source: ex.source.c.map((l: any) => l.text),
    // these exist in types.ts. recorded so the video can say what VRIG does with them
    winFlags: {
      sehChainSize: ex.sehChainSize ?? null, safeSEH: ex.safeSEH ?? null, sehop: ex.sehop ?? null,
      winVersion: ex.winVersion ?? null, windowsHeapType: ex.windowsHeapType ?? null,
    },
  };
}

// ── stack ────────────────────────────────────────────────────────

function newSim(ex: any, symbols: Record<string, number>) {
  return new StackSim({
    bufSize: ex.bufSize ?? 16,
    retAddr: (symbols.main || BASE_SYMBOLS.main) + 0x25,  // retAddrInMain()
    savedEbp: 0xbfff0200,
    useCanary: ex.canary,
    extraSize: 0,
  });
}

// Same sequence TextHexInput's Step button runs: reset, blank, generate, exec
function runStack(ex: any, sim: StackSim, symbols: Record<string, number>, hex: string) {
  const bytes = hexStrToBytes(hex);
  sim.resetForInput();
  sim.clearBlank();
  const snap = () => ({
    memory: Array.from(sim.memory),
    written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt),
    hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,
  });
  const steps: any[] = [];
  let canaryFailed = false;
  const state: any = {};
  for (const step of generateExecSteps(ex, bytes, sim, symbols)) {
    const r = execCurrentStep(step, sim, ex, symbols, state);
    steps.push({
      label: step.label,
      srcLine: step.srcLine,
      logs: r.logs.map(l => ({ cls: l.cls, msg: strip(l.msg) })),
      registers: r.registerUpdates ?? {},
      win: !!r.win,
      canaryFailed: !!r.canaryFailed,
      ...snap(),
    });
    if (r.canaryFailed) canaryFailed = true;
    if (r.done) break;
  }
  const stepWin = steps.some(s => s.win);
  const check = !!ex.check(sim, null, symbols, {});
  return { payload: bytes, payloadHex: toHex(bytes), steps, stepWin, check, canaryFailed, retAddr: sim.getRetAddr() };
}

// The exception dispatcher calls handler(ExceptionRecord, EstablisherFrame, ...),
// so on entry [esp+8] is the address of the SEH record (nSEH). Run VRIG's own
// x86 emulator over pop/pop/ret and the short jmp to show where control lands.
// Addresses here are placeholders for the demo, the scene shows roles only.
function pprDemo(recordAddr: number) {
  const PPR = 0x10101010;
  const SC = (recordAddr + 8) >>> 0;  // right after nSEH + handler
  const insns = [
    { addr: PPR, bytes: [0x5e], mnemonic: 'pop', operands: 'esi' },
    { addr: PPR + 1, bytes: [0x5f], mnemonic: 'pop', operands: 'edi' },
    { addr: PPR + 2, bytes: [0xc3], mnemonic: 'ret', operands: '' },
    // nSEH: jmp short over the 4-byte handler field. eb 06 = jmp +6 from the
    // end of this 2-byte insn, i.e. nSEH+8. two nops pad nSEH to 4 bytes
    { addr: recordAddr, bytes: [0xeb, 0x06], mnemonic: 'jmp', operands: '0x' + SC.toString(16) },
    { addr: SC, bytes: [0x90], mnemonic: 'nop', operands: '' },
  ];
  const ESP = 0xbfff0000;
  const emu = new X86Emulator(insns as any, { eip: PPR, esp: ESP });
  emu.writeMem(ESP, 0x77000000, 4);     // return into ntdll's dispatcher
  emu.writeMem(ESP + 4, 0x0012e000, 4); // ExceptionRecord*
  emu.writeMem(ESP + 8, recordAddr, 4); // EstablisherFrame = &nSEH
  emu.writeMem(ESP + 12, 0x0012e100, 4); // ContextRecord*
  const trace: any[] = [];
  for (let i = 0; i < 4; i++) {
    const before = emu.getCurrentInstruction();
    const r = emu.step();
    if (!r || !before) break;
    trace.push({
      insn: (before.mnemonic + ' ' + before.operands).trim(), at: before.addr,
      esp: emu.state.registers.esp, eip: emu.state.registers.eip, log: r.log,
    });
  }
  return {
    esp0: ESP, recordAddr, ppr: PPR, shellcode: SC, trace,
    landsOnRecord: trace[2]?.eip === recordAddr,
    jumpsPastHandler: trace[3]?.eip === SC,
  };
}

function stackTrace(id: string) {
  const ex = getExercise(id)!;
  Math.random = seeded(seedFor(id));
  const symbols = symbolsFor(ex);
  const sim = newSim(ex, symbols);
  const initial = {
    memory: Array.from(sim.memory), written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt), hl: null,
  };
  const retOff = sim.bufSize + sim.canarySize + sim.ebpSize;

  // filler to buf's end, the cookie back where it was, ebp as it was, then win
  const pad = (n: number) => fillWith(sim.origSavedEbp, n);
  const pay = [...pad(sim.bufSize)];
  if (sim.useCanary) pay.push(...le(sim.canaryValue));
  pay.push(...le(sim.origSavedEbp), ...le(symbols.win));
  const good = runStack(ex, sim, symbols, toHex(pay));

  const out: any = {
    ...common(ex),
    gadgets: ex.gadgets ?? {},
    symbols,
    flagAddr: ex.flagAddr ?? null,
    magicValue: ex.magicValue ?? null,
    layout: {
      base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
      ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
    },
    retOffset: retOff,
    origRetAddr: sim.origRetAddr,
    origSavedEbp: sim.origSavedEbp,
    canary: sim.useCanary ? sim.canaryValue : null,
    payload: good.payload,
    payloadHex: good.payloadHex,
    initial,
    steps: good.steps,
    stepWin: good.stepWin,
    check: good.check,
    solved: good.stepWin && good.check,
    attempts: {} as Record<string, any>,
  };

  if (id === 'win-39') {
    // the desc says 20 bytes to the return address. VRIG's frame says otherwise
    const m = ex.desc.match(/total distance to the return address is (\d+) bytes/);
    const hinted = m ? parseInt(m[1], 10) : null;
    out.descRetDistance = hinted;
    if (hinted !== null) {
      const s2 = newSim(ex, symbols);
      const r = runStack(ex, s2, symbols, toHex([...pad(hinted), ...le(symbols.win)]));
      out.attempts.descHint = { payloadHex: r.payloadHex, stepWin: r.stepWin, check: r.check, retAddr: r.retAddr };
    }
    // offsets straight from the source's layout comment: buf 8, then nSEH, handler
    out.sehRecord = { nsehOff: 8, handlerOff: 12, nsehAddr: sim.baseAddr + 8, handlerAddr: sim.baseAddr + 12 };
    const after = good.steps[good.steps.length - 1].memory;
    out.sehRecord.nsehAfter = after.slice(8, 12);
    out.sehRecord.handlerAfter = after.slice(12, 16);
  }

  if (id === 'win-40') {
    out.ppr = pprDemo(0xbfff0110);
  }

  if (id === 'win-41') {
    // same payload with the cookie slot left as filler
    Math.random = seeded(seedFor(id));
    const s2 = newSim(ex, symbols);
    const naive = [...pad(s2.bufSize + s2.canarySize + s2.ebpSize), ...le(symbols.win)];
    const r = runStack(ex, s2, symbols, toHex(naive));
    out.attempts.noCookie = {
      payload: r.payload, payloadHex: r.payloadHex, steps: r.steps,
      stepWin: r.stepWin, check: r.check, canaryFailed: r.canaryFailed,
    };
  }

  if (id === 'win-42') {
    // CFG keeps one entry per 16-byte slot of the image. A slot is a valid
    // indirect-call target when a function starts in it. Use VRIG's own .text
    // symbols as the function starts.
    const text = Object.entries(symbols).filter(([, a]) => (a >>> 24) === 0x08);
    const lo = symbols.main & ~0xf;
    const hi = (Math.max(...text.map(([, a]) => a)) | 0xf) + 1;
    const slots: any[] = [];
    for (let a = lo; a < hi; a += 16) {
      const fn = text.find(([, s]) => (s & ~0xf) === a);
      slots.push({ addr: a, valid: !!fn, fn: fn ? fn[0] : null });
    }
    const slotOf = (v: number) => ((v & ~0xf) - lo) / 16;
    out.cfg = {
      slots,
      retTarget: symbols.win,
      retSlot: slotOf(symbols.win),
      // the normal return site is mid-main: a fine ret target, never a valid call target
      probe: { addr: sim.origRetAddr, slot: slotOf(sim.origRetAddr), valid: slots[slotOf(sim.origRetAddr)].valid },
    };
  }

  return out;
}

// ── heap ─────────────────────────────────────────────────────────

function heapSnap(heap: WinHeapSim, names: Record<string, number>) {
  const chunks = heap.getChunksForDisplay().map(c => {
    const h = heap._readHeapEntry(c.addr);
    return {
      ...c,
      header: Array.from(heap.memory.slice(c.addr, c.addr + 8)),
      decoded: h,
      headerOk: heap.validateHeader(c.addr),
      flink: heap._readLE(c.dataStart, 4),
      blink: heap._readLE(c.dataStart + 4, 4),
      lfh: heap.chunks.get(c.addr)?.lfh ?? false,
    };
  });
  return {
    memory: Array.from(heap.memory),
    written: Array.from(heap.written),
    chunks,
    freeLists: heap.getFreeLists(),
    funcPtrs: JSON.parse(JSON.stringify(heap.funcPtrs)),
    topAddr: heap.topAddr,
    topSize: heap.topSize,
    names: { ...names },
    highlight: heap.highlight,
  };
}

// Same setup ExercisePageClient runs for each heap mode, minus React
function heapInit(ex: any, heap: WinHeapSim, symbols: Record<string, number>) {
  const names: Record<string, number> = {};
  if (ex.mode === 'heap-uaf') {
    const u = heap.malloc(16)!;
    names.User = u.addr;
    heap._writeLE(u.dataAddr, symbols.normal, 4);
    heap.funcPtrs['action'] = { original: symbols.normal, current: symbols.normal } as any;
  } else if (ex.mode === 'heap-double-free') {
    const a = heap.malloc(16)!;
    heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.normal } as any;
    names.A = a.addr;
  } else if (ex.mode === 'heap-overflow') {
    const a = heap.malloc(16)!;
    const b = heap.malloc(16)!;
    heap._writeLE(b.dataAddr, symbols.normal, 4);
    heap.funcPtrs['handler'] = { original: symbols.normal, current: symbols.normal } as any;
    names.A = a.addr;
    names.B = b.addr;
  }
  return names;
}

function stepsFor(mode: string) {
  if (mode === 'heap-uaf') return UAF_STEPS;
  if (mode === 'heap-double-free') return DF_STEPS;
  return [];  // heap-overflow goes straight to input
}

function submit(ex: any, bytes: number[], heap: WinHeapSim, names: Record<string, number>, symbols: Record<string, number>) {
  const funcPtrAddr = ex.funcPtrAddr ?? 0x0804a040;  // HeapStepInput's default
  if (ex.mode === 'heap-uaf') return heapUafSubmit(bytes, heap, names, symbols);
  if (ex.mode === 'heap-double-free') return heapDoubleFreeSubmit(bytes, heap, names, symbols, funcPtrAddr);
  if (ex.mode === 'heap-overflow') return heapOverflowSubmit(bytes, heap, names, symbols);
  throw new Error('mode ' + ex.mode);
}

function runHeap(ex: any, symbols: Record<string, number>, payload: (heap: WinHeapSim, names: any) => number[]) {
  Math.random = seeded(seedFor(ex.id));
  const heap = new WinHeapSim(ex.heapSize ?? 256, ex.winVersion);
  let names = heapInit(ex, heap, symbols);
  const timeline: any[] = [{ label: 'setup', srcLine: null, logs: [], ...heapSnap(heap, names) }];

  stepsFor(ex.mode).forEach((step, i) => {
    const r = executeHeapGuidedStep(step, heap, names);
    names = { ...names, ...(r.heapNames ?? {}) };
    timeline.push({
      label: 'step ' + (i + 1), srcLine: step.srcLine ?? null,
      doFree: step.doFree ?? null, doubleFree: !!step.doubleFree, doMalloc: !!step.doMalloc,
      logs: r.logs.map(l => ({ cls: l.cls, msg: strip(l.msg) })),
      ...heapSnap(heap, names),
    });
  });

  const bytes = hexStrToBytes(toHex(payload(heap, names)));
  const r = submit(ex, bytes, heap, names, symbols);
  timeline.push({
    label: 'submit', srcLine: null,
    logs: r.logs.map(l => ({ cls: l.cls, msg: strip(l.msg) })),
    ...heapSnap(heap, names),
  });
  const completed = !!r.completed;
  const check = !!ex.check(null, heap, symbols, {});
  return {
    encodingKey: heap.encodingKey, baseAddr: heap.baseAddr, headerSize: heap.HEADER_SIZE,
    payload: bytes, payloadHex: toHex(bytes), timeline, completed, check,
  };
}

// LFH never switches on inside the exercises (18 same-size allocs first, and a
// 32-slot UserBlocks for 24-byte chunks needs 768 bytes of a 256-byte heap).
// So run WinHeapSim on a bigger heap to show what the bucket does once it's on.
function lfhDemo(version: 'win7' | 'win8' | 'win10', seed: number) {
  Math.random = seeded(seed);
  const heap = new WinHeapSim(2048, version);
  const allocs: any[] = [];
  let activatedAt = -1;
  for (let i = 0; i < 26; i++) {
    const r = heap.malloc(16)!;
    const lfh = heap.chunks.get(r.addr)!.lfh;
    if (lfh && activatedAt < 0) activatedAt = i + 1;
    allocs.push({ n: i + 1, addr: r.addr, lfh });
  }
  const unitsFor16 = heap._toUnits(heap._alignSize(16));
  const bucket = heap.lfhBuckets[unitsFor16];
  const slotIndex = (a: number) => bucket.slots.findIndex(s => s.addr === a);
  const lfhAllocs = allocs.filter(a => a.lfh).map(a => ({ ...a, slot: slotIndex(a.addr) }));

  // free one LFH object (the "User") and ask for the same size again
  const victim = lfhAllocs[Math.min(3, lfhAllocs.length - 1)];
  const state0 = bucket.slots.map(s => s.inUse);
  heap.free(victim.addr);
  const again = heap.malloc(16)!;
  const reuse = { victimSlot: victim.slot, gotSlot: slotIndex(again.addr), inUseBefore: state0 };

  // how often does the next alloc land on the freed slot? replay that exact
  // free/alloc from the same bucket state with many seeds
  let hits = 0;
  const TRIALS = 400;
  for (let t = 0; t < TRIALS; t++) {
    Math.random = seeded(seed * 1000 + t);
    const h = new WinHeapSim(2048, version);
    for (let i = 0; i < 26; i++) h.malloc(16);
    const b = h.lfhBuckets[unitsFor16];
    const inUse = b.slots.filter(s => s.inUse);
    const v = inUse[Math.min(3, inUse.length - 1)];
    h.free(v.addr);
    if (h.malloc(16)!.addr === v.addr) hits++;
  }

  // spray: fill every slot, free the victim, the next alloc has one choice
  Math.random = seeded(seed + 7);
  const h2 = new WinHeapSim(2048, version);
  for (let i = 0; i < 17; i++) h2.malloc(16);  // back-end until activation
  const b2Allocs: number[] = [];
  for (let i = 0; i < 32; i++) b2Allocs.push(h2.malloc(16)!.addr);
  const b2 = h2.lfhBuckets[unitsFor16];
  const full = b2.slots.every(s => s.inUse);
  const vAddr = b2Allocs[5];
  const vSlot = b2.slots.findIndex(s => s.addr === vAddr);
  h2.free(vAddr);
  const back = h2.malloc(16)!.addr;

  return {
    version,
    threshold: activatedAt,
    chunkBytes: heap._alignSize(16),
    sizeUnits: unitsFor16,
    regionStart: bucket.slots[0].addr,
    nSlots: bucket.slots.length,
    allocs,
    lfhAllocs,
    slotsAfter: bucket.slots.map(s => s.inUse),
    reuse,
    reuseRate: { hits, trials: TRIALS },
    spray: { full, victimSlot: vSlot, gotSlot: b2.slots.findIndex(s => s.addr === back), reused: back === vAddr },
  };
}

function heapTrace(id: string) {
  const ex = getExercise(id)!;
  const symbols = symbolsFor(ex);
  const winLE = () => le(symbols.win);

  let run: any;
  const attempts: Record<string, any> = {};
  if (ex.mode === 'heap-uaf') {
    run = runHeap(ex, symbols, () => winLE());
  } else if (ex.mode === 'heap-overflow') {
    // fill A's data, run straight over B's _HEAP_ENTRY, then B's first word
    run = runHeap(ex, symbols, (heap, names) => {
      const aData = heap.chunks.get(names.A)!.size - heap.HEADER_SIZE;
      const gap = names.B - (names.A + heap.HEADER_SIZE + aData);
      // A's own data address as filler, straight through B's header too
      const p = heap.baseAddr + names.A + heap.HEADER_SIZE;
      return [...fillWith(p, aData + gap + heap.HEADER_SIZE), ...winLE()];
    });
  } else if (ex.mode === 'heap-double-free') {
    run = runHeap(ex, symbols, () => le(ex.funcPtrAddr ?? 0x0804a040));
    // what the desc tells you to type: win() itself
    const wrong = runHeap(ex, symbols, () => winLE());
    attempts.descHint = { payloadHex: wrong.payloadHex, completed: wrong.completed, check: wrong.check,
      logs: wrong.timeline[wrong.timeline.length - 1].logs };
  }

  const out: any = {
    ...common(ex),
    heapSize: ex.heapSize ?? 256,
    symbols,
    funcPtrAddr: ex.funcPtrAddr ?? 0x0804a040,
    ...run,
    solved: run.completed && run.check,
    attempts,
  };

  // the LFH side story. win10 randomizes the slot, win7 is first-fit
  if (id === 'win-43' || id === 'win-44') out.lfh = lfhDemo('win10', seedFor(id));
  if (id === 'win-46') out.lfh = { win7: lfhDemo('win7', seedFor(id)), win10: lfhDemo('win10', seedFor(id)) };
  return out;
}

for (const id of [...STACK_IDS, ...HEAP_IDS]) {
  if (only && id !== only) continue;
  const out = STACK_IDS.includes(id) ? stackTrace(id) : heapTrace(id);
  writeFileSync(`${outdir}/${id}.json`, JSON.stringify(out, null, 1));
  console.log(`${id}: solved=${out.solved}`);
}
