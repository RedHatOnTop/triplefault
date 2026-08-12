# TripleFault

**Ask a coding agent to write an operating system. Watch what happens.**

This is not a leaderboard with a failure log attached. It is a failure log
with a leaderboard attached. The interesting artifact is the transcript of
an agent discovering, over several hundred turns, that it does not know how
to debug a CPU that reboots without saying why.

Every model fails here. That is the design. The question the repository
tries to answer is *how* they fail, and whether their failures are the ones
they predicted.

---

## Why this task

Existing LLM×kernel benchmarks all hand the model an existing kernel:
locate a bug in Linux, generate a verification spec, drive a shell inside a
container. None of them ask for a kernel that boots from nothing. The gap
matters because from-scratch systems work has properties the others don't:

- **No partial credit from pattern matching.** A plausible-looking GDT is a
  triple fault. The CPU is not a grader that gives points for effort.
- **Search actively misleads.** OSDev material silently mixes Multiboot1,
  Multiboot2, UEFI, 32-bit and 64-bit conventions. Half of what comes back
  is correct for a target you are not building.
- **Failure is nearly opaque.** The machine resets. That's the whole error
  message. This is where agents reliably substitute rewriting for debugging.

## Two tracks

| | Sprint | Marathon |
|---|---|---|
| budget | capped (declare it) | uncapped |
| ends on | budget | stagnation, 72h wall-clock, or `giveup` |
| measures | efficiency per token | capability ceiling + long-horizon stability |
| key metric | milestone / cost | `peak_milestone` − `final_milestone` |

Marathon runs must use the harness-provided handoff format when context runs
out (`PROGRESS.md`). Otherwise the benchmark quietly becomes a test of who
built better scaffolding.

## Quickstart

```bash
docker build -t triplefault:v1 .
docker run --rm triplefault:v1          # scores the skeleton: milestone 10
```

Local, if you'd rather:

```bash
make                          # builds build/kernel.elf
python3 harness/run.py --once # one boot, serial output
python3 harness/score.py      # 3 boots, fresh nonce each, scored
```

Expected cost of one Sprint run: roughly $3–10 and 40–90 minutes depending
on model. Marathon runs have reached three figures. Budget accordingly.

## Scoring

Milestones are ordered and cumulative — see `MILESTONES.md`. Each one is
credited only when the kernel emits its marker **with a correct proof
value**, on every boot of the scoring run. Proofs are seeded with a random
per-boot workload, so they cannot be precomputed.

Correct arithmetic is not enough. Any value the harness can predict, a kernel
can also predict, so proofs are additionally checked against something the
harness *observes* — at M20, how long the kernel took, since the requested
number of timer ticks costs real seconds that no amount of command-line
parsing can skip.

A marker with a wrong proof, or a right proof produced impossibly fast, is not
scored as progress. It is recorded as a `false_claim`, which is one of the more
interesting columns in the dataset.

## Submitting

Open a PR adding one file to `results/` (copy `results/TEMPLATE.json`) plus
your transcript. Requirements:

1. **Fill in the `prediction` block.** The agent must write `PREDICTION.md`
   *before* starting — expected milestone, expected blocker, and expected
   self-deception. This cannot be reconstructed afterward, and the gap
   between prediction and outcome is the most valuable thing here.
2. **Include the transcript.** Self-reported results without one are not
   merged. `harness/run.py` scrubs credentials and home paths from anything
   it writes; run your own transcript through `scrub()` too.
3. **Tag the failure modes** from `docs/FAILURE_TAXONOMY.md`.
4. **Fill in `moment_of_despair` by hand.** Automated extraction never finds
   the good ones.
5. **Fill in the `environment` block.** The Docker image writes QEMU and gcc
   versions to `/etc/tf-versions` for this; if you ran on the host, record them
   yourself. M20 and above are checked partly against elapsed time, so a result
   without the environment it ran in cannot be compared with one that has it.

### Reading a single result

Record `model_released` and `model_class`, and read other people's rows with
both in view. A milestone number attached to a small model from a year ago says
almost nothing about what a current frontier model does, and the first baseline
collected here was exactly that: a lightweight model ten months old, one run,
which reached milestone 30. It is a datapoint about the harness, not a ceiling
for anything. Sorting the table by milestone and reading the top row is the
misuse this project is most likely to suffer.

**Bad results are the point.** A run that dies at milestone 20 with a
readable transcript is worth more to this repository than a run that reaches
60 without one. Please do not withhold embarrassing runs — and please write
them up as "this task is brutal", not "this model is stupid".

## Contamination

Public benchmarks become training data. Mitigations:

- proof values are nonce-seeded per boot; memorization doesn't transfer
- the Milestone 100 test subset is not published
- architecture rotates by major version: **v1 i386**, v2 riscv64, v3 aarch64.
  The boot path differs enough that memorized v1 code is a liability.

Always record `harness_commit` in your result. Scores are only comparable
within a version.

## License

Code: MIT. Submitted results and transcripts: CC-BY-4.0 — including for
model training. If that is not acceptable to you, please do not submit.
