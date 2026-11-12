"""
Regression test for backend/src/test_engine.py's CLI null-safety fix
(CTO Remediation Plan Revision 4, Task 0.1.2): `stop_loss`/`take_profit_1`/
`take_profit_2` can now legitimately be `None` on a `TradeRecommendation`
(SELL/STRONG_SELL/NEUTRAL - `DynamicRiskManager` only computes long-side
risk geometry, Finding 8's fix). `_format_optional_price` must never crash
on `None` and must never display it as a misleading `0.0000`.

Importing `test_engine` here is safe: `pytest.ini`'s `testpaths = src/tests`
means pytest never collects `backend/src/test_engine.py` itself as a test
module (it lives at `src/`, not `src/tests/`), and the module does no
network/environment work at import time - `GROQ_API_KEY` is only checked
inside `main()`, and `HybridTradingEngine` is only imported inside `main()`
too.
"""
import test_engine


def test_format_optional_price_handles_none_without_crashing():
    text = test_engine._format_optional_price(None, "red")

    assert "Mevcut değil" in text.plain


def test_format_optional_price_never_shows_a_misleading_zero_for_none():
    text = test_engine._format_optional_price(None, "red")

    assert text.plain != "0.0000"
    assert "0.0000" not in text.plain


def test_format_optional_price_formats_a_real_value_exactly_as_before():
    """Preserves the original `f"{v:,.4f}"` formatting and the given
    color for a real value - BUY presentation is unaffected."""
    text = test_engine._format_optional_price(175.5, "red")

    assert text.plain == "175.5000"
    assert text.style == "red"


def test_format_optional_price_uses_the_given_style_for_take_profit_too():
    text = test_engine._format_optional_price(190.0, "green")

    assert text.plain == "190.0000"
    assert text.style == "green"
