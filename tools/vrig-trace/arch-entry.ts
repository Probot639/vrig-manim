// Units 13 and 14 (ARM, MIPS). Two kinds of trace come out of here:
//
//   asm-quiz   VRIG's own ArmEmulator / MipsEmulator, built the way
//              ExercisePageClient builds them, stepped the way AsmQuizInput's
//              "Run All" steps them. Registers, flags, and touched memory
//              after every instruction, plus each quiz answer checked
//              against what the emulator actually holds.
//   input-hex  StepEngine on a payload, same shape as entry.ts so
//              vrig.trace.StackTrace loads it.
//
//   node dist/vrig-arch.mjs <exercise-id> [payload-hex]

import { getExercise } from '@/exercises/registry';
import { BASE_SYMBOLS } from '@/exercises/shared/symbols';
import { ArmEmulator } from '@/engine/arm/emulator';
import { MipsEmulator } from '@/engine/mips/emulator';
import { StackSim } from '@/engine/simulators/StackSim';
import { generateExecSteps, execCurrentStep } from '@/engine/execution/StepEngine';

const [id, payloadHex = ''] = process.argv.slice(2);
const ex = getExercise(id);
if (!ex) {
  console.error('no exercise ' + id);
  process.exit(1);
}

const strip = (s: string) => s.replace(/<[^>]+>/g, '');
const u32 = (v: number) => v >>> 0;

// AsmQuizInput.parseAnswer + its compare, copied since they live inside the
// component. We feed it the emulator's value the way a student would type it.
function parseAnswer(text: string): number | null {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  if (t.startsWith('0x')) return parseInt(t, 16);
  if (/^[0-9a-f]+h$/.test(t)) return parseInt(t.slice(0, -1), 16);
  if (/^[0-9]+$/.test(t)) return parseInt(t, 10);
  if (/^[0-9a-f]+$/.test(t) && t.length > 2) return parseInt(t, 16);
  return parseInt(t, 10);
}
const quizAccepts = (typed: string, answer: number) => {
  const p = parseAnswer(typed);
  return p !== null && (p & 0xFFFFFFFF) === (answer & 0xFFFFFFFF);
};

// --- asm-quiz -------------------------------------------------------------

type Probe = (run: any) => { value: number; where: string };

// Where each question's value lives in the run. `after(addr)` is the state
// right after the first execution of the instruction at addr.
function after(run: any, addr: number) {
  const s = run.steps.find((s: any) => s.addr === addr && !s.skipped);
  if (!s) throw new Error(`${id}: never executed ${addr.toString(16)}`);
  return s;
}
const reg = (r: string, at?: number): Probe => run => {
  const s = at === undefined ? run.final : after(run, at);
  return { value: s.regs[r], where: at === undefined ? `${r} at halt` : `${r} after 0x${at.toString(16)}` };
};

const PROBES: Record<string, Probe[]> = {
  'arm-63': [reg('r3', 0x1000c), reg('r4', 0x10014), reg('r0')],
  'arm-64': [reg('r0', 0x10008), reg('r5', 0x10014), reg('r3', 0x1000c)],
  'arm-65': [reg('r0', 0x10004), reg('r3', 0x1000c), reg('r5', 0x10018)],
  'arm-66': [reg('r2', 0x10018), reg('r3', 0x1001c), reg('r5', 0x10028)],
  'arm-67': [reg('r14', 0x10008), reg('r0', 0x1001c), reg('r4')],
  'arm-68': [
    reg('r13', 0x10000),
    reg('r13', 0x10008),
    run => {
      const low = Math.min(...run.steps.map((s: any) => s.regs.r13));
      return { value: run.initial.regs.r13 - low, where: 'sp at entry minus lowest sp' };
    },
  ],
  'mips-71': [reg('$t3', 0x400010), reg('$t4', 0x400014), reg('$t2', 0x400008)],
  'mips-72': [reg('$t4', 0x400008), reg('$t5', 0x40000c), reg('$t6', 0x400010)],
  'mips-73': [reg('$t0', 0x400000), reg('$t2', 0x400008), reg('$t4', 0x400014)],
  'mips-74': [
    run => {
      // the delay slot ran if 0x400010 executed while a branch was pending
      const s = run.steps.find((s: any) => s.addr === 0x400010);
      return { value: s && s.inDelaySlot ? 1 : 0, where: 'delay slot instruction executed' };
    },
    reg('$t2'),
    reg('$t3'),
  ],
  'mips-75': [reg('$v0', 0x400018), reg('$ra', 0x400008)],
  'mips-76': [
    reg('$sp', 0x400000),
    run => {
      const w = after(run, 0x400004).writes[0];
      return { value: w.addr, where: 'address sw $ra wrote' };
    },
    run => {
      const w = after(run, 0x400004).writes[0];
      return { value: w.addr - after(run, 0x400000).regs.$sp, where: 'saved $ra minus $sp' };
    },
  ],
};

