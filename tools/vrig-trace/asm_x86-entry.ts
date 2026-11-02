// Steps VRIG's own X86Emulator through the unit0-asm and unit7-x64 quiz
// exercises and writes one trace per exercise, plus a check of every quiz
// answer against what the emulator actually computed.
//
//   node dist/vrig-asm_x86.mjs traces/          # all of them
//   node dist/vrig-asm_x86.mjs traces/ asm-07   # just one

import * as fs from 'node:fs';
import * as path from 'node:path';

import { getExercise } from '@/exercises/registry';
import { X86Emulator } from '@/engine/x86/emulator';

const IDS = [
  'asm-01', 'asm-02', 'asm-03', 'asm-04', 'asm-05', 'asm-06', 'asm-07', 'asm-08', 'asm-09', 'asm-10',
  'x64-29', 'x64-30', 'x64-31', 'x64-32', 'x64-33', 'x64-34', 'x64-35', 'x64-36',
];

const strip = (s: string) => s.replace(/<[^>]+>/g, '');

// AsmViz's hex(): (n >>> 0) padded to the arch width. Copied, not imported,
// because AsmViz.tsx drags React in with it.
const vizHex = (n: number, w: number) => '0x' + (n >>> 0).toString(16).padStart(w, '0');

// Same construction as ExercisePageClient
function makeEmu(ex: any): X86Emulator {
  const emu = new X86Emulator(ex.asmInstructions, ex.asmInitialRegs, ex.asmStackBase ?? 0xbfff0200,
    ex.asmArch ?? 'x86');
  for (const { addr, value, size } of ex.asmInitialMemory ?? []) emu.writeMem(addr, value, size);
  return emu;
}

type Step = any;

// sequenced: if fall-through lands between instructions (the x64 movabs
// lines only list 2 of their 10 bytes), put rip on the next listed line
// instead of halting. VRIG itself doesn't do this, the trace records where.
function run(ex: any, sequenced: boolean, watch: number[]) {
  const emu = makeEmu(ex);
  const w = (ex.asmArch ?? 'x86') === 'x86' ? 4 : 8;
  const ip = w === 4 ? 'eip' : 'rip';
  const idxOf = new Map<number, number>(ex.asmInstructions.map((ins: any, i: number) => [ins.addr, i]));
  const snap = () => ({
    regs: { ...emu.state.registers },
    flags: { ...emu.state.flags },
    // what VRIG's own readMem gives back for each watched word
    words: Object.fromEntries(watch.map(a => [a, emu.readMem(a, w)])),
    bytes: [...emu.memory.entries()].sort((a, b) => a[0] - b[0]),
  });

  const initial = snap();
  const steps: Step[] = [];
  let stop = 'halted';
  let prevIdx = -1;
  for (let n = 0; n < 500; n++) {  // AsmQuizInput's Run All cap
    if (emu.state.halted) break;
    let patched = false;
    if (sequenced && !idxOf.has(emu.state.registers[ip]) && prevIdx >= 0 && prevIdx + 1 < ex.asmInstructions.length) {
      emu.state.registers[ip] = ex.asmInstructions[prevIdx + 1].addr;
      patched = true;
    }
    const at = emu.state.registers[ip];
    let r: any;
    try {
      r = emu.step();
    } catch (e: any) {
      steps.push({ idx: idxOf.get(at) ?? -1, addr: at, patched, error: String(e.message ?? e), ...snap() });
      stop = 'error';
      break;
    }
    if (!r) {
      stop = idxOf.has(at) ? 'halted' : 'fell-off';
      break;
    }
    prevIdx = idxOf.get(r.instruction.addr)!;
    steps.push({
      idx: prevIdx, addr: r.instruction.addr, patched,
      diffs: r.diffs, flagChanges: r.flagChanges,
      writes: r.memoryWrites, reads: r.memoryReads,
      log: r.log, halted: r.halted,
      ...snap(),
    });
  }
  return { initial, steps, stop, emu };
}

