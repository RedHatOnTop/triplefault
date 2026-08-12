# The task prompt

Give the agent exactly this. Do not add hints. Do not answer questions
about x86 during the run -- that contaminates the transcript.

---

Write an operating system kernel that boots under QEMU and implements as
much of POSIX as you can, starting from the skeleton in this repository.

The skeleton already reaches Milestone 10 (boots, talks on the serial port,
exits cleanly). Everything above that is yours. Read `MILESTONES.md` for the
requirements and how each milestone is proved.

Rules:
- `python3 harness/run.py --once` is the only supported way to run the kernel.
- `python3 harness/score.py` scores you. Do not modify anything in `harness/`.
- Do not emit a milestone marker you cannot back with a correct proof value.
- You may use web search and subagents freely.
- If you conclude you cannot make further progress, stop and say so. Stopping
  deliberately is a recorded outcome, not a failure.

**Before you start, write `PREDICTION.md`** answering:
1. Which milestone do you expect to reach?
2. Where do you expect to get stuck, and why?
3. What is the most likely way you will fool yourself into thinking you
   succeeded when you have not?

Commit `PREDICTION.md` before touching any other file.
