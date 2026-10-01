"""Build the configured LLM client. One place to add a new provider."""
from capability_agent.config import Settings
from capability_agent.llm.base import LLMClient


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "gemini":
        from capability_agent.llm.gemini_client import GeminiClient
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set. Put it in .env (see .env.example).")
        return GeminiClient(api_key=settings.gemini_api_key, model_name=settings.gemini_model)
    if settings.llm_provider == "openai":
        from capability_agent.llm.openai_client import OpenAIClient
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set. Put it in .env (see .env.example).")
        return OpenAIClient(api_key=settings.openai_api_key, model_name=settings.openai_model)
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'gemini' or 'openai'.")
