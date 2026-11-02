// Advanced asm-quiz exercises (mitigations, JIT spray, Spectre, BROP, seccomp,
// DOP, kernel layout, shellcode). Runs each one on VRIG's own X86Emulator the
// way ExercisePageClient builds it, grades the quiz answers with the same
// comparison AsmQuizInput uses, and writes traces/<id>.json.
//
//   node dist/vrig-asm_adv.mjs <out-dir>

import { writeFileSync } from 'node:fs';
import { getExercise } from '@/exercises/registry';
import { X86Emulator } from '@/engine/x86/emulator';
import { AsmInstruction } from '@/engine/x86/types';

const OUT = process.argv[2] ?? 'traces';

const strip = (s: string) => s.replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]+>/g, '')
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();

// AsmQuizInput.parseAnswer + doSubmit, copied because they live inside the component
function parseAnswer(text: string): number | null {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  if (t.startsWith('0x')) return parseInt(t, 16);
  if (/^[0-9a-f]+h$/.test(t)) return parseInt(t.slice(0, -1), 16);
  if (/^[0-9]+$/.test(t)) return parseInt(t, 10);
  if (/^[0-9a-f]+$/.test(t) && t.length > 2) return parseInt(t, 16);
  return parseInt(t, 10);
}
const graded = (typed: string, answer: number) => {
  const p = parseAnswer(typed);
  return p !== null && (p & 0xFFFFFFFF) === (answer & 0xFFFFFFFF);
};
// what you'd type: the expected string VRIG logs on a correct answer
const typedFor = (q: any) => q.format === 'decimal' ? String(q.answer) : '0x' + q.answer.toString(16);

function makeEmu(ex: any, instrs?: AsmInstruction[], regs?: Record<string, number>, mem?: any[]) {
  const emu = new X86Emulator(instrs ?? ex.asmInstructions, regs ?? ex.asmInitialRegs,
    ex.asmStackBase ?? 0xbfff0200, ex.asmArch ?? 'x86');
  for (const { addr, value, size } of (mem ?? ex.asmInitialMemory ?? [])) emu.writeMem(addr, value, size);
  return emu;
}

// Step to halt, snapshotting registers after every instruction. An operand
// the emulator can't parse throws from inside step(), which leaves its
// readMem/writeMem wrappers installed. Record the error and stop there.
function walk(emu: X86Emulator, max = 200) {
  const steps: any[] = [];
  const init = { regs: { ...emu.state.registers }, flags: { ...emu.state.flags } };
  while (!emu.state.halted && steps.length < max) {
    const cur = emu.getCurrentInstruction();
    let r;
    try {
      r = emu.step();
    } catch (e: any) {
      delete (emu as any).readMem;
      delete (emu as any).writeMem;
      steps.push({ instr: cur, error: String(e.message ?? e), regs: { ...emu.state.registers } });
      return { init, steps, error: String(e.message ?? e) };
    }
    if (!r) {
      steps.push({ instr: null, fetchFault: true, eip: emu.state.registers[emu.state.arch === 'x86' ? 'eip' : 'rip'] });
      break;
    }
    steps.push({
      instr: r.instruction, diffs: r.diffs, flagChanges: r.flagChanges, flags: { ...emu.state.flags },
      memWrites: r.memoryWrites, memReads: r.memoryReads, log: r.log, halted: r.halted,
      regs: { ...emu.state.registers },
    });
  }
  return { init, steps, error: null };
}

function base(id: string) {
  const ex: any = getExercise(id);
  if (!ex) throw new Error('no exercise ' + id);
  const quiz = (ex.asmQuiz ?? []).map((q: any) => ({
    question: strip(q.question), answer: q.answer, format: q.format, hint: strip(q.hint ?? ''),
    typed: typedFor(q), correct: graded(typedFor(q), q.answer),
  }));
  return {
    ex,
    out: {
      exercise: ex.id, unit: ex.unitId, title: ex.title, desc: strip(ex.desc), mode: ex.mode,
      arch: ex.asmArch ?? 'x86', source: (ex.source?.c ?? []).map((l: any) => l.text),
      instructions: ex.asmInstructions ?? [], initialMemory: ex.asmInitialMemory ?? [],
      protections: ex.protections ?? [], auxViz: ex.auxViz ?? [],
      winTitle: ex.winTitle, winMsg: strip(ex.winMsg), realWorld: ex.realWorld ?? null,
      quiz, quizSolved: quiz.length > 0 && quiz.every((q: any) => q.correct),
    } as any,
  };
}

