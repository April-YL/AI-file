from rules.lead_dates import parse_lead_date


def test_parse_iso_date():
    assert parse_lead_date("2025-12-31").isoformat() == "2025-12-31"


def test_parse_slash_date():
    assert parse_lead_date("2025/12/31").isoformat() == "2025-12-31"


def test_parse_invalid_returns_none():
    assert parse_lead_date("TBD") is None
    assert parse_lead_date(None) is None
