"""
Tests for the financial-statement fetch functions added to
data/fetcher.py (fetch_financials, fetch_balance_sheet,
fetch_cashflow_statement) — purely additive, existing functions in this
module are untouched.
"""
import pandas as pd
import pytest

from data.fetcher import fetch_balance_sheet, fetch_cashflow_statement, fetch_financials


class _FakeTicker:
    def __init__(self, financials=None, balance_sheet=None, cashflow=None, raises=False):
        self._financials = financials
        self._balance_sheet = balance_sheet
        self._cashflow = cashflow
        self._raises = raises

    @property
    def financials(self):
        if self._raises:
            raise RuntimeError("simulated yfinance failure")
        return self._financials

    @property
    def balance_sheet(self):
        if self._raises:
            raise RuntimeError("simulated yfinance failure")
        return self._balance_sheet

    @property
    def cashflow(self):
        if self._raises:
            raise RuntimeError("simulated yfinance failure")
        return self._cashflow


def _nonempty_df():
    return pd.DataFrame({"2025-01-01": [1.0]}, index=["Total Revenue"])


def test_fetch_financials_returns_dataframe_on_success(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(financials=_nonempty_df()))
    result = fetch_financials("AAPL")
    assert result is not None
    assert not result.empty


def test_fetch_financials_returns_none_when_empty(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(financials=pd.DataFrame()))
    assert fetch_financials("AAPL") is None


def test_fetch_financials_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(raises=True))
    assert fetch_financials("AAPL") is None


def test_fetch_balance_sheet_returns_dataframe_on_success(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(balance_sheet=_nonempty_df()))
    result = fetch_balance_sheet("AAPL")
    assert result is not None


def test_fetch_balance_sheet_returns_none_when_empty(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(balance_sheet=pd.DataFrame()))
    assert fetch_balance_sheet("AAPL") is None


def test_fetch_balance_sheet_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(raises=True))
    assert fetch_balance_sheet("AAPL") is None


def test_fetch_cashflow_statement_returns_dataframe_on_success(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(cashflow=_nonempty_df()))
    result = fetch_cashflow_statement("AAPL")
    assert result is not None


def test_fetch_cashflow_statement_returns_none_when_empty(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(cashflow=pd.DataFrame()))
    assert fetch_cashflow_statement("AAPL") is None


def test_fetch_cashflow_statement_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr("data.fetcher.yf.Ticker", lambda symbol: _FakeTicker(raises=True))
    assert fetch_cashflow_statement("AAPL") is None


def test_real_fetch_financials_for_a_real_company():
    result = fetch_financials("AAPL")
    assert result is not None
    assert "Total Revenue" in result.index
