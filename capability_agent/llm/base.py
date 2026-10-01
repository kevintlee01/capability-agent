"""Minimal LLM client contract: plain text in, plain text out."""
from typing import Protocol


class LLMClient(Protocol):
    model_name: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant's raw text response for one turn."""
        ...
