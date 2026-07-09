"""快速验证持久化层。"""
import sys
sys.path.insert(0, "src")

from report.ui_state.database import init_db, ARTIFACTS_DIR
from report.ui_state.project_store import ensure_default_project, create_project, list_projects
from report.ui_state.run_store import save_run, get_latest_run
import json

init_db()

# 项目
pid = ensure_default_project()
assert pid > 0
pid2 = create_project("G科技", "G科技有限公司", "2025-12-31",
                       engagement_code="SH-2025-00128",
                       engagement_name="XX集团 2025年度审计")
assert pid2 > pid

projects = list_projects()
assert len(projects) >= 2
for p in projects:
    print(f"  project: {p['name']} | eng: {p['engagement_name']} | code: {p['engagement_code']}")

# 运行
fake = {
    "summary": {"overall_severity": "WARN", "fail_count": 2, "warn_count": 3, "need_review_count": 1},
    "issues": [
        {"severity": "FAIL", "rule_id": "test_rule", "source_sheet": "Sheet1", "source_row": 5, "field": "test", "message": "test"},
        {"severity": "PASS", "rule_id": "test_pass", "message": "ok"},
        {"severity": "WARN", "rule_id": "test_warn", "message": "warning"},
    ],
    "runtime_timings": {"total_seconds": 5.0, "llm_enabled": False},
    "subject_code": "FA_K1",
}
json_bytes = json.dumps(fake, ensure_ascii=False, indent=2).encode("utf-8")
html_bytes = b"<html><body>test</body></html>"
run_id = save_run(pid, "test_workbook.xlsx", fake, json_bytes, html_bytes)
assert run_id > 0
print(f"run_id: {run_id}")

# 读取最近
latest = get_latest_run()
assert latest is not None
assert latest["source_filename"] == "test_workbook.xlsx"
assert latest["overall_severity"] == "WARN"
assert latest["finding_count"] == 2  # FAIL + WARN, PASS excluded
assert latest["fail_count"] == 2
print(f"latest: {latest['source_filename']} | {latest['overall_severity']} | findings={latest['finding_count']}")

# 产物文件
ad = ARTIFACTS_DIR / str(run_id)
assert (ad / "report.json").exists()
assert (ad / "review.html").exists()
print(f"artifacts dir ok: {ad}")

# 读取完整 data
assert "data" in latest
assert latest["data"]["summary"]["overall_severity"] == "WARN"
print("data round-trip ok")

print("\n=== ALL CHECKS PASSED ===")
