# The task prompt

Give the agent exactly this. Do not add hints. Do not answer questions
about x86 during the run -- that contaminates the transcript.

## Isolate the agent from your own configuration

"Exactly this" includes everything the harness operator's tooling injects
without being asked. A coding agent run from your normal environment inherits
your global instruction files, output style, project conventions, and MCP
servers, none of which appear anywhere in this repository and none of which
another submitter has.

This is not a small effect. The first attempted baseline here ran with a
global instruction file that said to commit periodically without being asked,
and an output style that said to state plainly when a step was skipped or a
result was unverified. Both showed up in the transcript as behaviour --
disciplined checkpoint commits, and frank notes that paging was a TODO -- and
neither is attributable to the model. That run was discarded.

Before running, give the agent a clean environment: no user-level or
project-level instruction files, no output style, no MCP servers, and the
repository as its only working directory. Record what the environment was in
the result either way; see the `agent_config` block in `results/TEMPLATE.json`.

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
