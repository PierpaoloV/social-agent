from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RuntimeSettings:
    state_dir: Path
    dry_run: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    openai_api_key: str | None
    x_api_bearer_token: str | None
    x_api_key: str | None
    x_api_secret: str | None
    x_access_token: str | None
    x_access_token_secret: str | None
    github_token: str | None


def load_runtime_settings() -> RuntimeSettings:
    state_dir = Path(os.environ.get("SOCIAL_AGENT_STATE_DIR", ".state"))
    return RuntimeSettings(
        state_dir=state_dir,
        dry_run=os.environ.get("SOCIAL_AGENT_DRY_RUN", "false").lower() == "true",
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        x_api_bearer_token=os.environ.get("X_API_BEARER_TOKEN"),
        x_api_key=os.environ.get("X_API_KEY"),
        x_api_secret=os.environ.get("X_API_SECRET"),
        x_access_token=os.environ.get("X_ACCESS_TOKEN"),
        x_access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
        github_token=os.environ.get("GITHUB_TOKEN"),
    )

