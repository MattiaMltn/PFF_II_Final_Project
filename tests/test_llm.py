"""Tests for the Gemini pricing explainer."""

from unittest.mock import MagicMock, patch

import pytest

from backend.llm.explainer import (
    DEFAULT_GEMINI_MODEL,
    explain_pricing_result,
    explain_unified,
)


SAMPLE_PARAMS = {
    "ticker": "AAPL",
    "S": 298.87,
    "K": 300.0,
    "T": 0.25,
    "r": 0.0425,
    "sigma": 0.243,
    "bid": 11.90,
    "ask": 12.10,
    "option_type": "call",
    "american": False,
}

SAMPLE_GREEKS = {
    "delta": 0.48,
    "gamma": 0.012,
    "theta": -0.045,
    "vega": 0.38,
    "rho": 0.11,
}


def _mock_response(text: str = "This is the explanation.") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    return response


def test_explain_returns_string() -> None:
    """explain_pricing_result must return a non-empty string."""
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_calls_correct_model() -> None:
    """The explainer must use the configured Gemini model."""
    with (
        patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": DEFAULT_GEMINI_MODEL},
            clear=False,
        ),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        request_url = mock_post.call_args.args[0]
        assert DEFAULT_GEMINI_MODEL in request_url


def test_explain_prompt_contains_key_values() -> None:
    """Prompt must include the core pricing context."""
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        prompt = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0][
            "text"
        ]
        assert "AAPL" in prompt
        assert "12.34" in prompt
        assert "Delta" in prompt
        assert "11.90 / $12.10" in prompt
        assert "Market mid: $12.0000" in prompt


def test_explain_with_american_option() -> None:
    """The explainer must work for American options without errors."""
    params = {**SAMPLE_PARAMS, "american": True, "option_type": "put"}

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_pricing_result(params, 5.67, SAMPLE_GREEKS)

    assert isinstance(result, str)


def test_explain_unified_alias() -> None:
    """explain_unified keeps compatibility with the latest handoff."""
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_unified(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)


def test_explain_handles_missing_market_quote() -> None:
    """Zero bid/ask must be described as an unreliable market comparison."""
    params = {**SAMPLE_PARAMS, "bid": 0.0, "ask": 0.0}

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(params, 12.34, SAMPLE_GREEKS)

        prompt = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0][
            "text"
        ]

    assert "unavailable or non-positive" in prompt
    assert "no active two-sided quote" in prompt


def test_explain_requires_api_key() -> None:
    """A clear error is raised when the Gemini key is missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)