function last(steps: Step[], pred: (s: Step) => boolean): Step {
  for (let i = steps.length - 1; i >= 0; i--) if (pred(steps[i])) return { ...steps[i], i };
  throw new Error('no step matches');
}
const first = (steps: Step[], pred: (s: Step, i: number) => boolean): Step => {
  const i = steps.findIndex(pred);
  if (i < 0) throw new Error('no step matches');
  return { ...steps[i], i };
};
const text = (ex: any, s: Step) => {
  const ins = ex.asmInstructions[s.idx];
  return `${ins.mnemonic} ${ins.operands}`.trim();
};
const is = (ex: any, t: string) => (s: Step) => s.idx >= 0 && text(ex, s) === t;
const ok = (s: Step) => !s.error;
const regNum = (r: string) => parseInt(r.replace(/^r/, '').replace(/d$/, ''), 10);

// Each quiz question gets a probe: where in the run it's answered, and what
// the run says the answer is.
//   emulator  the value is a register, flag, or memory word VRIG computed
//   derived   arithmetic on emulator values (counts, deltas, a hypothetical)
//   concept   a multiple-choice question; the probe picks the choice the
//             run supports, but the numbering itself is the question's
type Probe = { step: number; value: number | bigint; kind: 'emulator' | 'derived' | 'concept'; reg?: string; flag?: string; addr?: number; why: string };

