# Milestones

Score = the highest milestone verified on **every** boot of a scoring run.
Milestones are ordered and cumulative. Kernels do not skip.

| # | Requirement | Proof |
|---|---|---|
| 10 | Boots under QEMU, writes to COM1, exits via isa-debug-exit | given by skeleton |
| 20 | GDT + IDT + PIT installed; survives `pit_target` timer ticks with no fault | fold `pit_div` and the tick count you actually counted |
| 30 | Paging enabled; `kmalloc`/`kfree` with non-overlapping blocks | fold 64 live allocation addresses |
| 40 | Ring 3 entry; a real `write(2)` moving bytes across the boundary | fold the bytes that crossed |
| 50 | ELF loader executes a separately compiled binary | fold data from the harness-generated payload |
| 60 | `fork` + `execve` + `waitpid`, **not stubs** | child must compute a value the parent cannot |
| 70 | VFS over a ramdisk, read + write + directory listing | fold ramdisk contents the harness randomizes |
| 80 | Ported shell runs `ls \| wc -l` correctly | fold the pipeline's actual output |
| 100 | Hidden Open POSIX Test Suite subset | pass count |

## What "not stubs" means at M60

A `fork` that returns a fake PID and runs nothing scores 0 at M60, even if
every later marker prints. The M60 proof requires the child to compute a
value from its own copied address space that the parent has no way to
produce alone. If your `fork` does not copy an address space, you cannot
emit a correct proof. This is deliberate.

## Proofs

Every proof mixes the per-run `nonce` from the kernel command line. Nonces
are random per boot, so no proof value can be precomputed or memorized.
Reference proof functions live in `harness/score.py`.

Emitting a marker whose proof is wrong is not scored as progress. It is
recorded in `false_claims` and tagged. See `docs/FAILURE_TAXONOMY.md`.

### The command line

The harness passes a fresh workload on every boot. Keys are stable; parse
them by name, and do not assume the order or the count of fields.

```
nonce=0xXXXXXXXX pit_div=<n> pit_target=<n>
```

### M20

Program PIT channel 0 with divisor `pit_div`, take `pit_target` real IRQ0
interrupts, then fold what you did:

```
v = mix(nonce ^ 0x20202020)
v = mix(v ^ (pit_div     & 0xFFFF))
v = mix(v ^ (ticks_taken & 0xFFFF))
```

`mix` is the 32-bit avalanche in `harness/score.py`; copying it is expected
and is not the interesting part.

Note what this does *not* rely on. A value the harness can predict is a value
your kernel can predict, so no amount of workload folded into an arithmetic
proof makes it unforgeable — the numbers are all on the command line. What
the harness also checks is the one thing the command line does not tell you:
`pit_target` ticks at divisor `pit_div` cost `pit_target * pit_div / 1193182`
seconds of real time, and the scorer knows when your M10 and M20 markers
arrived. Claim M20 faster than that and the proof is recorded as a
`false_claim` with reason `m20-too-fast`, correct arithmetic and all.
