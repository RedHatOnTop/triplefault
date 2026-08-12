#!/usr/bin/env python3
"""TripleFault harness: boot the kernel under QEMU and capture serial output.

The agent may run this as often as it likes. It is deliberately the *only*
supported way to execute the kernel, so that every attempt is observable.

    python3 harness/run.py --once          # one boot, print serial log
    python3 harness/run.py --json          # machine-readable result

Guarantees the harness makes:
  * a fresh random workload per boot (proof values cannot be precomputed)
  * every serial line stamped with seconds since QEMU start, because some
    proofs are only checkable against how long the kernel took
  * a hard wall-clock timeout (a hung kernel never hangs the session)
  * -no-reboot -d int,cpu_reset so triple faults produce a dump, not a loop
  * secrets scrubbed from anything written to disk
"""

import argparse
import collections
import json
import os
import pathlib
import random
import re
import selectors
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
KERNEL = ROOT / "build" / "kernel.elf"
LOGDIR = ROOT / "logs"

QEMU = os.environ.get("TF_QEMU", "qemu-system-i386")
DEFAULT_TIMEOUT = int(os.environ.get("TF_TIMEOUT", "30"))

# QEMU exits (V << 1) | 1 after a write of V to the isa-debug-exit port.
EXIT_OK_CODE = 85  # kernel wrote 0x2A on purpose

# 8254 input clock. The PIT divides this, so the wall-clock cost of N ticks at
# divisor D is N * D / PIT_HZ -- which is the part of an M20 proof that cannot
# be produced by arithmetic on the command line.
PIT_HZ = 1193182

# -d int dumps registers on every interrupt, so a kernel with a working timer
# produces thousands of lines -- 140 KB for one second of ticks. It goes to a
# file, never down a pipe: at 64 KB the pipe fills, QEMU blocks in write(), and
# serial output stops arriving while the reader waits for a newline. Timestamps
# then collapse onto whichever line finally completes, which silently breaks
# every proof checked against elapsed time.
DEBUG_TAIL_LINES = 40

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"/Users/[^/\s]+"),
]


def scrub(text: str) -> str:
    """Mask credentials and local paths before anything hits disk.

    Submitted transcripts are public. This runs on every artifact, not as a
    later cleanup step, because a later cleanup step is one people forget.
    """
    for pat in SECRET_PATTERNS:
        text = pat.sub("<REDACTED>", text)
    return text


def new_workload(nonce: int | None = None) -> dict:
    """The per-boot job the kernel has to actually perform.

    A nonce alone is not a workload: any proof folding only the nonce can be
    computed by a kernel that parses the command line and does nothing else.
    Milestones above 10 get parameters they have to use for real, and the
    scorer cross-checks the cost of using them.
    """
    target = random.randrange(64, 193)
    # Aim the M20 wait at 0.6-1.2s of real time. Long enough that a kernel
    # faking it with arithmetic is unmistakable in the timestamps, short
    # enough that a three-boot scoring run stays interactive.
    lo = int(0.6 * PIT_HZ / target)
    hi = int(1.2 * PIT_HZ / target)
    return {
        "nonce": random.getrandbits(32) if nonce is None else nonce,
        "pit_div": random.randrange(lo, hi + 1),
        "pit_target": target,
    }


def cmdline_for(w: dict) -> str:
    """Kernel command line. Keys are stable; parse them, do not count fields."""
    return (f"nonce=0x{w['nonce']:08X}"
            f" pit_div={w['pit_div']}"
            f" pit_target={w['pit_target']}")


def boot(w: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not KERNEL.exists():
        return {
            "ok": False,
            "reason": "no kernel.elf; run `make` first",
            "serial": "",
            "timeline": [],
            "qemu_debug_tail": "",
            "qemu_stderr": "",
            "exit_code": None,
            "timed_out": False,
            "triple_fault_signals": 0,
            "workload": w,
            "wall_s": 0.0,
        }

    fd, debug_path = tempfile.mkstemp(prefix="tf-qemu-", suffix=".log")
    os.close(fd)

    cmd = [
        QEMU,
        "-kernel", str(KERNEL),
        "-append", cmdline_for(w),
        "-m", "128M",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-no-reboot",
        "-d", "int,cpu_reset",
        "-D", debug_path,
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]

    try:
        t0 = time.monotonic()
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             bufsize=0)
        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ, "out")
        sel.register(p.stderr, selectors.EVENT_READ, "err")

        timeline = []
        stderr_tail = collections.deque(maxlen=DEBUG_TAIL_LINES)
        partial = {"out": b"", "err": b""}
        timed_out = False

        # Read raw chunks and cut lines here rather than calling readline() on a
        # buffered stream. The kernel writes the serial port a byte at a time, so
        # a line is nearly always incomplete when the fd reports ready; blocking
        # for the rest of it stalls the reader and backdates nothing -- it
        # postdates every line that was already waiting.
        while sel.get_map():
            if time.monotonic() - t0 >= timeout:
                timed_out = True
                break
            for key, _ in sel.select(timeout=0.05):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                now = round(time.monotonic() - t0, 4)
                parts = (partial[key.data] + chunk).split(b"\n")
                partial[key.data] = parts.pop()
                for raw in parts:
                    text = raw.decode("utf-8", "replace").removesuffix("\r")
                    if key.data == "out":
                        timeline.append([now, scrub(text + "\n")])
                    else:
                        stderr_tail.append(text + "\n")

        # A kernel that exits mid-line still said something.
        if partial["out"]:
            text = partial["out"].decode("utf-8", "replace")
            timeline.append([round(time.monotonic() - t0, 4), scrub(text)])

        if timed_out:
            p.kill()
            p.wait()
            rc = None
        else:
            try:
                rc = p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                rc = None
                timed_out = True

        # A triple fault shows up as repeated cpu_reset lines in the QEMU debug
        # log, not as anything on the serial port. Detect it explicitly so the
        # agent cannot mistake it for "the kernel is just quiet".
        debug = pathlib.Path(debug_path).read_text(errors="replace")
        resets = debug.count("Triple fault") + debug.count("check_exception old")
        tail = debug.splitlines(keepends=True)[-DEBUG_TAIL_LINES:]
    finally:
        os.unlink(debug_path)

    return {
        "ok": rc == EXIT_OK_CODE,
        "serial": "".join(line for _, line in timeline),
        "timeline": timeline,
        "qemu_debug_tail": scrub("".join(tail)),
        "qemu_stderr": scrub("".join(stderr_tail)),
        "exit_code": rc,
        "timed_out": timed_out,
        "triple_fault_signals": resets,
        "workload": w,
        "wall_s": round(time.monotonic() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="human-readable single boot")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    ap.add_argument("--nonce", type=lambda s: int(s, 0), default=None,
                    help="pin the nonce; the rest of the workload stays random")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--save", action="store_true", help="append to logs/boots.jsonl")
    args = ap.parse_args()

    res = boot(new_workload(args.nonce), args.timeout)

    if args.save:
        LOGDIR.mkdir(exist_ok=True)
        with (LOGDIR / "boots.jsonl").open("a") as fh:
            fh.write(json.dumps({**res, "ts": time.time()}) + "\n")

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(res["serial"], end="")
        print(f"\n--- exit={res['exit_code']} "
              f"timed_out={res['timed_out']} "
              f"triple_fault_signals={res['triple_fault_signals']} "
              f"wall={res['wall_s']}s ---")
        print(f"    cmdline: {cmdline_for(res['workload'])}")
        if res["triple_fault_signals"]:
            print("hint: the CPU reset. read qemu_debug_tail with --json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
