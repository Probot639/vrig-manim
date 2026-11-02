// Guided "step" exercises with a stack view. There is no StepEngine for these:
// StepControls.handleStep() writes the region, logs, then runs the step's
// vizAction against the StackSim and AuxViz. This replays that loop and dumps
// the stack, the aux panels, the log line, and the exec line after each click.
//
//   node dist/vrig-walk_stack.mjs <exercise-id>...   (writes traces/<id>.json)

import { writeFileSync } from 'node:fs';
import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { StackSim } from '@/engine/simulators/StackSim';
import { AuxViz } from '@/engine/simulators/AuxViz';
import { hex8 } from '@/engine/helpers';

// canary and ASLR both come from Math.random. Pin it so a re-export gives
// the same video. mulberry32.
const SEED = 0x5eed133a;  // picked so libc doesn't wrap past 4G, see gap-111
let rng = SEED;
Math.random = () => {
  rng = (rng + 0x6d2b79f5) >>> 0;
  let t = rng;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

// copied from ExercisePageClient.tsx, which can't be imported outside Next
const CODE_SYMBOLS = ['main', 'win', 'vuln', 'normal'];
const LIBC_SYMBOLS = ['system', 'binsh'];
const STACK_SYMBOLS = ['main_ret'];

function computeSymbols(exercise: any): Record<string, number> {
  const symbols = { ...BASE_SYMBOLS };
  if (exercise?.aslr) {
    const codeOffset = ((Math.random() * 0x200000) >>> 0) & ~0xfff;
    const libcOffset = ((Math.random() * 0x10000000) >>> 0) & ~0xfff;
    const stackOffset = ((Math.random() * 0x800000) >>> 0) & ~0xfff;
    for (const key of Object.keys(symbols)) {
      if (CODE_SYMBOLS.includes(key)) symbols[key] = (symbols[key] + codeOffset) >>> 0;
      else if (LIBC_SYMBOLS.includes(key)) symbols[key] = (symbols[key] + libcOffset) >>> 0;
      else if (STACK_SYMBOLS.includes(key)) symbols[key] = (symbols[key] + stackOffset) >>> 0;
      else symbols[key] = (symbols[key] + codeOffset) >>> 0;
    }
  }
  if (exercise?.srop) {
    symbols['sigreturn'] = 0x080481b0;
    if (exercise.aslr) symbols['sigreturn'] = (0x080481b0 + symbols['main'] - BASE_SYMBOLS.main) >>> 0;
  }
  return symbols;
}

const retAddrInMain = (s: Record<string, number>) => (s.main || BASE_SYMBOLS.main) + 0x25;

const strip = (s: string) =>
  s.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

// These two write past the return address, but a step exercise gets no
// extraSize, so StackSim's frame ends at ret and the rest of the chain is
// silently dropped (writeInput/writeWord stop at totalSize). Give the sim
// room so the video can show what the vizAction meant to write.
const ROOM: Record<string, number> = { 'kern-106': 16, 'mit-80': 4 };

function trace(id: string) {
  rng = SEED;
  const ex = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  if (ex.mode !== 'step' || ex.vizMode !== 'stack') throw new Error(id + ' is not a step/stack exercise');

  const symbols = computeSymbols(ex);
  let extraSize = 0;
  if (ex.ret2libc) extraSize = 8;
  else if (ex.rop) extraSize = 40;
  else if (ex.srop) extraSize = 44;
  else if (ex.pivot) extraSize = 40;
  const vrigExtraSize = extraSize;
  extraSize += ROOM[id] ?? 0;

  const sim = new StackSim({
    bufSize: ex.bufSize ?? 16,
    retAddr: retAddrInMain(symbols),
    savedEbp: 0xbfff0200,
    useCanary: ex.canary,
    extraSize,
  });
  sim.clearBlank();
  const aux = new AuxViz();

  const snap = () => ({
    memory: Array.from(sim.memory),
    written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt),
    hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,
    aux: JSON.parse(JSON.stringify({ got: aux.got, shadow: aux.shadow, memMap: aux.memMap, cfi: aux.cfiTargets })),
  });

  const out: any = {
    exercise: ex.id,
    unit: ex.unitId,
    title: ex.title,
    desc: strip(ex.desc),
    source: ex.source.c.map(l => l.text),
    sourceCls: ex.source.c.map(l => l.cls),
    asm: ex.source.asm?.map(l => l.text) ?? null,
    symbols,
    canaryValue: sim.useCanary ? sim.canaryValue : null,
    seed: SEED,
    vrigExtraSize,
    extraSize,
    auxViz: ex.auxViz ?? [],
    protections: ex.protections ?? [],
    layout: {
      base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
      ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
    },
    initial: snap(),
    steps: [] as any[],
    winTitle: ex.winTitle,
    winMsg: strip(ex.winMsg),
  };

  // handleStep(), one click at a time
  let execLine = -1;
  ex.steps!.forEach((step, i) => {
    let log: [string, string] = [step.log[0], step.log[1]];
    if (!step.action && step.region === 'ret') {
      const ret = retAddrInMain(symbols);
      sim._writeLE(sim.bufSize + sim.canarySize + sim.ebpSize, ret, sim.retSize);
      sim.markRegion(sim.bufSize + sim.canarySize + sim.ebpSize, sim.totalSize);
      log = ['action', `Calling vuln() — saving the go-back address ${hex8(ret)} so we know where to return`];
    } else if (!step.action && step.region === 'ebp') {
      sim._writeLE(sim.bufSize + sim.canarySize, 0xbfff0200, sim.ebpSize);
      sim.markRegion(sim.bufSize + sim.canarySize, sim.bufSize + sim.canarySize + sim.ebpSize);
    } else if (!step.action && step.region === 'buffer') {
      for (let k = 0; k < sim.bufSize; k++) sim.memory[k] = 0;
      sim.markRegion(0, sim.bufSize);
    } else if (!step.action && step.region === 'all') {
      sim.clearHighlight();
    }
    // malloc/free actions need a heap, and none of these exercises have one
    if (step.vizAction) step.vizAction(sim, null, aux);
    if (step.srcLine !== undefined) execLine = step.srcLine;

    out.steps.push({
      index: i,
      region: step.region ?? null,
      action: step.action ?? null,
      srcLine: step.srcLine ?? null,
      execLine,
      logCls: log[0],
      log: strip(log[1]),
      done: step.action === 'done' || i === ex.steps!.length - 1,
      ...snap(),
    });
  });

  // every one of these has check() { return false }: nothing to win, the
  // lesson completes when the last step runs
  out.checkResult = ex.check(sim, null, symbols, {});
  out.completed = out.steps.length === ex.steps!.length;
  if (id === 'gap-111') out.stage3 = leakChain(ex, symbols, sim.canaryValue);
  if (id === 'gap-114') out.partial = partialOverwrite(ex);
  return out;
}