// each check is [what, emulator/derived value, quiz answer]
function verdict(out: any, checks: Array<[string, number, number]>) {
  out.checks = checks.map(([what, got, want]) => ({ what, got, want, ok: got === want }));
  out.solved = (out.quiz.length === 0 || out.quizSolved) && out.checks.every((c: any) => c.ok);
}

const save = (out: any) => {
  writeFileSync(`${OUT}/${out.exercise}.json`, JSON.stringify(out, null, 1));
  console.log(`${out.exercise}: solved=${out.solved} steps=${out.run?.steps?.length ?? 0}` +
    (out.run?.error ? ` error="${out.run.error}"` : ''));
};

const regAfter = (run: any, addr: number, reg: string) =>
  run.steps.find((s: any) => s.instr?.addr === addr).regs[reg];

// ---------------------------------------------------------------- mit-79
{
  const { ex, out } = base('mit-79');
  out.run = walk(makeEmu(ex));
  // the Run 1 / Run 2 table lives in the source comments
  out.runs = out.source.flatMap((l: string) => {
    const m = l.match(/^\/\/ (\.?\w+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s*(.*)$/);
    return m ? [{ name: m[1], run1: parseInt(m[2], 16), run2: parseInt(m[3], 16), note: m[4] }] : [];
  });
  const text = out.runs.find((r: any) => r.name === '.text');
  verdict(out, [
    ['2^12', 2 ** 12, ex.asmQuiz[0].answer],
    ['2^28', 2 ** 28, ex.asmQuiz[1].answer],
    ['eax (.text base, run 1)', regAfter(out.run, 0x08048000, 'eax'), ex.asmQuiz[2].answer],
    ['.text base, run 2', text.run2, ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- mit-83
{
  const { ex, out } = base('mit-83');
  out.run = walk(makeEmu(ex));
  // real lea [rip+d] semantics: address of the *next* instruction plus d.
  // VRIG's emulator uses the current rip and masks the sum to 32 bits, so
  // keep both and let the scene show the real one.
  const leas = (instrs: AsmInstruction[]) => instrs.filter(i => i.mnemonic === 'lea').map(i => {
    const disp = parseInt(i.operands.match(/0x([0-9a-f]+)/)![1], 16);
    const next = i.addr + i.bytes.length;
    return { addr: i.addr, reg: i.operands.split(',')[0], disp, next, value: next + disp };
  });
  const BASE1 = 0x555555554000, BASE2 = 0x7fff00000000;  // BASE2 from quiz question 2
  const moved = ex.asmInstructions.map((i: AsmInstruction) => ({ ...i, addr: i.addr - BASE1 + BASE2 }));
  out.bases = [BASE1, BASE2];
  out.lea = { run1: leas(ex.asmInstructions), run2: leas(moved) };
  out.emuLea = out.lea.run1.map((l: any) => ({ reg: l.reg, emu: regAfter(out.run, l.addr, l.reg) }));
  const absolute = ex.asmInstructions.find((i: AsmInstruction) => i.operands.startsWith('rcx'));
  out.absolute = parseInt(absolute.operands.split(',')[1], 16);
  const r1 = out.lea.run1[0], r2 = out.lea.run2[0];
  verdict(out, [
    ['lea rax (real semantics)', r1.value, ex.asmQuiz[0].answer],
    ['rax - base same in both runs', Number(r1.value - BASE1 === r2.value - BASE2), ex.asmQuiz[1].answer],
    ['absolute rcx still inside moved image', Number(out.absolute >= BASE2 && out.absolute < BASE2 + 0x3000),
      ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- mit-86
{
  const { ex, out } = base('mit-86');
  out.run = walk(makeEmu(ex));
  const fs = ex.asmInstructions.find((i: AsmInstruction) => i.operands.includes('fs:'));
  out.checksec = out.source.flatMap((l: string) => {
    const m = l.match(/^\/\/ (\w+):\s+(.+)$/);
    return m ? [{ name: m[1], value: m[2] }] : [];
  });
  out.blocks = out.source.flatMap((l: string) => {
    const m = l.match(/^\/\/ (\w+)\s+-> (.+)$/);
    return m ? [{ name: m[1], what: m[2] }] : [];
  });
  verdict(out, [
    ['fs offset in canary load', parseInt(fs.operands.match(/fs:(0x[0-9a-f]+)/)[1], 16), ex.asmQuiz[3].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv-91
{
  const { ex, out } = base('adv-91');
  out.run = walk(makeEmu(ex));
  verdict(out, [
    ['eax after loading obj1 vptr', regAfter(out.run, 0x08048005, 'eax'), ex.asmQuiz[0].answer],
    ['edx = vtable1[0]', regAfter(out.run, 0x08048007, 'edx'), ex.asmQuiz[1].answer],
    ['esi = vtable2[1]', regAfter(out.run, 0x08048013, 'esi'), ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv2-95
{
  const { ex, out } = base('adv2-95');
  out.run = walk(makeEmu(ex));
  // VRIG has no decoder, so decode the JIT page from +1 with the three
  // opcodes the exercise itself names: 90 nop, 3c ib cmp al, 35 id xor eax
  const page: number[] = ex.asmInstructions.flatMap((i: AsmInstruction) => i.bytes);
  const start = ex.asmInstructions[0].addr;
  const decode = (from: number, upto: number) => {
    const res: any[] = [];
    let p = from;
    while (p < upto) {
      const b = page[p];
      let len = 1, text = '';
      if (b === 0x90) text = 'nop';
      else if (b === 0x3c) { len = 2; text = `cmp al, 0x${page[p + 1].toString(16)}`; }
      else if (b === 0x35) { len = 5; text = 'xor eax, 0x' + page.slice(p + 1, p + 5).reverse().map(x => x.toString(16).padStart(2, '0')).join(''); }
      else if (b === 0xb8) { len = 5; text = 'mov eax, ...'; }
      else if (b === 0xf4) text = 'hlt';
      else text = '??';
      res.push({ off: p, addr: start + p, len, bytes: page.slice(p, p + len), text });
      p += len;
    }
    return res;
  };
  const xor1 = ex.asmInstructions[1];
  const from = xor1.addr - start + 1;
  out.page = page;
  out.pageBase = start;
  out.entry = start + from;
  out.unaligned = decode(from, page.length - 1);
  const firstRun = out.unaligned.findIndex((d: any) => d.text !== 'nop');
  verdict(out, [
    ['first byte at xor+1', page[from], ex.asmQuiz[0].answer],
    ['nops before first non-nop', firstRun, ex.asmQuiz[1].answer],
    ['R+W+X flag count', 'RWX'.length, ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv2-97
{
  const { ex, out } = base('adv2-97');
  out.run = walk(makeEmu(ex));  // architectural: jge is taken, the loads never retire
  // Speculative window: the same three instructions VRIG lists as the
  // SPECULATIVE path, run from the state at the branch. The secret byte at
  // array1[64] is the 0x41 from quiz question 3.
  const SECRET = ex.asmQuiz[2].question.match(/is (0x[0-9a-f]+)/)[1];
  const atBranch = out.run.steps.find((s: any) => s.instr?.mnemonic === 'jge');
  const specInstrs = ex.asmInstructions.filter((i: AsmInstruction) => i.comment?.includes('SPECULATIVE') || i.mnemonic === 'shl');
  const specRegs = { ...out.run.steps[1].regs, eip: specInstrs[0].addr };
  const mem = [...ex.asmInitialMemory, { addr: 0x0804b000 + specRegs.eax, value: parseInt(SECRET, 16), size: 1 }];
  const spec = walk(makeEmu(ex, specInstrs, specRegs, mem));
  out.secret = parseInt(SECRET, 16);
  out.spec = spec;
  out.branchTaken = atBranch.regs.eip === 0x0804801b;
  const ld = spec.steps[0].memReads[0];
  const probe = spec.steps[2].memReads[0];
  out.array2 = 0x0804c000;
  out.probeAddr = probe.addr;
  verdict(out, [
    ['speculative load address', ld.addr, ex.asmQuiz[0].answer],
    ['ebx survives rollback', 0, ex.asmQuiz[1].answer],  // the architectural run never wrote ebx
    ['array2 offset cached', probe.addr - out.array2, ex.asmQuiz[2].answer],
    ['architectural ebx', out.run.steps.at(-1).regs.ebx, 0],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv2-98
{
  const { ex, out } = base('adv2-98');
  out.run = walk(makeEmu(ex));
  // the four canary bytes are the guesses loaded into eax..edx
  out.canary = ['eax', 'ebx', 'ecx', 'edx'].map((r, i) => regAfter(out.run, ex.asmInstructions[i].addr, r));
  out.tries = out.canary.map((b: number) => b + 1);  // counting up from 0x00
  verdict(out, [
    ['4 bytes x 256 guesses', 4 * 256, ex.asmQuiz[0].answer],
    ['stop gadget = hang', 2, ex.asmQuiz[1].answer],
    ['canary byte 0', out.canary[0], ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv2-100
{
  const { ex, out } = base('adv2-100');
  out.run = walk(makeEmu(ex));  // int 0x80 halts the emulator: that's the SIGSYS kill
  const tail = ex.asmInstructions.filter((i: AsmInstruction) => i.addr >= 0x08048010);
  out.allowed = walk(makeEmu(ex, tail));
  const kill = out.run.steps.at(-1);
  out.killed = { eax: kill.regs.eax, at: kill.instr.addr };
  verdict(out, [
    ['eax at the blocked int 0x80 = execve', kill.regs.eax, 11],
    ['SIGSYS', 31, ex.asmQuiz[0].answer],
    ['x86-64 write', 1, ex.asmQuiz[1].answer],
    ['PROT_READ|PROT_WRITE|PROT_EXEC', 1 | 2 | 4, ex.asmQuiz[2].answer],
    ['write path eax', out.allowed.steps.at(-1).regs.eax, 4],
  ]);
  save(out);
}

// ---------------------------------------------------------------- adv2-102
{
  const { ex, out } = base('adv2-102');
  // as shipped there are no records in memory, so the loop reads zeros and exits
  out.run = walk(makeEmu(ex));
  // then the attacker's records: two LOAD ops that copy a secret word out to
  // a buffer the program later prints. struct op { type, src, dst, next }
  const REC = 0x0804a000, SECRET = 0x0804b000, OUTBUF = 0x0804c000;
  const records = [
    { at: REC, type: 1, src: SECRET, dst: OUTBUF, next: REC + 0x10 },
    { at: REC + 0x10, type: 1, src: SECRET + 4, dst: OUTBUF + 4, next: 0 },
  ];
  const mem = records.flatMap(r => [
    { addr: r.at, value: r.type, size: 4 }, { addr: r.at + 4, value: r.src, size: 4 },
    { addr: r.at + 8, value: r.dst, size: 4 }, { addr: r.at + 12, value: r.next, size: 4 },
  ]);
  const secret = [0x73736170, 0x64726f77];  // "password", little-endian words
  mem.push({ addr: SECRET, value: secret[0], size: 4 }, { addr: SECRET + 4, value: secret[1], size: 4 });
  const emu = makeEmu(ex, undefined, undefined, mem);
  out.attack = walk(emu);
  out.records = records;
  out.secretAddr = SECRET;
  out.outAddr = OUTBUF;
  out.secret = secret;
  out.outAfter = [emu.readMem(OUTBUF, 4), emu.readMem(OUTBUF + 4, 4)];
  const ld = ex.asmInstructions.find((i: AsmInstruction) => i.addr === 0x08048012);
  const pcs = new Set(out.attack.steps.map((s: any) => s.instr?.addr));
  verdict(out, [
    ['0x08048012 reads [edx]', Number(ld.operands === 'eax, [edx]'), ex.asmQuiz[1].answer],
    ['secret copied to out buffer', Number(out.outAfter.every((v: number, i: number) => v === secret[i])), 1],
    ['every pc is a listed instruction', Number([...pcs].every(a => ex.asmInstructions.some((i: any) => i.addr === a))), 1],
    ['Turing complete', 1, ex.asmQuiz[0].answer],
    ['CFI detects', 0, ex.asmQuiz[2].answer],
  ]);
  save(out);
}

// ---------------------------------------------------------------- kern-103
{
  const { ex, out } = base('kern-103');
  const cmt = out.source.join('\n');
  const kbase = cmt.match(/start at 0x([0-9a-f]+)/)[1];
  out.kernelBase = kbase;  // string, too wide for a double to round-trip
  const pages = Number(cmt.match(/Kernel stack: (\d+) pages/)[1]);
  const kb = Number(cmt.match(/\((\d+)KB\)/)[1]);
  const bits = Number(cmt.match(/KASLR adds (\d+) bits/)[1]);
  out.stackPages = pages;
  out.stackKB = kb;
  out.kaslrBits = bits;
  out.kaslrSlots = 2 ** bits;
  const trailing = kbase.slice('ffff8000'.length);
  verdict(out, [
    ['ring', 0, ex.asmQuiz[0].answer],
    ['zero nibbles after ffff8000', trailing.length * Number(/^0+$/.test(trailing)), ex.asmQuiz[1].answer],
    ['stack pages', pages, ex.asmQuiz[2].answer],
    ['16KB / 4KB', kb / 4, ex.asmQuiz[2].answer],
    ['KASLR bits', bits, ex.asmQuiz[3].answer],
    ['512 slots', 2 ** bits, 512],
  ]);
  save(out);
}

// ---------------------------------------------------------------- gap-113
{
  const { ex, out } = base('gap-113');
  out.steps = ex.steps.map((s: any) => ({ cls: s.log[0], msg: strip(s.log[1]), srcLine: s.srcLine ?? null, done: !!s.done }));
  const fin = ex.steps.find((s: any) => s.done).log[1];
  const bytes: number[] = fin.match(/<code>([0-9a-f ]+)<\/code>/)[1].split(' ').map((b: string) => parseInt(b, 16));
  const names: string[] = strip(fin).split('\n').at(-1)!.replace(/\. No null bytes!$/, '').split(' → ');
  // instruction lengths for the handful of opcodes this shellcode uses
  const LEN: Record<number, number> = { 0x31: 2, 0x50: 1, 0x68: 5, 0x89: 2, 0xb0: 2, 0xcd: 2 };
  const R: Record<number, string> = { 0xc0: 'eax, eax', 0xc9: 'ecx, ecx', 0xd2: 'edx, edx', 0xe3: 'ebx, esp' };
  const instrs: AsmInstruction[] = [];
  let addr = 0xbfff0100, p = 0;  // somewhere in the overflowed buffer
  while (p < bytes.length) {
    const b = bytes[p], len = LEN[b], raw = bytes.slice(p, p + len);
    let mnemonic = '', operands = '';
    if (b === 0x31) { mnemonic = 'xor'; operands = R[raw[1]]; }
    else if (b === 0x50) { mnemonic = 'push'; operands = 'eax'; }
    else if (b === 0x68) { mnemonic = 'push'; operands = '0x' + raw.slice(1).reverse().map(x => x.toString(16).padStart(2, '0')).join(''); }
    else if (b === 0x89) { mnemonic = 'mov'; operands = R[raw[1]]; }
    else if (b === 0xb0) { mnemonic = 'mov'; operands = `al, 0x${raw[1].toString(16).padStart(2, '0')}`; }
    else if (b === 0xcd) { mnemonic = 'int'; operands = '0x' + raw[1].toString(16); }
    instrs.push({ addr, bytes: raw, mnemonic, operands });
    addr += len;
    p += len;
  }
  // the decode has to agree with VRIG's own spelled-out sequence
  const said = names.map(n => n.split(/[ ,]/)[0]);
  out.decodeMatchesVrig = said.length === instrs.length && said.every((m, i) => m === instrs[i].mnemonic);
  out.vrigSequence = names;
  out.shellcode = bytes;
  out.instructions = instrs;
  // stack sits below the buffer so the pushes don't land on the code
  const emu = new X86Emulator(instrs, undefined, 0xbfff0400, 'x86');
  out.run = walk(emu);
  // X86Emulator has no 8-bit registers, "mov al" throws. Do the low-byte
  // write by hand, mark it, and let VRIG's emulator finish the int 0x80.
  out.patched = [];
  if (out.run.error) {
    const bad = out.run.steps.at(-1);
    const imm = parseInt(bad.instr.operands.split(',')[1], 16);
    const eax = emu.state.registers.eax;
    emu.state.registers.eax = ((eax & ~0xff) | imm) >>> 0;
    emu.state.registers.eip = bad.instr.addr + bad.instr.bytes.length;
    bad.regs = { ...emu.state.registers };
    bad.patched = true;
    out.patched.push({ addr: bad.instr.addr, why: bad.error });
    const rest = walk(emu);
    out.run.steps.push(...rest.steps);
    out.run.error = rest.error;
  }
  const last = out.run.steps.at(-1).regs;
  const str = [...Array(12).keys()].map(i => emu.readMem(last.ebx + i, 1));
  const sh = String.fromCharCode(...str.slice(0, str.indexOf(0)));
  out.ebxString = sh;
  out.final = last;
  verdict(out, [
    ['no null bytes', Number(!bytes.includes(0)), 1],
    ['length <= 64', Number(bytes.length <= 64), 1],
    ['length 23 as VRIG says', bytes.length, 23],
    ['eax = execve', last.eax, 0x0b],
    ['ecx = NULL', last.ecx, 0],
    ['edx = NULL', last.edx, 0],
    ['[ebx] = "/bin//sh"', Number(sh === '/bin//sh'), 1],
    ['decode agrees with VRIG text', Number(out.decodeMatchesVrig), 1],
  ]);
  out.solved = out.solved && ex.check() === true;
  save(out);
}
