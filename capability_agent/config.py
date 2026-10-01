"""Runtime settings, loaded from environment / .env. No secrets committed."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    target_base_url: str = "http://127.0.0.1:8731"
    allowlist_path: str = "config/allowlist.yml"
    artifact_dir: str = "artifacts"
    evidence_dir: str = "evidence"
    max_discovery_steps: int = 25
    headless: bool = False


settings = Settings()
