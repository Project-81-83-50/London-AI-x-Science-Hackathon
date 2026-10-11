import os
from pathlib import Path

from dotenv import dotenv_values

from ..paths import PROCESSED_DIR, REPO_ROOT, SEM_PIPELINE_DIR
from .models import Settings


class ResearchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OutputError(ResearchError):
    pass


def environment() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (REPO_ROOT / ".env", SEM_PIPELINE_DIR / ".env"):
        if path.is_file():
            merged.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    merged.update(os.environ)
    return merged


def settings_from_env(env: dict[str, str] | None = None) -> Settings:
    env = environment() if env is None else env
    return Settings(
        writer_model=env.get("RESEARCH_MODEL", "claude-sonnet-5-5"),
        reviewer_model=env.get("RESEARCH_REVIEWER_MODEL", "claude-sonnet-5-5"),
        online=env.get("RESEARCH_ONLINE", "true").lower() not in {"0", "false", "no"},
        deadline=float(env.get("RESEARCH_DEADLINE_SECONDS", "240")),
    )


def require_key(env: dict[str, str]) -> str:
    value = env.get("ANTHROPIC_API_KEY", "").strip()
    if not value or value.lower() in {"your_api_key_here", "your_actual_key_here", "..."}:
        raise ResearchError(
            "credentials_missing", "Set ANTHROPIC_API_KEY in sem_pipeline/.env or the server environment."
        )
    return value


def store_path() -> Path:
    return PROCESSED_DIR / "research"