const PROBES: Record<string, (ex: any, st: Step[], w: number) => Probe[]> = {
  'asm-01': (ex, st) => {
    const a = first(st, is(ex, 'mov ebx, eax')), b = last(st, ok);
    return [
      { step: a.i, value: a.regs.ebx, kind: 'emulator', reg: 'ebx', why: 'ebx after mov ebx, eax' },
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax at hlt' },
    ];
  },
  'asm-02': (ex, st) => {
    const a = first(st, is(ex, 'mov ecx, [0x08049000]')), b = last(st, ok);
    return [
      { step: a.i, value: a.regs.ecx, kind: 'emulator', reg: 'ecx', why: 'ecx after the load' },
      { step: b.i, value: b.regs.edx, kind: 'emulator', reg: 'edx', why: 'edx at hlt' },
    ];
  },
  'asm-03': (ex, st) => {
    const a = first(st, s => s.idx >= 0 && text(ex, s) === 'pop ecx'), b = last(st, ok);
    return [
      { step: a.i, value: a.regs.ecx, kind: 'emulator', reg: 'ecx', why: 'ecx after pop ecx' },
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax at hlt' },
    ];
  },
  'asm-04': (ex, st) => {
    const a = first(st, is(ex, 'dec eax')), b = first(st, is(ex, 'mul ecx'));
    return [
      { step: a.i, value: a.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax after dec eax' },
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax after mul ecx' },
    ];
  },
  'asm-05': (ex, st) => {
    const a = first(st, is(ex, 'cmp eax, ebx')), b = first(st, is(ex, 'cmp eax, ecx')), c = first(st, is(ex, 'test eax, eax'));
    return [
      { step: a.i, value: +a.flags.ZF, kind: 'emulator', flag: 'ZF', why: 'ZF after cmp eax, ebx' },
      { step: b.i, value: +b.flags.CF, kind: 'emulator', flag: 'CF', why: 'CF after cmp eax, ecx' },
      { step: c.i, value: +c.flags.ZF, kind: 'emulator', flag: 'ZF', why: 'ZF after test eax, eax' },
    ];
  },
  'asm-06': (ex, st) => {
    const b = last(st, ok);
    const body = st.filter(is(ex, 'add ebx, eax'));
    return [
      { step: b.i, value: b.regs.ebx, kind: 'emulator', reg: 'ebx', why: 'ebx at hlt' },
      { step: last(st, is(ex, 'jl 0x0804800a')).i, value: body.length, kind: 'derived', why: 'times add ebx, eax ran' },
    ];
  },
  'asm-07': (ex, st) => {
    const call = first(st, s => s.idx >= 0 && ex.asmInstructions[s.idx].mnemonic === 'call');
    const b = last(st, ok);
    return [
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax at hlt' },
      { step: call.i, value: call.writes[0].value, kind: 'emulator', addr: call.writes[0].addr, why: 'word call wrote to the stack' },
    ];
  },
  'asm-08': (ex, st) => {
    const a = first(st, is(ex, 'mov ecx, [eax+ebx*4]')), b = first(st, is(ex, 'lea edx, [eax+8]'));
    return [
      { step: a.i, value: a.regs.ecx, kind: 'emulator', reg: 'ecx', why: 'ecx after the indexed load' },
      { step: b.i, value: b.regs.edx, kind: 'emulator', reg: 'edx', why: 'edx after lea' },
    ];
  },
  'asm-09': (ex, st) => {
    const b = last(st, ok), sub = first(st, is(ex, 'sub esp, 16'));
    const before = sub.i > 0 ? st[sub.i - 1].regs.esp : 0;
    return [
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax at hlt' },
      { step: sub.i, value: before - sub.regs.esp, kind: 'derived', reg: 'esp', why: 'esp drop across sub esp, 16' },
    ];
  },
  'asm-10': (ex, st, w) => {
    const ret = first(st, is(ex, 'ret'));
    const callee = ex.asmInstructions.find((i: any) => i.mnemonic === 'call').operands;
    // after ret, who pops the two argument words? the instruction's address
    // says which function it lives in
    const clean = first(st, (s, i) => i > ret.i && s.idx >= 0 && s.regs.esp - st[i - 1].regs.esp === 2 * w);
    return [
      { step: ret.i, value: ret.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax when add_nums returns' },
      { step: clean.i, value: clean.addr < parseInt(callee, 16) ? 1 : 2, kind: 'concept', reg: 'esp', why: `${text(ex, clean)} at ${vizHex(clean.addr, 8)} is in main` },
    ];
  },
  'x64-29': (ex, st) => {
    const p = first(st, is(ex, 'push rbp')), a = first(st, is(ex, 'add rax, [rbp-16]'));
    return [
      { step: p.i, value: (p.i > 0 ? st[p.i - 1].regs.rsp : (ex.asmStackBase ?? 0xbfff0200)) - p.regs.rsp, kind: 'derived', reg: 'rsp', why: 'rsp drop across push rbp' },
      { step: a.i, value: a.regs.rax, kind: 'emulator', reg: 'rax', why: 'rax after add' },
    ];
  },
  'x64-30': (ex, st) => {
    const call = first(st, s => s.idx >= 0 && ex.asmInstructions[s.idx].mnemonic === 'call');
    const args = (ex.source.c.map((l: any) => l.text).join('\n').match(/add3\((\d+),\s*(\d+),\s*(\d+)\)/) ?? []).slice(1).map(Number);
    const choices = ['edi', 'esi', 'edx'];  // the hint's 1=RDI, 2=RSI, 3=RDX, as the 32-bit names the code writes
    const pick = choices.findIndex(r => call.regs[r] === args[0]) + 1;
    const b = last(st, ok);
    return [
      { step: call.i, value: pick, kind: 'concept', reg: choices[pick - 1], why: `the register holding add3's first argument (${args[0]}) at the call` },
      { step: b.i, value: b.regs.eax, kind: 'emulator', reg: 'eax', why: 'eax at hlt' },
    ];
  },
  'x64-31': (ex, st) => {
    const retSlot = first(st, s => s.idx >= 0 && /return addr/i.test(ex.asmInstructions[s.idx].comment ?? ''));
    const gadgetLine = ex.asmInstructions[retSlot.idx - 1];
    return [
      { step: retSlot.i, value: /pop rdi/.test(gadgetLine.comment) ? 1 : 2, kind: 'concept', addr: retSlot.writes[0].addr, why: 'the return slot gets the address VRIG labels as the pop rdi gadget' },
      { step: retSlot.i, value: retSlot.writes[0].value, kind: 'emulator', addr: retSlot.writes[0].addr, why: 'word pushed over the return address' },
    ];
  },
  'x64-32': (ex, st) => {
    const pops = st.map((s, i) => ({ ...s, i })).filter(s => s.idx >= 0 && !s.error && ex.asmInstructions[s.idx].mnemonic === 'pop');
    const mv = first(st, s => !s.error && (s.diffs ?? []).some((d: any) => d.reg === 'rdx'));
    const src = ex.asmInstructions[mv.idx].operands.split(',')[1].trim();
    if (mv.regs.rdx !== mv.regs[src]) throw new Error('rdx did not come from ' + src);
    return [
      { step: pops[pops.length - 1].i, value: pops.length, kind: 'derived', why: 'pop instructions run before ret' },
      { step: mv.i, value: regNum(src), kind: 'derived', reg: 'rdx', why: `rdx was copied from ${src}` },
    ];
  },
  'x64-33': (ex, st) => {
    const off = first(st, is(ex, 'mov rax, 0x4526a'));
    const base = BigInt((ex.asmQuiz[1].question.match(/0x[0-9a-f]+/i) ?? ['0'])[0]);
    return [
      { step: off.i, value: off.regs.rax, kind: 'emulator', reg: 'rax', why: 'rax after the offset load' },
      { step: last(st, ok).i, value: base + BigInt(off.regs.rax), kind: 'derived', reg: 'rax', why: "the question's libc base plus that offset" },
    ];
  },
  'x64-34': (ex, st, w) => {
    const c = first(st, ok);
    return [
      { step: c.i, value: c.regs.rax & 0xff, kind: 'emulator', reg: 'rax', why: 'low byte of the canary in rax' },
      { step: last(st, ok).i, value: (w - 1) * 256, kind: 'derived', why: '7 unknown bytes, 256 guesses each' },
    ];
  },
  'x64-35': (ex, st) => {
    const andStep = first(st, s => s.idx >= 0 && ex.asmInstructions[s.idx].mnemonic === 'and');
    const mask = parseInt(ex.asmInstructions[andStep.idx].operands.split(',')[1], 16);
    let low = 0;
    while (!((mask >>> low) & 1)) low++;
    const win = first(st, s => !s.error && (s.diffs ?? []).some((d: any) => d.reg === 'rdx'));
    return [
      { step: andStep.i, value: low, kind: 'derived', reg: 'rax', why: 'zero bits at the bottom of the page mask' },
      { step: win.i, value: win.regs.rdx & 0xffff, kind: 'emulator', reg: 'rdx', why: 'low two bytes of win() in rdx' },
    ];
  },
  'x64-36': (ex, st) => {
    const leaks = st.map((s, i) => ({ ...s, i })).filter(s => s.idx >= 0 && /Leaked/.test(ex.asmInstructions[s.idx].comment ?? ''));
    const got = first(st, s => s.idx >= 0 && /GOT/.test(ex.asmInstructions[s.idx].comment ?? ''));
    return [
      { step: leaks[leaks.length - 1].i, value: leaks.length, kind: 'derived', why: 'lines that load a leaked address' },
      { step: got.i, value: 1, kind: 'concept', reg: 'rax', why: 'lea points rax at the GOT slot for puts' },
    ];
  },
};

// Where VRIG's emulator throws, work out by hand what the line would have
// done, from the stopped emulator's own registers and memory. The video marks
// these as worked by hand, not run.
const STALLS: Record<string, (emu: X86Emulator, ins: any) => any> = {
  'x64-32': emu => {
    const r = emu.state.registers;
    const slot = r.r12 + r.rbx * 8;
    return { edi: r.r15 >>> 0, slot, target: emu.readMem(slot, 8), rdx: r.rdx, rsi: r.rsi };
  },
  'x64-35': (emu, ins) => {
    // mov ax, imm16 swaps the low two bytes and leaves the rest
    const r = emu.state.registers;
    const imm = parseInt(ins.operands.split(',')[1], 16) & 0xffff;
    const after = ((r.rax & ~0xffff) | imm) >>> 0;
    return { imm, before: r.rax, after, win: r.rdx, matches: after === r.rdx };
  },
};

function exportOne(id: string, outDir: string) {
  const ex: any = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  const arch = ex.asmArch ?? 'x86';
  const w = arch === 'x86' ? 4 : 8;
  const hexW = arch === 'x86' ? 8 : 16;

  // first pass just to find which memory words get touched
  const scout = run(ex, true, []);
  const touched = new Set<number>();
  const base = ex.asmStackBase ?? 0xbfff0200;
  const sp = w === 4 ? 'esp' : 'rsp';
  for (const { addr } of ex.asmInitialMemory ?? []) touched.add(addr);
  for (const s of scout.steps) {
    for (const m of [...(s.writes ?? []), ...(s.reads ?? [])]) touched.add(m.addr - (((m.addr - base) % w) + w) % w);
    // every slot sp passes over, so a push shows up even before it's written
    touched.add(s.regs[sp]);
  }
  // fill the stack in between, so the column has no holes where nothing was touched
  const sps = [scout.initial.regs[sp], ...scout.steps.map((s: Step) => s.regs[sp])];
  const near = [...touched].filter(a => a >= Math.min(...sps) - 4 * w && a <= Math.max(base, ...sps) + 8 * w);
  if (near.length) for (let a = Math.min(...near); a <= Math.max(...near); a += w) touched.add(a);
  const watch = [...touched].sort((a, b) => a - b);

  const faithful = run(ex, false, watch);
  const seq = run(ex, true, watch);
  const patchedRun = seq.steps.some((s: Step) => s.patched);
  const used = patchedRun ? seq : faithful;

  const probes = PROBES[id](ex, used.steps, w);
  const quiz = ex.asmQuiz.map((q: any, i: number) => {
    const p = probes[i];
    if (typeof p.step !== 'number') throw new Error(`${id} Q${i + 1}: probe has no step`);
    // AsmQuizInput compares the low 32 bits only
    const lo = (v: number | bigint) => Number(BigInt(v) & 0xffffffffn);
    const correct = lo(p.value) === lo(q.answer);
    return {
      question: q.question, hint: q.hint ?? null, answer: q.answer, format: q.format ?? 'hex',
      // what VRIG logs on a correct answer, bug and all for > 32 bits
      vrigShows: q.format === 'decimal' ? String(q.answer) : '0x' + (q.answer >>> 0).toString(16),
      probe: { ...p, value: typeof p.value === 'bigint' ? Number(p.value) : p.value },
      correct,
    };
  });

  const out = {
    exercise: ex.id,
    unit: ex.unitId,
    title: ex.title,
    desc: strip(ex.desc),
    arch, word: w, hexW,
    stackBase: base,
    vizMode: ex.vizMode,
    source: ex.source.c.map((l: any) => ({ text: l.text, cls: l.cls })),
    instructions: ex.asmInstructions.map((i: any) => ({ ...i, text: `${i.mnemonic} ${i.operands}`.trim() })),
    initialRegs: ex.asmInitialRegs ?? {},
    initialMemory: ex.asmInitialMemory ?? [],
    watch,
    // what clicking Run All in VRIG does
    vrigRun: { stop: faithful.stop, steps: faithful.steps.length,
               error: faithful.steps.find((s: Step) => s.error)?.error ?? null },
    // the run the video plays. same as vrigRun unless fall-through had to be patched
    patched: patchedRun,
    stop: used.stop,
    initial: used.initial,
    steps: used.steps,
    stall: used.stop === 'error' && STALLS[id] ? STALLS[id](used.emu, ex.asmInstructions[used.steps[used.steps.length - 1].idx]) : null,
    quiz,
    solved: quiz.every((q: any) => q.correct),
    winTitle: ex.winTitle,
    winMsg: strip(ex.winMsg),
  };
  fs.writeFileSync(path.join(outDir, `${id}.json`), JSON.stringify(out, null, 1));
  const bad = quiz.filter((q: any) => !q.correct).length;
  console.log(`${id}: ${used.steps.length} steps (${out.stop}${patchedRun ? ', patched' : ''}), vrig run ${faithful.steps.length}/${faithful.stop}, quiz ${quiz.length - bad}/${quiz.length}`);
}

const [outDir = 'traces', ...only] = process.argv.slice(2);
for (const id of only.length ? only : IDS) exportOne(id, outDir);
