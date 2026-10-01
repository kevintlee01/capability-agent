"""Explicit, configurable allowlist: the agent must not act outside it."""
from __future__ import annotations

import fnmatch
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel

DEFAULT_ALLOWLIST_PATH = Path("config/allowlist.yml")


class GuardrailViolation(Exception):
    """Raised when an action would step outside the configured allowlist."""


class AllowlistPolicy(BaseModel):
    allowed_domains: list[str]
    allowed_route_prefixes: list[str]
    allowed_actions: list[str]

    @classmethod
    def load(cls, path: Path = DEFAULT_ALLOWLIST_PATH) -> AllowlistPolicy:
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if not any(fnmatch.fnmatch(parsed.netloc, pattern) for pattern in self.allowed_domains):
            raise GuardrailViolation(f"Domain '{parsed.netloc}' is not in the allowlist.")
        if self.allowed_route_prefixes and not any(path.startswith(prefix) for prefix in self.allowed_route_prefixes):
            raise GuardrailViolation(f"Route '{path}' is not in the allowed route prefixes.")

    def check_action(self, action_name: str) -> None:
        if action_name not in self.allowed_actions:
            raise GuardrailViolation(f"Action type '{action_name}' is not in the allowlist.")
