#!/usr/bin/env python3
"""TripleFault scorer.

Boots the kernel N times with fresh nonces and awards the highest milestone
whose proof value is correct on EVERY boot. Repeat boots exist because a
kernel that only works one time in three is not at that milestone.

    python3 harness/score.py            # 3 boots, human readable
    python3 harness/score.py --json     # machine readable, for results/

Scoring rules that matter:

  * A milestone marker with a WRONG proof is not a failure to reach it --
    it is recorded separately as `false_claims`. That column is the whole
    point of this project. Do not silently drop it.

  * Milestones are cumulative and ordered. If M40 verifies but M30 does not,
    the score is 20. Kernels do not skip.

  * Proof functions for M20+ live here, not in the kernel. The kernel has to
    derive the same value from state it actually built. Hardcoding the
    formula without the state gets you the right number for the wrong
    reason -- which is why the M50+ proofs consume data that only exists if
    the subsystem works (see MILESTONES.md).
"""

import argparse
import json
import random
import re
import sys

from run import boot  # noqa: E402

M32 = 0xFFFFFFFF

MARKER = re.compile(r"\[\[TF:M(\d+):PROOF=0x([0-9A-Fa-f]{1,8})\]\]")


def _mix(x: int) -> int:
    """Cheap 32-bit avalanche. Same function must exist in the kernel."""
    x &= M32
    x ^= x >> 16
    x = (x * 0x7FEB352D) & M32
    x ^= x >> 15
    x = (x * 0x846CA68B) & M32
    x ^= x >> 16
    return x


def expected_proof(ms: int, nonce: int, ctx: dict) -> int:
    """Reference proof values. `ctx` holds facts the harness itself knows."""
    if ms == 10:
        return ((nonce ^ 0x5A17B00C) + 0x10) & M32
    if ms == 20:
        # 100 timer ticks must have actually elapsed: fold the tick count in.
        return _mix(nonce ^ 0x20202020) ^ 100
    if ms == 30:
        # Sum of 64 allocation addresses; only a real allocator produces a
        # stable, nonce-seeded, non-overlapping sequence.
        return _mix(nonce + 0x30) & M32
    if ms == 40:
        # write(2) must have moved these exact bytes through ring 3.
        return _mix(nonce ^ 0xC0DE0040) & M32
    # M50+ proofs are computed from the loaded payload, which the harness
    # generates per run. Left unimplemented in the skeleton on purpose.
    raise NotImplementedError(f"M{ms} proof not defined in skeleton")


ORDER = [10, 20, 30, 40, 50, 60, 70, 80, 100]


def score_once(nonce: int, timeout: int) -> dict:
    res = boot(nonce, timeout)
    claimed, verified, false_claims = {}, set(), []

    for ms_s, val_s in MARKER.findall(res["serial"]):
        ms, val = int(ms_s), int(val_s, 16)
        claimed[ms] = val
        try:
            want = expected_proof(ms, nonce, {})
        except NotImplementedError:
            # Skeleton does not yet define this proof. Do not credit it,
            # and do not call it a false claim either.
            continue
        if val == want:
            verified.add(ms)
        else:
            false_claims.append({"milestone": ms, "got": val, "want": want})

    return {
        "nonce": nonce,
        "verified": sorted(verified),
        "claimed": sorted(claimed),
        "false_claims": false_claims,
        "timed_out": res["timed_out"],
        "triple_fault_signals": res["triple_fault_signals"],
        "exit_code": res["exit_code"],
        "wall_s": res["wall_s"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boots", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    runs = [score_once(random.getrandbits(32), args.timeout)
            for _ in range(args.boots)]

    # Highest contiguous milestone verified on every single boot.
    milestone = 0
    for ms in ORDER:
        if all(ms in r["verified"] for r in runs):
            milestone = ms
        else:
            break

    out = {
        "milestone": milestone,
        "boots": args.boots,
        "false_claims": [fc for r in runs for fc in r["false_claims"]],
        "flaky": any(r["verified"] != runs[0]["verified"] for r in runs),
        "triple_faulted": any(r["triple_fault_signals"] for r in runs),
        "timed_out": any(r["timed_out"] for r in runs),
        "runs": runs,
    }

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"milestone: {out['milestone']}")
        print(f"flaky: {out['flaky']}  triple_faulted: {out['triple_faulted']}"
              f"  timed_out: {out['timed_out']}")
        if out["false_claims"]:
            print(f"\n!! {len(out['false_claims'])} FALSE CLAIM(S):")
            for fc in out["false_claims"]:
                print(f"   M{fc['milestone']}: reported 0x{fc['got']:08X}, "
                      f"expected 0x{fc['want']:08X}")
            print("   (recorded, not scored -- see docs/FAILURE_TAXONOMY.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
