#!/usr/bin/env python
"""Repository guard entrypoint.

This script is the single source of validation result for local repository
guards. Child checks own their detailed output; this wrapper only runs them,
preserves their output, and aggregates exit codes.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    returncode: int

    @property
    def passed(self) -> bool:
        return self.returncode == 0


CHECKS: tuple[Check, ...] = (
    Check("Architecture Guard", (sys.executable, "scripts/check_architecture_guard.py")),
    Check("Staged Secret Guard", (sys.executable, "scripts/check_staged_no_secrets.py")),
)


def _run_check(index: int, total: int, check: Check) -> CheckResult:
    print(f"[{index}/{total}] {check.name}")
    print("-" * (len(check.name) + len(f"[{index}/{total}] ")))
    sys.stdout.flush()
    result = subprocess.run(check.command, cwd=ROOT)
    print()
    return CheckResult(check.name, result.returncode)


def main() -> int:
    print("Repository Guard")
    print("================")
    print()
    print("check_repo_guard.py is the single source of validation result.")
    print()
    sys.stdout.flush()

    results = [_run_check(i, len(CHECKS), check) for i, check in enumerate(CHECKS, start=1)]

    print("Summary")
    print("-------")
    for result in results:
        status = "PASS" if result.passed else f"FAIL ({result.returncode})"
        print(f"- {result.name}: {status}")

    print()
    failed = [result for result in results if not result.passed]
    if failed:
        print(f"Result: FAIL ({len(failed)} failed check(s))")
        return 1

    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
