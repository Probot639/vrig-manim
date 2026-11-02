// Traces for the recap CTFs and the "advanced" input-hex lessons (unit10,
// mit-81, unit16, adv2-101, kern-104). Same output shape as entry.ts, so
// vrig/trace.py's StackTrace loads them, plus what the videos need on top:
// whether VRIG calls it a win, what ex.check() says, the canary, protections.
//
//   node dist/vrig-stack_adv.mjs <outdir>            # every exercise below
//   node dist/vrig-stack_adv.mjs <outdir> kern-104   # just one
//
// Payloads are built here from the sim's own layout, never typed in as hex.

import { writeFileSync } from 'fs';
import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { StackSim } from '@/engine/simulators/StackSim';
import { generateExecSteps, execCurrentStep } from '@/engine/execution/StepEngine';

const IDS = ['ctf-47', 'ctf-49', 'ctf-50', 'ctf-52', 'mit-81', 'adv-88', 'adv-89',
  'adv-92', 'adv-93', 'adv-94', 'adv2-101', 'kern-104'];

const [outdir = 'traces', only] = process.argv.slice(2);

// canary and ASLR both come from Math.random. Pin it so a re-export gives the
// same bytes as the committed trace.
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

// copy of computeSymbols() in ExercisePageClient.tsx, it isn't exported
const CODE_SYMBOLS = ['main', 'win', 'vuln', 'normal'];
const LIBC_SYMBOLS = ['system', 'binsh'];
function computeSymbols(ex: any): Record<string, number> {
  const symbols = { ...BASE_SYMBOLS };
  if (ex.aslr) {
    const codeOffset = ((Math.random() * 0x200000) >>> 0) & ~0xfff;
    const libcOffset = ((Math.random() * 0x10000000) >>> 0) & ~0xfff;
    for (const key of Object.keys(symbols)) {
      const off = LIBC_SYMBOLS.includes(key) ? libcOffset : codeOffset;
      symbols[key] = (symbols[key] + off) >>> 0;
    }
  }
  if (ex.srop) symbols['sigreturn'] = (0x080481b0 + symbols.main - BASE_SYMBOLS.main) >>> 0;
  return symbols;
}

function extraSizeFor(ex: any) {
  if (ex.ret2libc) return 8;
  if (ex.rop) return 40;
  if (ex.srop) return 44;
  if (ex.pivot) return 40;
  return 0;
}

const le = (v: number, n = 4) => Array.from({ length: n }, (_, i) => (v >>> (i * 8)) & 0xff);
const fill = (ch: string, n: number) => Array(n).fill(ch.charCodeAt(0));
const strip = (s: string) => s.replace(/<[^>]+>/g, '');

function newSim(ex: any, symbols: Record<string, number>) {
  return new StackSim({
    bufSize: ex.bufSize ?? 16,
    retAddr: (symbols.main || BASE_SYMBOLS.main) + 0x25,  // retAddrInMain()
    savedEbp: 0xbfff0200,
    useCanary: ex.canary,
    extraSize: extraSizeFor(ex),
  });
}

// What goes in buf. Most lessons only care about the return address, so buf
// is filler. The vtable one plants its fake vtable at &buf so the bytes on
// screen match the story the video tells.
function bufBytes(id: string, sim: StackSim, symbols: Record<string, number>): number[] {
  const n = sim.bufSize;
  if (id === 'adv-88') return [...le(symbols.win), ...fill('A', n - 4)];
  return fill('A', n);
}

function buildPayload(id: string, sim: StackSim, symbols: Record<string, number>, target: number): number[] {
  const p = bufBytes(id, sim, symbols);
  if (id === 'adv2-101') return [...p, ...le(1)];  // isAdmin = 1, stop there
  if (sim.useCanary) p.push(...le(sim.canaryValue, sim.canarySize));  // the leaked value, put back
  p.push(...fill('B', sim.ebpSize));
  p.push(...le(target, sim.retSize));
  return p;
}

// ctf-4x/52 call sim.readWord(sim.retOffset) and sim.checkCanary(). StackSim
// has neither, so the real check throws. This shim maps them onto what
// StackSim does have, to show the check's *intent* agrees with the payload.
function adapted(sim: StackSim): any {
  return new Proxy(sim as any, {
    get(t, k) {
      if (k === 'readWord') return (off: number) => t._readLE(off, t.retSize);
      if (k === 'retOffset') return t.bufSize + t.canarySize + t.ebpSize;
      if (k === 'checkCanary') return () => t.canaryIntact();
      const v = t[k];
      return typeof v === 'function' ? v.bind(t) : v;
    },
  });
}

