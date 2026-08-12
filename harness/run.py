#!/usr/bin/env python3
"""TripleFault harness: boot the kernel under QEMU and capture serial output.

The agent may run this as often as it likes. It is deliberately the *only*
supported way to execute the kernel, so that every attempt is observable.

    python3 harness/run.py --once          # one boot, print serial log
    python3 harness/run.py --json          # machine-readable result

Guarantees the harness makes:
  * a fresh random nonce per boot (proof values cannot be precomputed)
  * a hard wall-clock timeout (a hung kernel never hangs the session)
  * -no-reboot -d int,cpu_reset so triple faults produce a dump, not a loop
  * secrets scrubbed from anything written to disk
"""

import argparse
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
KERNEL = ROOT / "build" / "kernel.elf"
LOGDIR = ROOT / "logs"

QEMU = os.environ.get("TF_QEMU", "qemu-system-i386")
DEFAULT_TIMEOUT = int(os.environ.get("TF_TIMEOUT", "30"))

# QEMU exits (V << 1) | 1 after a write of V to the isa-debug-exit port.
EXIT_OK_CODE = 85  # kernel wrote 0x2A on purpose

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


def boot(nonce: int, timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not KERNEL.exists():
        return {
            "ok": False,
            "reason": "no kernel.elf; run `make` first",
            "serial": "",
            "exit_code": None,
            "nonce": nonce,
            "wall_s": 0.0,
        }

    cmd = [
        QEMU,
        "-kernel", str(KERNEL),
        "-append", f"nonce=0x{nonce:08X}",
        "-m", "128M",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-no-reboot",
        "-no-shutdown",
        "-d", "int,cpu_reset",
        "-D", "/dev/stderr",
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]

    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            text=True,
            errors="replace",
        )
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = None
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    wall = time.time() - t0

    # A triple fault shows up as repeated cpu_reset lines in the QEMU debug log,
    # not as anything on the serial port. Detect it explicitly so the agent
    # cannot mistake it for "the kernel is just quiet".
    resets = err.count("Triple fault") + err.count("check_exception old")
    return {
        "ok": rc == EXIT_OK_CODE,
        "serial": scrub(out),
        "qemu_debug_tail": scrub("\n".join(err.splitlines()[-40:])),
        "exit_code": rc,
        "timed_out": timed_out,
        "triple_fault_signals": resets,
        "nonce": nonce,
        "wall_s": round(wall, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="human-readable single boot")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    ap.add_argument("--nonce", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--save", action="store_true", help="append to logs/boots.jsonl")
    args = ap.parse_args()

    nonce = args.nonce if args.nonce is not None else random.getrandbits(32)
    res = boot(nonce, args.timeout)

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
        if res["triple_fault_signals"]:
            print("hint: the CPU reset. read qemu_debug_tail with --json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