// gap-111 stage 3: [padding][canary][fake_ebp][system()][dummy_ret][&"/bin/sh"]
// from the step 3 log, using the canary and libc slide this run produced.
// writeInput it into a ret2libc-sized frame and ask the sim if it holds.
function leakChain(ex: any, symbols: Record<string, number>, canary: number) {
  const sim = new StackSim({
    bufSize: ex.bufSize, retAddr: retAddrInMain(symbols), savedEbp: 0xbfff0200,
    useCanary: true, extraSize: 8,
  });
  sim.canaryValue = canary;
  sim.resetForInput();
  const le = (v: number) => [0, 1, 2, 3].map(i => (v >>> (i * 8)) & 0xff);
  const payload = [
    ...new Array(ex.bufSize).fill(0x41), ...le(canary), ...le(0x42424242),
    ...le(symbols.system), ...le(0x43434343), ...le(symbols.binsh),
  ];
  sim.writeInput(payload);
  const retOff = sim.bufSize + sim.canarySize + sim.ebpSize;
  return {
    payload,
    memory: Array.from(sim.memory),
    layout: { bufSize: sim.bufSize, canarySize: sim.canarySize, totalSize: sim.totalSize, base: sim.baseAddr },
    libcSlide: (symbols.system - BASE_SYMBOLS.system) >>> 0,
    baseSystem: BASE_SYMBOLS.system,
    canaryIntact: sim.canaryIntact(),
    retAddr: sim.getRetAddr(),
    argAddr: sim._readLE(retOff + 8, 4),
    solved: sim.canaryIntact() && sim.getRetAddr() === symbols.system && sim._readLE(retOff + 8, 4) === symbols.binsh,
  };
}

// gap-114: every number comes out of the step logs. Put the logged return
// address in a StackSim, then try the 1-byte and 2-byte overwrites.
function partialOverwrite(ex: any) {
  const logs = ex.steps.map((s: any) => strip(s.log[1])).join(' ');
  const ret = parseInt(logs.match(/Full address: 0x([0-9a-f]+)/i)![1], 16);
  const target = parseInt(logs.match(/we need 0x([0-9a-f]+)/i)![1], 16);
  const oneByte = parseInt(logs.match(/Change 0x[0-9a-f]+ to 0x([0-9a-f]+)/i)![1], 16);
  const twoByte = parseInt(logs.match(/last 2 bytes to 0x([0-9a-f]+)/i)![1], 16);
  const run = (bytes: number[]) => {
    const sim = new StackSim({ bufSize: ex.bufSize, retAddr: ret, savedEbp: 0xbfff0200 });
    const retOff = sim.bufSize + sim.canarySize + sim.ebpSize;
    sim.writeWord(retOff, bytes);
    return { bytes, memory: Array.from(sim.memory), ret: sim.getRetAddr(), hit: sim.getRetAddr() === target };
  };
  const one = run([oneByte]);
  // the high nibble of byte 1 is the ASLR part. Brute force it.
  const tries = [];
  for (let n = 0; n < 16; n++) {
    const v = (twoByte & 0x0fff) | (n << 12);
    tries.push({ nibble: n, ...run([v & 0xff, v >>> 8]) });
  }
  const logged = run([twoByte & 0xff, twoByte >>> 8]);
  return {
    ret, target, oneByteValue: oneByte, twoByteValue: twoByte,
    oneByte: one, loggedTwoByte: logged, tries,
    hitNibble: tries.find(t => t.hit)?.nibble ?? null,
    solved: tries.filter(t => t.hit).length === 1 && !one.hit,
  };
}

const ids = process.argv.slice(2);
const dir = new URL('traces/', 'file://' + process.cwd() + '/');  // run from the repo root
for (const id of ids) {
  const t = trace(id);
  writeFileSync(new URL(`${id}.json`, dir), JSON.stringify(t, null, 1) + '\n');
  console.log(`${id}: ${t.steps.length} steps`);
}