function runQuiz() {
  const arch = ex!.asmArch ?? 'x86';
  const instrs = ex!.asmInstructions!;
  let emu: ArmEmulator | MipsEmulator;
  // same constructor calls as ExercisePageClient
  if (arch === 'arm') {
    emu = new ArmEmulator(instrs, ex!.asmInitialRegs, ex!.asmStackBase ?? 0xbfff0200);
  } else {
    emu = new MipsEmulator(instrs, ex!.asmInitialRegs, ex!.asmStackBase ?? 0x7ffffffc);
  }
  for (const { addr, value, size } of ex!.asmInitialMemory ?? []) emu.writeMem(addr, value, size);

  // every address the program reads or writes, plus the seeded data and the
  // stack around sp, so the scene can draw memory cells
  const watch = new Set<number>();
  for (const { addr, size } of ex!.asmInitialMemory ?? []) for (let i = 0; i < size; i += 4) watch.add(addr + i);

  const flagsOf = () => ({ ...(emu.state.flags as any) });
  const snapRegs = () => ({ ...emu.state.registers });
  const pending = () => (emu as any).pendingPC ?? null;

  const initial = { regs: snapRegs(), flags: flagsOf() };
  const steps: any[] = [];
  let n = 0;
  let endedAtHlt = false;
  // Run All caps at 500 steps. A program that hits the cap never halted.
  while (!emu.state.halted && n < 500) {
    const pcBefore = arch === 'arm' ? emu.state.registers.r15 : emu.state.registers.pc;
    const cur = emu.getCurrentInstruction();
    // pending jump as we enter the step. On MIPS this is non-null exactly when
    // the step is the delay slot, and it names where the branch will land.
    const pendingBefore = arch === 'mips' ? pending() : null;
    const inDelaySlot = pendingBefore !== null;
    const r = emu.step();
    if (!r) break;
    n++;
    // mask to the word, unsigned: a stack addr like 0xbfff01f0 is past 2^31,
    // and a signed & would turn the watch key negative
    for (const w of r.memoryWrites) watch.add((w.addr & ~3) >>> 0);
    for (const m of r.memoryReads) watch.add((m.addr & ~3) >>> 0);
    const fetched = cur ? cur.addr : r.instruction.addr;
    steps.push({
      addr: r.instruction.addr,
      pcBefore,
      fetched,
      // How far the fetch landed from where pc points. 8 on ARM (the pc+8
      // pipeline read is applied to the fetch too), 0 on MIPS.
      fetchSkew: (fetched - pcBefore) | 0,
      mnemonic: r.instruction.mnemonic,
      operands: r.instruction.operands,
      log: r.log,
      skipped: r.log.includes('(skipped'),
      inDelaySlot,
      // the target active in the delay slot, and the target a branch just set
      branchPending: pendingBefore,
      branchTarget: arch === 'mips' ? pending() : null,
      diffs: r.diffs,
      flagChanges: r.flagChanges,
      writes: r.memoryWrites,
      reads: r.memoryReads,
      regs: snapRegs(),
      flags: flagsOf(),
      halted: r.halted,
    });
    // Neither emulator treats the hlt pseudo-op as a stop. Most programs end
    // with hlt as the last line, so pc runs off and the fetch returns null.
    // mips-75 keeps real code past its hlt, so it loops the body until the
    // 500 cap. Treat reaching hlt as the end of the program.
    if (r.instruction.mnemonic.toLowerCase() === 'hlt') { endedAtHlt = true; break; }
  }

  // memory snapshot per step for the watched words. Replay from scratch so
  // each snapshot is the memory as of that step, not as of the end.
  const words = [...watch].sort((a, b) => a - b);
  const mem: Record<string, number>[] = [];
  const replay = arch === 'arm'
    ? new ArmEmulator(instrs, ex!.asmInitialRegs, ex!.asmStackBase ?? 0xbfff0200)
    : new MipsEmulator(instrs, ex!.asmInitialRegs, ex!.asmStackBase ?? 0x7ffffffc);
  for (const { addr, value, size } of ex!.asmInitialMemory ?? []) replay.writeMem(addr, value, size);
  const peek = () => Object.fromEntries(words.map(a => ['0x' + a.toString(16), replay.readMem(a, 4)]));
  const memInitial = peek();
  for (let i = 0; i < steps.length; i++) {
    replay.step();
    mem.push(peek());
  }
  steps.forEach((s, i) => (s.memory = mem[i]));

  const run = { initial: { ...initial, memory: memInitial }, steps, final: steps[steps.length - 1] };
  const quiz = (ex!.asmQuiz ?? []).map((q, i) => {
    let probe: { value: number; where: string };
    try {
      probe = PROBES[id][i](run);
    } catch (e: any) {
      // the instruction the question is about never ran
      probe = { value: NaN, where: e.message };
    }
    const typed = Number.isNaN(probe.value) ? '' : q.format === 'hex' ? '0x' + u32(probe.value).toString(16) : String(probe.value | 0);
    return {
      question: strip(q.question),
      answer: q.answer,
      format: q.format,
      hint: q.hint,
      emulator: Number.isNaN(probe.value) ? null : u32(probe.value),
      where: probe.where,
      typed,
      accepted: quizAccepts(typed, q.answer),
    };
  });

  return {
    exercise: ex!.id,
    title: ex!.title,
    unit: ex!.unitId,
    mode: ex!.mode,
    vizMode: ex!.vizMode,
    arch,
    desc: strip(ex!.desc),
    source: ex!.source.c.map(l => l.text),
    instructions: instrs.map(i => ({
      addr: i.addr, bytes: i.bytes, mnemonic: i.mnemonic, operands: i.operands, comment: i.comment,
    })),
    initialRegs: ex!.asmInitialRegs ?? {},
    initialMemory: ex!.asmInitialMemory ?? [],
    stackBase: ex!.asmStackBase ?? null,
    memWords: words,
    initial: run.initial,
    steps,
    halted: emu.state.halted,
    endedAtHlt,
    ended: emu.state.halted || endedAtHlt,
    stepCount: n,
    hitStepCap: n >= 500,
    // Diagnostics for the ARM instruction-fetch bug. getCurrentInstruction
    // reads r15, and getReg('pc') returns r15+8, so each fetch lands two
    // instructions ahead of where pc points. Net effect: pc advances by one
    // instruction per step but the fetch jumps three, so the program runs
    // roughly every third line and most quiz answers never get computed.
    pcFetchBug: arch === 'arm' && steps.some((s: any) => s.fetchSkew !== 0),
    fetchSkew: steps.length ? steps[0].fetchSkew : 0,
    executedAddrs: [...new Set(steps.map((s: any) => s.addr))].sort((a, b) => a - b),
    neverRan: instrs.map(i => i.addr).filter(a => !steps.some((s: any) => s.addr === a)),
    quiz,
    solved: quiz.length > 0 && quiz.every(q => q.accepted),
    winTitle: strip(ex!.winTitle),
    winMsg: strip(ex!.winMsg),
  };
}

