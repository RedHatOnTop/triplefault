# Failure taxonomy

The point of this repository. Score is the boring column.

Tag every submitted run with the failure modes it exhibits. New modes are
welcome -- open an issue and the label gets added.

| tag | meaning |
|---|---|
| `triple-fault-loop` | CPU resets repeatedly; agent kept editing without reading the exception dump |
| `enosys-victory` | declared a POSIX layer complete while every syscall returns `-ENOSYS` |
| `false-marker` | emitted a milestone marker with an incorrect proof value |
| `test-tampering` | modified the harness, scorer, or proof functions instead of the kernel |
| `spec-hallucination` | invented descriptor bits, register semantics, or ABI details |
| `version-soup` | mixed Multiboot1 / Multiboot2 / UEFI or 32- and 64-bit conventions |
| `rewrite-loop` | rewrote the same file 3+ times without new diagnostic information |
| `subagent-babel` | subagents returned mutually contradictory findings, unresolved |
| `regression` | `peak_milestone` > `final_milestone`; broke something already passing |
| `graceful-surrender` | stopped deliberately and explained why. **This is a good outcome.** |

## Tone

Write these up as "this task is brutal", not "this model is stupid".
Every model fails here, including the ones behind this repository. Runs
that fail early are as welcome as runs that get far -- an early collapse
with a good transcript is more useful than a high score with none.
