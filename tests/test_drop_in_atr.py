"""TDD: scanner.drop_in_atr — drop magnitude (in $) normalized by ATR(14) in $.
drop_kind-agnostic: caller supplies the $ drop matching that kind's definition
(intraday: open-intraday_low ; gradual: ref_close_window-close). Descriptive only."""
import scanner


def test_drop_in_atr_basic():
    # a $6 drop with a $2 ATR spans 3 ATRs
    assert scanner.drop_in_atr(6.0, 2.0) == 3.0


def test_drop_in_atr_none_atr_returns_none():
    assert scanner.drop_in_atr(6.0, None) is None


def test_drop_in_atr_zero_atr_returns_none():
    assert scanner.drop_in_atr(6.0, 0.0) is None


def test_drop_in_atr_none_drop_returns_none():
    assert scanner.drop_in_atr(None, 2.0) is None
