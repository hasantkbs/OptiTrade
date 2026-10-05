from unittest.mock import MagicMock, patch

import httpx

from providers.coingecko_provider import get_btc_dominance


def test_get_btc_dominance_returns_value_on_success():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"data": {"market_cap_percentage": {"btc": 54.32, "eth": 17.1}}}
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response) as mock_get:
        result = get_btc_dominance()
    assert result == 54.32
    mock_get.assert_called_once()


def test_get_btc_dominance_returns_none_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=MagicMock(),
    )
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response):
        result = get_btc_dominance()
    assert result is None


def test_get_btc_dominance_returns_none_on_timeout():
    with patch("providers.coingecko_provider.httpx.get", side_effect=httpx.TimeoutException("timed out")):
        result = get_btc_dominance()
    assert result is None


def test_get_btc_dominance_returns_none_on_malformed_json():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"data": {}}  # missing market_cap_percentage entirely
    with patch("providers.coingecko_provider.httpx.get", return_value=mock_response):
        result = get_btc_dominance()
    assert result is None
