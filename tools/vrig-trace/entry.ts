// Bundled by build.sh against a 0xVRIG checkout. Runs an exercise's real
// StepEngine on a payload and dumps every step as JSON, so scenes animate
// what VRIG actually computes instead of numbers retyped by hand.
//
//   node dist/vrig-trace.mjs <exercise-id> <payload-hex>

import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { StackSim } from '@/engine/simulators/StackSim';
import { generateExecSteps, execCurrentStep } from '@/engine/execution/StepEngine';

const [id, payloadHex = ''] = process.argv.slice(2);
const ex = getExercise(id);
if (!ex) {
  console.error('no exercise ' + id);
  process.exit(1);
}

const bytes = (payloadHex.replace(/[^0-9a-f]/gi, '').match(/../g) || []).map(b => parseInt(b, 16));

// Same sizing ExercisePageClient uses
let extraSize = 0;
if (ex.ret2libc) extraSize = 8;
else if (ex.rop) extraSize = 40;
else if (ex.srop) extraSize = 44;
else if (ex.pivot) extraSize = 40;

const symbols = { ...BASE_SYMBOLS };  // aslr off for everything we trace so far
const sim = new StackSim({
  bufSize: ex.bufSize ?? 16,
  retAddr: symbols.main + 0x25,  // retAddrInMain() in StepControls
  savedEbp: 0xbfff0200,
  useCanary: ex.canary,
  extraSize,
});

const snap = () => ({
  memory: Array.from(sim.memory),
  written: Array.from(sim.written),
  overflow: Array.from(sim.overflowAt),
  hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,  // what this step touched
});

const strip = (s: string) => s.replace(/<[^>]+>/g, '');

const out: any = {
  exercise: ex.id,
  title: ex.title,
  source: ex.source.c.map(l => l.text),
  gadgets: ex.gadgets ?? {},
  symbols,
  flagAddr: ex.flagAddr ?? null,
  magicValue: ex.magicValue ?? null,
  layout: {
    base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
    ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
  },
  payload: bytes,
  initial: snap(),
  steps: [] as any[],
};

const state: any = {};
for (const step of generateExecSteps(ex, bytes, sim, symbols)) {
  const r = execCurrentStep(step, sim, ex, symbols, state);
  out.steps.push({
    label: step.label,
    srcLine: step.srcLine,
    logs: r.logs.map(l => ({ cls: l.cls, msg: strip(l.msg) })),
    registers: r.registerUpdates ?? {},
    win: !!r.win,
    ...snap(),
  });
  if (r.done) break;
}

console.log(JSON.stringify(out, null, 1));
