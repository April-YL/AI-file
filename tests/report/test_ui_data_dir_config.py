from pathlib import Path

from report.ui_state.database import _resolve_data_dir


def test_data_dir_uses_environment_override(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "qc-history"
    monkeypatch.setenv("FA_QC_DATA_DIR", str(configured))

    assert _resolve_data_dir() == configured.resolve()


def test_data_dir_defaults_to_project_local_data(monkeypatch) -> None:
    monkeypatch.delenv("FA_QC_DATA_DIR", raising=False)

    expected_root = Path(__file__).resolve().parents[2]
    assert _resolve_data_dir() == expected_root / "local_data" / "fixed_asset_qc"
