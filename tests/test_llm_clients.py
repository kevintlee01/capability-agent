"""LLM client request construction, mocked at the SDK boundary, plus provider factory wiring."""
from unittest.mock import MagicMock, patch

import pytest

from capability_agent.config import Settings
from capability_agent.llm.factory import build_llm_client


def test_gemini_client_builds_request_and_returns_text():
    with patch("capability_agent.llm.gemini_client.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text="{}")
        mock_client_cls.return_value = mock_client
        from capability_agent.llm.gemini_client import GeminiClient

        client = GeminiClient(api_key="k", model_name="gemini-flash-lite-latest")
        result = client.complete("system prompt", "user prompt")

        assert result == "{}"
        mock_client_cls.assert_called_once_with(api_key="k")
        _, kwargs = mock_client.models.generate_content.call_args
        assert kwargs["model"] == "gemini-flash-lite-latest"
        assert kwargs["contents"] == "user prompt"
        assert kwargs["config"]["system_instruction"] == "system prompt"
        assert kwargs["config"]["response_mime_type"] == "application/json"


def test_gemini_client_handles_empty_response_text():
    with patch("capability_agent.llm.gemini_client.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=None)
        mock_client_cls.return_value = mock_client
        from capability_agent.llm.gemini_client import GeminiClient

        client = GeminiClient(api_key="k")
        assert client.complete("sys", "user") == ""


def test_openai_client_builds_request_and_returns_text():
    with patch("capability_agent.llm.openai_client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_message = MagicMock(content='{"ok": true}')
        mock_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=mock_message)])
        mock_openai_cls.return_value = mock_client
        from capability_agent.llm.openai_client import OpenAIClient

        client = OpenAIClient(api_key="k", model_name="gpt-4o")
        result = client.complete("system prompt", "user prompt")

        assert result == '{"ok": true}'
        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["messages"][0] == {"role": "system", "content": "system prompt"}
        assert kwargs["messages"][1] == {"role": "user", "content": "user prompt"}


def test_factory_builds_gemini_client_when_configured():
    with patch("capability_agent.llm.gemini_client.genai.Client"):
        settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k")
        client = build_llm_client(settings)
        assert client.model_name == settings.gemini_model


def test_factory_builds_openai_client_when_configured():
    with patch("capability_agent.llm.openai_client.OpenAI"):
        settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="k")
        client = build_llm_client(settings)
        assert client.model_name == settings.openai_model


def test_factory_raises_when_gemini_key_missing():
    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_llm_client(settings)


def test_factory_raises_when_openai_key_missing():
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_llm_client(settings)


def test_factory_raises_on_unknown_provider():
    settings = Settings(_env_file=None, llm_provider="carrier-pigeon")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        build_llm_client(settings)
