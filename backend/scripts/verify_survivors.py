"""T_TEST.10 — re-run every surviving mutant against the whole suite.

Usage (inside backend container, from /app):
    python scripts/verify_survivors.py
    python scripts/verify_survivors.py x_visible_to__mutmut_5   # just these

**Why a survivor is not yet a finding.** mutmut times each mutant against only
the tests its stats pass believes touch the mutated line. That pass records
coverage per test, so anything executed *outside* a test is attributed to
nobody — and `require_perm` is exactly that: a dependency factory FastAPI calls
once, while importing the route modules, long before the first test starts. Its
mutants were handed an empty set of tests, and a mutant no test runs against
survives by definition.

That is not a misconfiguration to fix. Any function that runs at import time —
dependency factories, decorators, module-level code — is mis-attributed the same
way, and the effect is one-directional: it invents survivors, never hides them.
So the run is a lower bound on the kill-rate, and this script turns it into a
measurement.

Each mutant here gets the **full** suite with no selection at all, which is the
answer that settles it. `-x` makes the cost asymmetric in our favour: a mutant
the suite catches dies on the first disagreeing test, usually in seconds, while
only genuine survivors pay the full eight minutes. Verifying fourteen of them
costs far less than fourteen full runs.

Run from `/app` — `mutmut results` reads its store relative to the working
directory, while the suite has to run inside `mutants/`, against the mutated
copy.
"""
import os
import re
import subprocess
import sys
import time

MUTANTS_DIR = "mutants"


def survivors() -> list[str]:
    out = subprocess.run(
        ["mutmut", "results"], capture_output=True, text=True
    ).stdout
    found = []
    for line in out.splitlines():
        # `    app.core.permissions.x_visible_to__mutmut_5: survived`
        match = re.match(r"\s*(\S+):\s*survived\s*$", line)
        if match:
            found.append(match.group(1))
    return found


def verdict(mutant: str) -> tuple[bool, float]:
    """`(survived, seconds)` — survived meaning the suite did not notice."""
    env = dict(os.environ, MUTANT_UNDER_TEST=mutant)
    started = time.monotonic()
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "tests/"],
        cwd=MUTANTS_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    return run.returncode == 0, time.monotonic() - started


def main(only: list[str]) -> int:
    if not os.path.isdir(MUTANTS_DIR):
        print(f"no {MUTANTS_DIR}/ here — run from /app, after `mutmut run`")
        return 2

    names = survivors()
    if only:
        names = [n for n in names if any(fragment in n for fragment in only)]
    if not names:
        print("no survivors to verify")
        return 0

    print(f"{len(names)} to verify, full suite each\n")
    real, false_alarms = [], []

    for index, mutant in enumerate(names, 1):
        short = mutant.rsplit(".", 1)[-1]
        print(f"[{index}/{len(names)}] {short} ... ", end="", flush=True)
        survived, seconds = verdict(mutant)
        (real if survived else false_alarms).append(mutant)
        print(f"{'SURVIVED' if survived else 'killed'}  {seconds:.0f}s")

    print(f"\n{len(false_alarms)} false, {len(real)} real")
    if real:
        print("\nreal survivors — these are the gaps worth a test:")
        for mutant in real:
            print(f"  {mutant}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
