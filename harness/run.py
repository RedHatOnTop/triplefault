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
import socket
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
    n = random.randrange(24, 49)
    return {
        "nonce": random.getrandbits(32) if nonce is None else nonce,
        "pit_div": random.randrange(lo, hi + 1),
        "pit_target": target,
        # M30: how many blocks to allocate, the seed their sizes come from, and
        # which of them to free before the second round. The sizes are derived
        # rather than listed so the command line stays short; see MILESTONES.md
        # for the derivation the kernel has to reproduce.
        "heap_n": n,
        "heap_seed": random.getrandbits(32),
        "heap_free_seed": random.getrandbits(32),
        # M40: how many separate write(2) calls to issue from ring 3, and the
        # seed the bytes come from. The count is what the interrupt log is
        # checked against, so it has to be large enough that a stray software
        # interrupt cannot be mistaken for the workload.
        "ring3_n": random.randrange(24, 65),
        "ring3_seed": random.getrandbits(32),
    }


def heap_sizes(w: dict) -> list[int]:
    """The allocation sizes the kernel is required to request, in order.

    Derived from heap_seed by a 32-bit xorshift so the kernel can reproduce it
    with a few lines of C. Sizes are 16-byte multiples in [16, 1024].
    """
    x = w["heap_seed"] & 0xFFFFFFFF
    out = []
    for _ in range(w["heap_n"]):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out.append(16 * (1 + (x % 64)))
    return out


