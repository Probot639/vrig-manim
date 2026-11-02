# Curriculum

Every concept that gets a scene. Part A is 0xVRIG, one scene per exercise unless
noted. Part B is everything else: RE and VR work done outside VRIG, plus topics
asked for directly (packing). `src` says where the material comes from, so a
scene can be checked against something real.

Status: `-` not started, `wip`, `done`.

## Booth demo

VRIG's `/demo` mode, one video per challenge. Data comes from `traces/demo.json`.

| challenge | scene | status |
|---|---|---|
| buffer overflow, "Can you become admin?" (follows the slideshow's five beats) | `scenes/demo.py DemoOverflow` | done |
| address leak, "Same trick. A different address." | `scenes/demo.py DemoAddresses` | done |
| integer overflow, "A big number. A tiny buffer." | `scenes/demo.py DemoCounter` | done |

## Part A: 0xVRIG

| unit | concepts | 3D? |
|---|---|---|
| intro-c | variables and memory, pointers, arrays and strings, functions and the call stack, structs and layout, dynamic memory, common pitfalls, spot the bug | |
| 0 asm | registers, MOV, arithmetic, PUSH/POP, CMP and flags, jumps, CALL/RET, memory addressing, calling conventions, stack frames | |
| 1 stack | stack frame, overflow, hijack, ASLR, canary | ASLR slide |
| 2 logic | integer overflow, format string read, format string write, off-by-one, signedness | |
| 3 stack II | ret2libc, ROP basics (done, `RopBasics`), stack pivot, SROP | pilot, ROP path across .text |
| 4 heap | the heap, UAF, double free, heap overflow | bins as lists |
| 5 heap II | tcache poison, fastbin dup, unsorted bin, House of Force / Spirit / Orange / Einherjar / Lore | |
| 6 final | full chain, blind chain | |
| 7 x64 | stack frame, calling convention, ROP, ret2csu, canary leak, PIE bypass, one-gadget, full chain | |
| 8 win stack | stdcall overflow, Windows stack overflow, SEH on stack, SEH overwrite, /GS bypass, CFG | |
| 9 win heap | LFH UAF, LFH overflow, double free, WinAPI heap UAF | |
| 10 challenges | CTF easy / medium / hard / Windows (recap scenes, reuse earlier ones) | |
| 11 heap internals | ptmalloc2 overview, chunk lifecycle, bin types, tcache deep dive, arenas and threads, coalescing and unlink | arenas |
| 12 win heap internals | NT heap, LFH internals, segment heap, metadata encoding | |
| 13 ARM | registers, data processing, memory access, conditional execution, calling convention, stack frame, stack overflow, ROP | |
| 14 MIPS | registers, arithmetic, memory, branching (delay slots), calling convention, stack frame, overflow, ROP | |
| 15 mitigations | ASLR, DEP/NX, canaries, RELRO and GOT, PIE, CFI, CET shadow stacks, combined | address space volume |
| 16 advanced | vtable layout, vtable hijack, type confusion, UAF + vtable, COOP, ret2dlresolve, FILE structure, FSOP | |
| 17 advanced II | JIT spray, kernel pool overflow, Spectre v1, BROP, heap feng shui, sandboxing and escape, data-only attacks, DOP | Spectre cache |
| 18 kernel | kernel memory layout, kernel stack overflow, slab spray UAF, SMEP/SMAP bypass, modprobe_path | page tables |
| 19 glibc bypass | double free on 2.31, tcache poison on 2.32+ (safe-linking), heap consolidation | |
| 20 teaching gaps | info leak chaining, TOCTOU, shellcode crafting, partial overwrite and ASLR brute force, uninitialized memory | |

139 exercises. 106 have a video in `videos/<unit>/<id>.mp4`, and stack2-12
is `videos/RopBasics.mp4`.

Not made yet:
- unit1-stack: stack-02, stack-03, stack-04, stack-05
- unit2-logic: logic-06 to logic-10
- unit3-stack-ii: stack2-11, stack2-13, stack2-14
- imagine-rit: rit-02, rit-03, rit-04, rit-rop
- unit13-arm: arm-63 to arm-70 (`tools/vrig-trace/arch-entry.ts` exists, no scenes)
- unit14-mips: mips-71 to mips-78 (same)

The ARM quizzes also hit a VRIG emulator bug. Instruction fetch reads pc+8, so
programs run every third instruction and the quiz answers don't match.

Scene families: `scenes/asm_x86.py`, `asm_adv.py`, `walk_stack.py`,
`walk_heap.py`, `stack_adv.py`, `heap.py`, and `windows.py`. Each one has a
matching `tools/vrig-trace/<family>-entry.ts` and `tests/test_<family>.py`.

## Part B: beyond VRIG

### Binary exploitation, extended
| concept | src | 3D? |
|---|---|---|
| ARM64 ret2win, x29/x30 epilogue | `~/code/arm64-rop`, ARM64 ROP deck script | |
| ARM64 ROP to execve via svc | `arm64-rop/exploit_ropchain.py` | yes |
| PAC, signing oracles, autiasp | `arm64-rop/pac.c` | |
| Custom allocator UAF | `binex-vulnchat` | |
| House of Botcake / Tangerine | Heap_Exploitation_VRIG deck | |
| Signal handler reentrancy race (regreSSHion) | `cve-2024-6387` | timeline |

### OS and kernel internals
| concept | src | 3D? |
|---|---|---|
| Virtual memory, page tables, TLB, demand paging | xnu-memory-system deck | yes |
| Linux VMA vs XNU vm_map/vm_object/pmap, COW shadow chains | same | yes |
| XNU zones, kalloc_type, sequestering | Heap_Exploitation_VRIG deck | |
| SLUB, cross-cache, msg_msg spray | `~/kvmctf/training/curriculum.md` (planned only) | |

### Virtualization
| concept | src | 3D? |
|---|---|---|
| VT-x root/non-root, VMCS, VMEXIT round trip | `layer-zero-point-five` deck | yes |
| EPT, two-level translation | same, kvmctf module 0 | yes |
| VMEXIT timing detection (CPUID/RDTSC) | same, `topjail/csaw/os-no-good` | |
| MSR bitmaps, patched kvm-intel | `os-no-good` | |
| VM escape classes, virtio/device emulation | layer-zero-point-five deck | |
| CVE-2021-3653 nested AVIC intercept | kvmctf module 5 | |

### Fuzzing
| concept | src | 3D? |
|---|---|---|
| Dumb vs mutational vs grammar fuzzing | `fuzzing-example` | |
| Coverage feedback, corpus growth | `fuzzing-example`, `cyclonedds` | yes, coverage map |
| Snapshot fuzzing with an in-process harness (WinAFL/DynamoRIO) | `midi-fuzz` | |
| Sanitizers (ASan shadow memory) | `cyclonedds` report | |
| Differential fuzzing (HTTP smuggling, EVM consensus) | `bug-program`, `AIingFuzzyVM` | |
| Crash dedup by stack hash, distributed corpus | `mycelium` | |

### Malware, packing, anti-analysis
| concept | src | 3D? |
|---|---|---|
| ELF and PE layout, loader mapping | (requested) | yes |
| Packing: compress, stub, unpack to OEP | (requested) | yes, nested shells |
| Section entropy as a packing tell | `malware-rev` pipeline | |
| Anti-VM: SMBIOS, name blacklists, CPUID hypervisor bit | `anti-umbral`, `Marionette/doll/internal/anti` | |
| Anti-debug timing | `Marionette` | |
| Obfuscation: movfuscator, garble, control-flow flattening | `miller-ipc`, `Marionette` | CFG before/after |
| PLT/GOT lazy binding | (requested), unit 15 RELRO | |
| Linux persistence: PAM backdoor, cron, immutable bits | `Blueteamtime` | |
| eBPF tracepoints | `wabbit` | |

### Software protection
| concept | src | 3D? |
|---|---|---|
| Runtime patching through /proc/PID/mem | `ida-pro/VDJ_CRACK.md` | |
| .text integrity check bypass | same | |
| Hardware watchpoints (DR0-DR7) | `ida-pro/vdj_watchpoint.c` | |
| Signature check NOP patch | `ida-pro/reason_crack.sh` | |

### Crypto implementation bugs
| concept | src | 3D? |
|---|---|---|
| ECDH pubkey validation, invalid curve | `bug-program` PQC audit | curve |
| P-256 lost carry to key recovery | ecc_presentation_final deck | |
| PKCS7 chain-of-trust bypass | `miller-koth` CVE-2023-24011 PoC | |

### C2 and protocols
| concept | src | 3D? |
|---|---|---|
| X25519 + KDF + AES-GCM sealed frames | `Marionette` | |
| Beaconing, jitter, DNS chunking | `Marionette` | |
| Protocol MITM by forging acks from leaked keys | `miller-ipc` PoC | |
| BLE GATT / ATT framing recovered from an APK | `spotled` | |
| RTPS/SPDP discovery, CDR deserialization | `cyclonedds`, `robots-lately` writeup | |

### Containers and sandboxes
| concept | src | 3D? |
|---|---|---|
| Namespaces vs chroot | `topjail/NodeJail` | yes, nested boxes |
| Podman socket escape, rootful socket LPE | `miller-containers` | |
| File capabilities (cap_setuid) | `miller-koth/src/ros2_diag` | |
| V8 vm escape through a revoked Proxy | `nodeos-2` writeup | |
| Deserialization RCE (Ruby Marshal) | `miller-containers` | |

## Left out

SDR, audio and image stego, classical ciphers. These are on disk but they are
signals and puzzle work, not RE or VR. Easy to add later if wanted.
