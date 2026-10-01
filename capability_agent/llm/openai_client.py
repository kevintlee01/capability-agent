"""OpenAI-backed LLMClient implementation."""
from openai import OpenAI


class OpenAIClient:
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self._client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
