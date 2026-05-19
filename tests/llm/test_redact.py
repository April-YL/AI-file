from llm.redact import redact_text


def test_redact_fa_test_id():
    assert redact_text("资产 FA-TEST-001 重复") == "资产 [ASSET_ID] 重复"
