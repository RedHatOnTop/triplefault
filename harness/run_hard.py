#!/usr/bin/env python3
"""TripleFault hardmode runner (ppc64 big-endian, s390x).

Neither target has anything like isa-debug-exit, so the kernel signals a
clean stop by printing a sentinel and halting. The harness watches the
serial stream and kills QEMU as soon as it sees the sentinel, so a finished
kernel does not sit out the full timeout.

    python3 harness/run_hard.py --arch ppc64  --once
    python3 harness/run_hard.py --arch s390x  --json

Both configurations below are verified to boot and print. If you change the
QEMU arguments, you are changing the benchmark -- record it in your result.
"""

import argparse
import json
import pathlib
import random
import selectors
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from run import scrub  # noqa: E402

SENTINEL = "[[TF:HALT]]"

ARCHS = {
    # pseries with the lightweight Virtual Open Firmware. kernel-addr=0 is
    # load-bearing: QEMU otherwise relocates the image by +0x400000 and every
    # absolute address in the kernel silently points at nothing.
    "ppc64": {
        "qemu": "qemu-system-ppc64",
        "args": [
            "-M", "pseries,x-vof=on,kernel-addr=0",
            "-m", "512",
            "-display", "none", "-serial", "stdio",
            "-monitor", "none", "-nodefaults", "-no-reboot",
        ],
        "build": "build-ppc64/kernel.elf",
        "endian": "big",
        "note": "console is the H_PUT_TERM_CHAR hypercall on vty 0x71000000",
    },
    "s390x": {
        "qemu": "qemu-system-s390x",
        "args": [
            "-M", "s390-ccw-virtio",
            "-m", "512",
            "-display", "none", "-serial", "stdio",
            "-monitor", "none", "-nodefaults", "-no-reboot",
        ],
        "build": "build-s390x/kernel.elf",
        "endian": "big",
        "note": "console is SCLP write-event-data; cmdline lands at 0x10480",
    },
}


def boot(arch: str, nonce: int, timeout: int = 60) -> dict:
    cfg = ARCHS[arch]
    kernel = ROOT / cfg["build"]
    if not kernel.exists():
        return {"ok": False, "reason": f"build first: make -f Makefile.hard ARCH={arch}"}

    cmd = [cfg["qemu"], *cfg["args"],
           "-kernel", str(kernel),
           "-append", f"nonce=0x{nonce:08X}"]

    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, errors="replace", bufsize=1)
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ, "out")
    sel.register(p.stderr, selectors.EVENT_READ, "err")

    out, err, halted = [], [], False
    while time.time() - t0 < timeout and not halted:
        for key, _ in sel.select(timeout=0.2):
            line = key.fileobj.readline()
            if not line:
                continue
            (out if key.data == "out" else err).append(line)
            if key.data == "out" and SENTINEL in line:
                halted = True
        if p.poll() is not None and not sel.select(timeout=0):
            break

    timed_out = not halted and (time.time() - t0) >= timeout
    p.kill()
    p.wait()

    return {
        "ok": halted,
        "arch": arch,
        "serial": scrub("".join(out)),
        "qemu_stderr_tail": scrub("".join(err[-40:])),
        "halted": halted,
        "timed_out": timed_out,
        "nonce": nonce,
        "wall_s": round(time.time() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", choices=sorted(ARCHS), required=True)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--nonce", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    nonce = args.nonce if args.nonce is not None else random.getrandbits(32)
    res = boot(args.arch, nonce, args.timeout)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(res.get("serial", ""), end="")
        print(f"\n--- halted={res.get('halted')} timed_out={res.get('timed_out')} "
              f"wall={res.get('wall_s')}s ---")
        print(f"    {ARCHS[args.arch]['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
