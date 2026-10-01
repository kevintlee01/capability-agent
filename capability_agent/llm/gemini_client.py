"""Gemini-backed LLMClient implementation (Google's free-tier-friendly API)."""
from google import genai


class GeminiClient:
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        self._client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config={"system_instruction": system_prompt, "response_mime_type": "application/json"},
        )
        return response.text or ""
