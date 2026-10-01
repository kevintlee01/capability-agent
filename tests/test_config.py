"""Settings load sane defaults and respect environment overrides."""
import os

from capability_agent.config import Settings


def test_settings_defaults_without_env():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "gemini"
    assert settings.gemini_model == "gemini-flash-lite-latest"
    assert settings.target_base_url == "http://127.0.0.1:8731"
    assert settings.headless is False
    assert settings.max_discovery_steps == 25


def test_settings_reads_environment_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("HEADLESS", "true")
    monkeypatch.setenv("MAX_DISCOVERY_STEPS", "7")
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "openai"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.headless is True
    assert settings.max_discovery_steps == 7
