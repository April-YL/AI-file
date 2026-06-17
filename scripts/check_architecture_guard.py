#!/usr/bin/env python
"""Architecture guard for the frozen QC system contract.

This script is intentionally lightweight and read-only. It prevents new
high-risk drift while reporting existing legacy exceptions as warnings.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FROZEN_CONTRACT = ROOT / "docs" / "frozen-top-level-architecture.md"
CODE_MAPPING = ROOT / "docs" / "frozen-architecture-code-mapping.md"
AGENTS = ROOT / "AGENTS.md"

ALLOWED_CHAT_COMPLETION_PATHS = {
    "scripts/test_llm_connection.py",
}

ALLOWED_SRC_PACKAGES = {"ingest", "llm", "report", "rules"}
ALLOWED_SRC_MODULES = {"fa_qc_ui.py"}


@dataclass(frozen=True)
class Finding:
    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_python(path: str) -> bool:
    return path.endswith(".py")


def _contains_llm_import(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(from\s+llm\b|import\s+llm\b)", text))


def _contains_rules_import(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(from\s+rules\b|import\s+rules\b)", text))


def _contains_llm_client_import(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(from\s+llm\.client\b|import\s+llm\.client\b)", text))


def _contains_report_summary_import(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*from\s+report\.summary\b", text))


def _is_allowed_chat_completion_path(path: str) -> bool:
    if path.startswith("src/llm/") and path.endswith(".py"):
        return True
    if path in ALLOWED_CHAT_COMPLETION_PATHS:
        return True
    if path.startswith("tests/llm/") and path.endswith(".py"):
        return True
    return False


def _check_contract_files() -> list[Finding]:
    failures: list[Finding] = []
    if not FROZEN_CONTRACT.exists():
        failures.append(Finding(str(FROZEN_CONTRACT.relative_to(ROOT)), "missing frozen top-level architecture contract"))
    if not CODE_MAPPING.exists():
        failures.append(Finding(str(CODE_MAPPING.relative_to(ROOT)), "missing frozen architecture code mapping"))
    if not AGENTS.exists():
        failures.append(Finding("AGENTS.md", "missing agent collaboration rules"))
    else:
        text = AGENTS.read_text(encoding="utf-8", errors="replace")
        if "Frozen Architecture Contract" not in text:
            failures.append(Finding("AGENTS.md", "missing Frozen Architecture Contract section"))
    return failures


def _check_unexpected_src_packages(paths: list[str]) -> list[Finding]:
    warnings: list[Finding] = []
    seen: set[str] = set()
    for path in paths:
        if not path.startswith("src/"):
            continue
        rest = path[len("src/") :]
        top = rest.split("/", 1)[0]
        if top in seen:
            continue
        seen.add(top)
        if top in ALLOWED_SRC_PACKAGES or top in ALLOWED_SRC_MODULES:
            continue
        warnings.append(
            Finding(path, f"unexpected tracked top-level src package/module '{top}' not present in frozen mapping")
        )
    return warnings


def _check_file(path: str) -> tuple[list[Finding], list[Finding]]:
    text = _read(path)
    failures: list[Finding] = []
    warnings: list[Finding] = []

    if path.startswith("src/rules/") and _is_python(path):
        if _contains_llm_import(text):
            failures.append(Finding(path, "Rule Engine must not import llm modules"))
        if "chat_completion_json" in text:
            failures.append(Finding(path, "Rule Engine must not call chat_completion_json"))

    if "chat_completion_json" in text and not _is_allowed_chat_completion_path(path):
        if path.startswith("tests/"):
            warnings.append(
                Finding(path, "non-LLM test references chat_completion_json; keep as test-only patch/mock usage")
            )
        else:
            failures.append(Finding(path, "chat_completion_json is outside allowed LLM client boundaries"))

    if path.startswith("src/report/") and _is_python(path):
        if _contains_llm_client_import(text):
            failures.append(Finding(path, "Report layer must not import llm.client directly"))
        if "chat_completion_json" in text:
            failures.append(Finding(path, "Report layer must not call chat_completion_json directly"))

    if path in {"src/report/pipeline.py", "src/report/export_json.py"} and _contains_llm_import(text):
        warnings.append(Finding(path, "legacy report-to-LLM import documented in code mapping; do not expand"))

    if path.startswith("src/ingest/") and _is_python(path) and _contains_rules_import(text):
        warnings.append(Finding(path, "legacy ingest-to-rules dependency documented in code mapping; do not expand"))

    if path == "src/llm/review.py" and _contains_report_summary_import(text):
        warnings.append(Finding(path, "legacy LLM-to-report summary coupling documented in code mapping"))

    if path.startswith("src/llm/") and _is_python(path):
        if re.search(r"(?m)^\s*from\s+rules\.models\s+import\b.*\bQcIssue\b", text) or "QcIssue(" in text:
            warnings.append(Finding(path, "LLM helper creates or imports QcIssue; current legacy impact coupling"))

    if path.startswith("tests/") and not path.startswith("tests/llm/"):
        if _contains_llm_import(text):
            warnings.append(Finding(path, "non-LLM test imports llm helper; ensure this remains test-only"))

    return failures, warnings


def main() -> int:
    tracked = _git_ls_files()
    files = [
        path
        for path in tracked
        if _is_python(path) and (path.startswith("src/") or path.startswith("scripts/") or path.startswith("tests/"))
    ]

    failures: list[Finding] = []
    warnings: list[Finding] = []

    failures.extend(_check_contract_files())
    warnings.extend(_check_unexpected_src_packages(tracked))

    for path in files:
        file_failures, file_warnings = _check_file(path)
        failures.extend(file_failures)
        warnings.extend(file_warnings)

    print("Architecture Guard")
    print("==================")
    print()

    if failures:
        print("FAIL:")
        for item in failures:
            print(f"  - {item.format()}")
    else:
        print("FAIL: none")

    print()
    if warnings:
        print("WARN:")
        for item in warnings:
            print(f"  - {item.format()}")
    else:
        print("WARN: none")

    print()
    if failures:
        print(f"Result: FAIL ({len(failures)} failure(s), {len(warnings)} warning(s))")
        return 1
    if warnings:
        print(f"Result: PASS WITH WARNINGS ({len(warnings)} warning(s))")
        return 0
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
