"""Tests for the Groq pricing explainer."""

from unittest.mock import MagicMock, patch

import pytest

from backend.llm.explainer import (
    DEFAULT_GROQ_MODEL,
    explain_pricing_result,
    explain_volatility_surface,
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

SAMPLE_SURFACE = {
    "ticker": "AAPL",
    "option_type": "call",
    "snapshot_date": "2026-06-10",
    "source": "historical_db",
    "points": 240,
    "maturities": 8,
    "moneyness_min": 0.7,
    "moneyness_max": 1.3,
    "dte_min": 14,
    "dte_max": 365,
    "iv_min": 0.22,
    "iv_max": 0.55,
    "iv_median": 0.31,
    "atm_iv": 0.28,
    "left_wing_iv": 0.42,
    "right_wing_iv": 0.35,
    "short_iv": 0.38,
    "long_iv": 0.27,
    "smoothing_sigma": 0.6,
    "first_snapshot": None,
}


def _mock_response(text: str = "This is the explanation.") -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": text}}]
    }
    return response


def test_explain_returns_string() -> None:
    """explain_pricing_result must return a non-empty string."""
    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_calls_correct_model() -> None:
    """The explainer must use the configured Groq model."""
    with (
        patch.dict(
            "os.environ",
            {"GROQ_API_KEY": "gsk_test-key", "GROQ_MODEL": DEFAULT_GROQ_MODEL},
            clear=False,
        ),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        request_body = mock_post.call_args.kwargs["json"]
        assert request_body["model"] == DEFAULT_GROQ_MODEL


def test_explain_prompt_contains_key_values() -> None:
    """Prompt must include the core pricing context."""
    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        assert "AAPL" in prompt
        assert "12.34" in prompt
        assert "Delta" in prompt
        assert "USD 11.90 / USD 12.10" in prompt
        assert "Market mid: USD 12.0000" in prompt
        assert "never use the dollar symbol" in prompt


def test_explain_with_american_option() -> None:
    """The explainer must work for American options without errors."""
    params = {**SAMPLE_PARAMS, "american": True, "option_type": "put"}

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_pricing_result(params, 5.67, SAMPLE_GREEKS)

    assert isinstance(result, str)


def test_explain_unified_alias() -> None:
    """explain_unified keeps compatibility with the latest handoff."""
    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        result = explain_unified(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)


def test_explain_handles_missing_market_quote() -> None:
    """Zero bid/ask must be described as an unreliable market comparison."""
    params = {**SAMPLE_PARAMS, "bid": 0.0, "ask": 0.0}

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response()
        explain_pricing_result(params, 12.34, SAMPLE_GREEKS)

        prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]

    assert "unavailable or non-positive" in prompt
    assert "no active two-sided quote" in prompt


def test_explain_requires_api_key() -> None:
    """A clear error is raised when the Groq key is missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)


def test_explain_rejects_non_groq_key() -> None:
    """A key from another provider must be rejected before making a request."""
    with patch.dict("os.environ", {"GROQ_API_KEY": "not-a-groq-key"}, clear=True):
        with pytest.raises(RuntimeError, match="start with 'gsk_'"):
            explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)


def test_surface_explanation_uses_computed_statistics() -> None:
    """Surface prompt must contain raw statistics and smoothing caveat."""
    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response("Surface explanation.")
        result = explain_volatility_surface(SAMPLE_SURFACE)

        prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]

    assert result == "Surface explanation."
    assert "AAPL" in prompt
    assert "28.00%" in prompt
    assert "42.00%" in prompt
    assert "visual only" in prompt


def test_temporal_surface_explanation_includes_changes() -> None:
    """Temporal context must include first/latest changes."""
    summary = {
        **SAMPLE_SURFACE,
        "first_snapshot": "2026-06-01",
        "median_iv_change": 0.015,
        "atm_iv_change": -0.01,
    }
    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test-key"}, clear=False),
        patch("backend.llm.explainer.requests.post") as mock_post,
    ):
        mock_post.return_value = _mock_response("Temporal explanation.")
        explain_volatility_surface(summary)
        prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]

    assert "2026-06-01" in prompt
    assert "+1.50%" in prompt
    assert "-1.00%" in prompt
