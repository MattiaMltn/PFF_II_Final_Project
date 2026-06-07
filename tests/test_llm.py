"""Tests for backend/llm/explainer.py."""

from unittest.mock import MagicMock, patch

from backend.llm.explainer import explain_pricing_result, explain_unified


SAMPLE_PARAMS = {
    "ticker": "AAPL",
    "S": 298.87,
    "K": 300.0,
    "T": 0.25,
    "r": 0.0425,
    "sigma": 0.243,
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
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=text)]
    return mock_message


def test_explain_returns_string() -> None:
    """explain_pricing_result must return a non-empty string."""
    with patch("backend.llm.explainer.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = _mock_response()
        result = explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_calls_correct_model() -> None:
    """The explainer must use the Claude Sonnet 4 model from the guide."""
    with patch("backend.llm.explainer.anthropic.Anthropic") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.messages.create.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        call_kwargs = mock_instance.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"


def test_explain_prompt_contains_key_values() -> None:
    """Prompt must include the core pricing context."""
    with patch("backend.llm.explainer.anthropic.Anthropic") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.messages.create.return_value = _mock_response()
        explain_pricing_result(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

        prompt = mock_instance.messages.create.call_args[1]["messages"][0][
            "content"
        ]
        assert "AAPL" in prompt
        assert "12.34" in prompt
        assert "Delta" in prompt


def test_explain_with_american_option() -> None:
    """The explainer must work for American options without errors."""
    params = {**SAMPLE_PARAMS, "american": True, "option_type": "put"}

    with patch("backend.llm.explainer.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = _mock_response()
        result = explain_pricing_result(params, 5.67, SAMPLE_GREEKS)

    assert isinstance(result, str)


def test_explain_unified_alias() -> None:
    """explain_unified keeps compatibility with the latest handoff."""
    with patch("backend.llm.explainer.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = _mock_response()
        result = explain_unified(SAMPLE_PARAMS, 12.34, SAMPLE_GREEKS)

    assert isinstance(result, str)