function runCheck(ex: any, sim: any, symbols: Record<string, number>) {
  try {
    return { result: !!ex.check(sim, null, symbols, {}), error: null };
  } catch (e: any) {
    return { result: false, error: String(e?.message ?? e) };
  }
}

function trace(id: string, seed: number, retTarget?: (s: Record<string, number>) => number) {
  const ex: any = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  Math.random = seeded(seed);

  const symbols = computeSymbols(ex);
  const sim = newSim(ex, symbols);
  const payload = buildPayload(id, sim, symbols, retTarget ? retTarget(symbols) : symbols.win);

  // TextHexInput does exactly this before generating steps
  sim.resetForInput();
  sim.clearBlank();

  const snap = () => ({
    memory: Array.from(sim.memory),
    written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt),
    hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,
  });

  const out: any = {
    exercise: ex.id,
    unit: ex.unitId,
    title: ex.title,
    desc: strip(ex.desc),
    source: ex.source.c.map((l: any) => l.text),
    gadgets: ex.gadgets ?? {},
    symbols,
    flagAddr: ex.flagAddr ?? null,
    magicValue: ex.magicValue ?? null,
    flags: {
      canary: !!ex.canary, aslr: !!ex.aslr, nx: !!ex.nx, auxViz: ex.auxViz ?? [],
      extraSize: extraSizeFor(ex),
    },
    protections: ex.protections ?? [],
    canaryValue: sim.useCanary ? sim.canaryValue : null,
    layout: {
      base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
      ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
    },
    origRet: sim.origRetAddr,
    origEbp: sim.origSavedEbp,
    payload,
    initial: snap(),
    steps: [] as any[],
    winTitle: strip(ex.winTitle),
    winMsg: strip(ex.winMsg),
  };

  const state: any = {};
  let stepWin = false, canaryFailed = false;
  for (const step of generateExecSteps(ex, payload, sim, symbols)) {
    const r = execCurrentStep(step, sim, ex, symbols, state);
    out.steps.push({
      label: step.label,
      srcLine: step.srcLine,
      logs: r.logs.map(l => ({ cls: l.cls, msg: strip(l.msg) })),
      registers: r.registerUpdates ?? {},
      win: !!r.win,
      ...snap(),
    });
    stepWin ||= !!r.win;
    canaryFailed ||= !!r.canaryFailed;
    if (r.done) break;
  }

  out.retAfter = sim.getRetAddr();
  out.canaryIntact = sim.canaryIntact();
  out.inputLen = sim.inputLen;
  out.stepWin = stepWin;
  out.canaryFailed = canaryFailed;
  out.check = runCheck(ex, sim, symbols);
  out.checkAdapted = out.check.error ? runCheck(ex, adapted(sim), symbols) : null;
  // the UI only ever shows a win from StepEngine. adv2-101 is the exception
  // worth flagging: its check passes but StepEngine never calls it there.
  out.solved = out.check.error ? (stepWin && !!out.checkAdapted.result) : out.check.result;
  return out;
}

for (const [i, id] of IDS.entries()) {
  if (only && id !== only) continue;
  const out = trace(id, 0x5eed0000 + i);
  if (id === 'kern-104') {
    // the desc says "overwrite with commit_creds". Its address only lives in
    // a source comment, so pull it from there and see what VRIG does with it
    const line = out.source.find((l: string) => l.includes('commit_creds:'));
    const commit = parseInt(line.match(/0x([0-9a-f]+)/i)[1], 16);
    const alt = trace(id, 0x5eed0000 + i, () => commit);
    out.alt = {
      target: commit, payload: alt.payload, stepWin: alt.stepWin, check: alt.check,
      jumpLogs: alt.steps[alt.steps.length - 1].logs,
    };
  }
  writeFileSync(`${outdir}/${id}.json`, JSON.stringify(out, null, 1));
  console.log(id, 'solved', out.solved, 'stepWin', out.stepWin, 'check', JSON.stringify(out.check));
}