// --- input-hex ------------------------------------------------------------

function runStack() {
  const bytes = (payloadHex.replace(/[^0-9a-f]/gi, '').match(/../g) || []).map(b => parseInt(b, 16));
  let extraSize = 0;
  if (ex!.ret2libc) extraSize = 8;
  else if (ex!.rop) extraSize = 40;
  else if (ex!.srop) extraSize = 44;
  else if (ex!.pivot) extraSize = 40;

  const symbols = { ...BASE_SYMBOLS };
  const sim = new StackSim({
    bufSize: ex!.bufSize ?? 16,
    retAddr: symbols.main + 0x25,
    savedEbp: 0xbfff0200,
    useCanary: ex!.canary,
    extraSize,
  });
  sim.resetForInput();
  sim.clearBlank();

  const snap = () => ({
    memory: Array.from(sim.memory),
    written: Array.from(sim.written),
    overflow: Array.from(sim.overflowAt),
    hl: sim.hlStart >= 0 ? [sim.hlStart, sim.hlEnd] : null,
  });

  const out: any = {
    exercise: ex!.id,
    title: ex!.title,
    unit: ex!.unitId,
    mode: ex!.mode,
    arch: ex!.asmArch ?? null,   // mips-77/78 don't set it, so they run as plain StackSim
    desc: strip(ex!.desc),
    source: ex!.source.c.map(l => l.text),
    gadgets: ex!.gadgets ?? {},
    symbols,
    flagAddr: ex!.flagAddr ?? null,
    magicValue: ex!.magicValue ?? null,
    layout: {
      base: sim.baseAddr, bufSize: sim.bufSize, canarySize: sim.canarySize,
      ebpSize: sim.ebpSize, retSize: sim.retSize, totalSize: sim.totalSize,
    },
    payload: bytes,
    initial: snap(),
    steps: [] as any[],
    winTitle: strip(ex!.winTitle),
    winMsg: strip(ex!.winMsg),
  };

  // TextHexInput keeps one ropState per mounted input, so start it empty
  const state: any = {};
  let flags: Record<string, boolean> = {};
  for (const step of generateExecSteps(ex!, bytes, sim, symbols)) {
    const r = execCurrentStep(step, sim, ex!, symbols, state);
    if (r.flagUpdates) flags = { ...flags, ...r.flagUpdates };
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
  out.ropState = state;
  out.retAddr = sim.getRetAddr();
  out.check = ex!.check(sim, null, symbols, flags as any);
  out.solved = out.check && out.steps.some((s: any) => s.win);
  return out;
}

const out = ex.mode === 'asm-quiz' ? runQuiz() : runStack();
console.log(JSON.stringify(out, null, 1));
