from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path


UI_APP_PATH = Path(__file__).resolve().parents[2] / "src" / "report" / "ui_app.py"


def _load_naming_helpers() -> dict:
    source = UI_APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted_names = {
        "_OUTPUT_SUFFIXES",
        "_INVALID_FILENAME_CHARS",
        "_MAX_OUTPUT_STEM_LENGTH",
        "_new_run_id",
        "_clean_output_stem",
        "_output_filename",
    }
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            selected.append(node)
        elif isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted_names:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_names:
            selected.append(node)
    namespace: dict = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(UI_APP_PATH), "exec"), namespace)
    return namespace


HELPERS = _load_naming_helpers()


def test_output_files_share_one_run_id() -> None:
    run_id = HELPERS["_new_run_id"](datetime(2026, 6, 15, 14, 30, 25))

    assert run_id == "20260615_143025"
    assert (
        HELPERS["_output_filename"]("K01后推表测试.xlsx", run_id, "report")
        == "K01后推表测试_20260615_143025_qc_report.json"
    )
    assert (
        HELPERS["_output_filename"]("K01后推表测试.xlsx", run_id, "review")
        == "K01后推表测试_20260615_143025_qc_review.html"
    )
    assert (
        HELPERS["_output_filename"]("K01后推表测试.xlsx", run_id, "annotated")
        == "K01后推表测试_20260615_143025_qc_annotated.xlsx"
    )


def test_output_filename_cleans_special_characters_and_existing_suffix() -> None:
    output = HELPERS["_output_filename"](
        ' K01:测试?底稿_qc_report.json',
        "20260615_143025",
        "report",
    )

    assert output == "K01_测试_底稿_20260615_143025_qc_report.json"


def test_output_filename_limits_long_source_name() -> None:
    output = HELPERS["_output_filename"](
        f"{'A' * 150}.xlsx",
        "20260615_143025",
        "annotated",
    )

    assert output.startswith("A" * 100)
    assert output.endswith("_20260615_143025_qc_annotated.xlsx")