def heap_free_indices(w: dict) -> list[int]:
    """Which round-one blocks to free, as indices into heap_sizes().

    Every fourth block by the same xorshift, which scatters the holes instead
    of freeing a contiguous run -- a bump allocator that only ever moves
    forward cannot satisfy the reuse check either way, but scattered holes also
    rule out simply rewinding the bump pointer.
    """
    x = w["heap_free_seed"] & 0xFFFFFFFF
    n = w["heap_n"]
    picked, out = set(), []
    while len(out) < max(3, n // 6):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        i = x % n
        if i not in picked:
            picked.add(i)
            out.append(i)
    return out


def ring3_bytes(w: dict) -> list[int]:
    """The bytes write(2) has to carry out of ring 3, in order.

    Same xorshift as the heap sizes. Restricted to printable ASCII so the echo
    is readable in a transcript rather than being a run of control characters.
    """
    x = w["ring3_seed"] & 0xFFFFFFFF
    out = []
    for _ in range(w["ring3_n"]):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out.append(33 + (x % 94))
    return out


def cmdline_for(w: dict) -> str:
    """Kernel command line. Keys are stable; parse them, do not count fields."""
    return (f"nonce=0x{w['nonce']:08X}"
            f" pit_div={w['pit_div']}"
            f" pit_target={w['pit_target']}"
            f" heap_n={w['heap_n']}"
            f" heap_seed=0x{w['heap_seed']:08X}"
            f" heap_free_seed=0x{w['heap_free_seed']:08X}"
            f" ring3_n={w['ring3_n']}"
            f" ring3_seed=0x{w['ring3_seed']:08X}")


CR0_RE = re.compile(r"CR0=([0-9a-fA-F]{8}).*?CR3=([0-9a-fA-F]{8})", re.S)
CR0_PG = 1 << 31

# Every interrupt QEMU takes is logged with the vector, whether it came from an
# INT instruction, and the privilege level it was taken FROM:
#   151: v=80 e=0000 i=1 cpl=3 IP=001b:00101234 ...
# A guest cannot produce that line without executing int $0x80 at CPL 3. This is
# a log of events rather than a sample of state, so unlike CR0 there is no window
# to miss -- which is why M40 uses it and M30 could not.
SYSCALL_INT = re.compile(r"^\s*\d+:\s*v=80\s+e=[0-9a-fA-F]+\s+i=1\s+cpl=3\b",
                         re.M)


class _Qmp:
    """Minimal QMP client, used only to sample control registers.

    Best-effort by construction: a kernel that exits in 100 ms may be gone
    before the socket is even connectable, and that is a legitimate outcome, not
    an error. Failure to sample means paging was not observed, which is exactly
    what should be reported for a kernel that never enabled it.
    """

    def __init__(self, path: str, deadline: float):
        self.f = None
        self.sock = None
        while time.monotonic() < deadline:
            try:
                s = socket.socket(socket.AF_UNIX)
                s.settimeout(0.5)
                s.connect(path)
            except OSError:
                time.sleep(0.01)
                continue
            try:
                f = s.makefile("rwb")
                f.readline()                        # greeting
                f.write(b'{"execute":"qmp_capabilities"}\n')
                f.flush()
                f.readline()
            except OSError:
                s.close()
                return
            self.sock, self.f = s, f
            return

    def sample(self) -> tuple[int, int] | None:
        """(CR0, CR3) as QEMU sees them right now, or None."""
        if not self.f:
            return None
        try:
            self.f.write(b'{"execute":"human-monitor-command",'
                         b'"arguments":{"command-line":"info registers"}}\n')
            self.f.flush()
            while True:
                line = self.f.readline()
                if not line:
                    return None
                d = json.loads(line)
                if "error" in d:
                    return None
                if "return" in d:
                    m = CR0_RE.search(d["return"] or "")
                    return (int(m.group(1), 16), int(m.group(2), 16)) if m else None
        except (OSError, ValueError):
            self.f = None
            return None

    def close(self):
        for h in (self.f, self.sock):
            try:
                if h:
                    h.close()
            except OSError:
                pass


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
            "paging_observed": False,
            "cr0_observed": None,
            "cr3_observed": None,
            "ring3_syscalls": 0,
            "workload": w,
            "wall_s": 0.0,
        }

    fd, debug_path = tempfile.mkstemp(prefix="tf-qemu-", suffix=".log")
    os.close(fd)
    qmp_path = debug_path + ".qmp"

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
        # Paging cannot be proved by anything the kernel says: whatever value it
        # derives, the harness could derive too, so it is forgeable arithmetic.
        # CR0 read out of the hypervisor is not -- a guest cannot lie to QEMU
        # about its own control registers.
        "-qmp", f"unix:{qmp_path},server,nowait",
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

        qmp = _Qmp(qmp_path, t0 + min(2.0, timeout))
        cr0_seen = cr3_seen = None
        paging_seen = False
        next_sample = 0.0
        claimed = False

        # Read raw chunks and cut lines here rather than calling readline() on a
        # buffered stream. The kernel writes the serial port a byte at a time, so
        # a line is nearly always incomplete when the fd reports ready; blocking
        # for the rest of it stalls the reader and backdates nothing -- it
        # postdates every line that was already waiting.
        while sel.get_map():
            el = time.monotonic() - t0
            if el >= timeout:
                timed_out = True
                break
            # A slow background poll, only so a long-lived guest is looked at at
            # all. It is not what catches paging: the window where CR0.PG is set
            # can be a few milliseconds inside a run that spends a second
            # waiting on timer ticks, and blind polling misses it nearly always.
            if el >= next_sample:
                next_sample = el + 0.01
                claimed = True
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
                        # Look at the CPU whenever the kernel makes a claim.
                        # That is the moment its story has to be true, and it is
                        # the only moment the harness can be sure of finding it.
                        if b"[[TF:" in raw:
                            claimed = True
                    else:
                        stderr_tail.append(text + "\n")

            if claimed:
                claimed = False
                s = qmp.sample()
                if s:
                    cr0_seen, cr3_seen = s
                    if cr0_seen & CR0_PG:
                        paging_seen = True

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
        ring3_syscalls = len(SYSCALL_INT.findall(debug))
        tail = debug.splitlines(keepends=True)[-DEBUG_TAIL_LINES:]
        qmp.close()
    finally:
        os.unlink(debug_path)
        if os.path.exists(qmp_path):
            os.unlink(qmp_path)

    return {
        "ok": rc == EXIT_OK_CODE,
        "serial": "".join(line for _, line in timeline),
        "timeline": timeline,
        "qemu_debug_tail": scrub("".join(tail)),
        "qemu_stderr": scrub("".join(stderr_tail)),
        "paging_observed": paging_seen,
        "cr0_observed": cr0_seen,
        "cr3_observed": cr3_seen,
        "ring3_syscalls": ring3_syscalls,
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
