"""案例库底稿路径与批量回归跳过策略（本地目录，不入 Git）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 案例库 A 公司底稿约 42MB，首轮与回归均跳过；后续测试沿用此阈值。
DEFAULT_MAX_WORKBOOK_MB = 20.0

# 文件名片段（脱敏公司名），显式排除大文件以外的特殊个案时可扩展。
SKIP_WORKBOOK_NAME_FRAGMENTS: tuple[str, ...] = (
    "A有限公司",
    "A公司",
)


@dataclass(frozen=True)
class CaseWorkbookRef:
    path: Path
    size_mb: float
    skipped: bool
    skip_reason: str | None = None


def find_case_library_dir(root: Path | None = None) -> Path | None:
    """在项目根下查找 ``固定资产质检agent/案例库``。"""
    root = root or Path.cwd()
    for p in root.iterdir():
        if not p.is_dir() or not p.name.endswith("agent"):
            continue
        for c in p.iterdir():
            if c.is_dir() and "案例" in c.name:
                return c
    return None


def should_skip_case_workbook(path: Path, *, max_mb: float = DEFAULT_MAX_WORKBOOK_MB) -> str | None:
    """返回跳过原因；可跑则返回 ``None``。"""
    name = path.name
    if name.startswith("~$"):
        return "excel_lock_file"
    for frag in SKIP_WORKBOOK_NAME_FRAGMENTS:
        if frag in name:
            return f"name_contains:{frag}"
    limit = int(max_mb * 1024 * 1024)
    if path.stat().st_size > limit:
        return f"size>{max_mb}MB"
    return None


def iter_case_workbooks(
    root: Path | None = None,
    *,
    max_mb: float = DEFAULT_MAX_WORKBOOK_MB,
) -> list[CaseWorkbookRef]:
    """列举案例库 ``*.xlsx``，大文件与 A 公司个案标记为 skipped。"""
    case_dir = find_case_library_dir(root)
    if case_dir is None:
        return []
    refs: list[CaseWorkbookRef] = []
    for path in sorted(case_dir.glob("*.xlsx")):
        size_mb = path.stat().st_size / (1024 * 1024)
        reason = should_skip_case_workbook(path, max_mb=max_mb)
        refs.append(
            CaseWorkbookRef(
                path=path,
                size_mb=round(size_mb, 2),
                skipped=reason is not None,
                skip_reason=reason,
            )
        )
    return refs


def case_label(path: Path) -> str:
    """从文件名提取案例字母标签（B/C/…），用于回归表。"""
    stem = path.stem
    for token in ("B医疗", "C新材料", "D锂电", "E锂原", "F有限", "G科技", "A有限"):
        if token[0] in stem:
            return token[0]
    return stem[:12]
