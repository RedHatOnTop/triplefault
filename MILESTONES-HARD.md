# Hardmode milestones

**Not part of the v1 rotation. Scores here are not comparable with i386.**

The rotation (v1 i386 → v2 riscv64 → v3 aarch64) exists so scores can be
compared across versions. Hardmode exists for the opposite reason: to find
out what happens when almost nothing useful comes back from search.

Two targets, chosen for how little material exists about them:

| | ppc64 (BE) | s390x |
|---|---|---|
| firmware | PAPR / Virtual Open Firmware | s390 boot protocol |
| console | `H_PUT_TERM_CHAR` hypercall | SCLP write-event-data |
| endianness | **big** | **big** |
| MMU | HPT / radix, SLB | DAT, region/segment tables |
| I/O | hypercalls + PCI | channel subsystem (SSCH/TSCH) |
| port I/O | none | none |

Both skeletons boot and print. Verified, not aspirational.

## Milestones

| # | ppc64 | s390x |
|---|---|---|
| 10 | boots, console works | boots, console works | *(given)* |
| 15 | read nonce from FDT `/chosen/bootargs` (r3) | read nonce from `0x10480` |
| 25 | exception vectors installed; take and return from a trap | PSW swap; handle a program interrupt |
| 35 | decrementer interrupt, 100 ticks, no checkstop | CPU timer / clock comparator, 100 ticks |
| 45 | MMU on: HPT or radix page tables | DAT on: region + segment + page tables |
| 55 | problem state (userspace) + a real syscall | problem state + a real SVC |
| 65 | endianness audit: pass the mixed-width struct suite | same suite |
| 80 | one device through the real I/O path | one device through channel I/O |

Milestone 65 is the reason these targets are here. It replays data that was
laid out little-endian and checks every field. An x86 kernel ported by
search-and-replace passes everything up to 45 and dies at 65 without ever
having looked wrong.

## Realistic expectations

Most runs will end between 15 and 35. That is fine and it is the point --
but it also means the score distribution is compressed and boring, which is
exactly why hardmode is not the main track. Read the transcripts, not the
table.

The interesting tag here is `endianness-blindness`: the agent ports working
x86 logic, gets plausible output, and cannot explain why the numbers are
byte-swapped. Add it to your result when you see it.

## Setup

```bash
apt install gcc-powerpc64-linux-gnu gcc-s390x-linux-gnu \
            qemu-system-ppc qemu-system-s390x

make -f Makefile.hard ARCH=ppc64
python3 harness/run_hard.py --arch ppc64 --once

make -f Makefile.hard ARCH=s390x
python3 harness/run_hard.py --arch s390x --once
```

Two QEMU details the skeleton already handles, both of which cost real time
to discover, so they are documented rather than hidden:

- **ppc64**: `kernel-addr=0` is required. Without it QEMU relocates the image
  by `+0x400000` and every absolute address quietly points at nothing. The
  symptom is a checkstop with no other information.
- **ppc64**: ELFv2 needs `r2` pointing at the TOC before any C runs, or the
  first string constant load faults. This is set up in `arch/ppc64/boot.S`.
