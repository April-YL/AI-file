from decimal import Decimal

from rules.parsing import amount_tolerance, parse_amount


def test_parse_amount_thousands_and_paren():
    assert parse_amount("1,234.56") == Decimal("1234.56")
    assert parse_amount("(100)") == Decimal("-100")
    assert parse_amount("¥1,000") == Decimal("1000")


def test_amount_tolerance_scales_with_base():
    assert amount_tolerance(Decimal("100")) == Decimal("0.01")
    assert amount_tolerance(Decimal("1000000")) > Decimal("0.01")
