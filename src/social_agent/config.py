from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ProfileConfig:
    raw: dict[str, Any]

    @property
    def timezone(self) -> str:
        return self.raw["cadence"]["timezone"]

    @property
    def draft_every_days(self) -> int:
        return int(self.raw["cadence"]["draft_every_days"])

    @property
    def weekly_digest_day(self) -> str:
        return str(self.raw["cadence"]["weekly_digest_day"])

    @property
    def publish_window(self) -> str:
        return str(self.raw["cadence"]["publish_window"])

    @property
    def allowed_post_languages(self) -> list[str]:
        return list(self.raw["persona"]["voice"]["allowed_post_languages"])

    @property
    def allowed_reply_languages(self) -> list[str]:
        return list(self.raw["persona"]["voice"]["allowed_reply_languages"])

    @property
    def fixed_feedback_tags(self) -> list[str]:
        return list(self.raw["feedback"]["fixed_tags"])

    @property
    def repo_allowlist(self) -> list[str]:
        return list(self.raw["source_policy"]["repo_allowlist"])

    @property
    def source_weights(self) -> dict[str, float]:
        return dict(self.raw["source_policy"]["source_weights"])

    @property
    def thread_policy(self) -> dict[str, Any]:
        return dict(self.raw["thread_policy"])

    @property
    def model_name(self) -> str:
        return str(self.raw["models"]["cheap_default"]["model"])

    @property
    def immediate_types(self) -> list[str]:
        return list(self.raw["publishing"]["immediate_types"])

    @property
    def queued_types(self) -> list[str]:
        return list(self.raw["publishing"]["queued_types"])


@dataclass(slots=True)
class SeedsConfig:
    raw: dict[str, Any]

    @property
    def must_follow(self) -> list[dict[str, Any]]:
        return list(self.raw["seed_accounts"]["must_follow"])

    @property
    def starter_candidates(self) -> list[dict[str, Any]]:
        return list(self.raw["seed_accounts"]["starter_candidates"])

    @property
    def keywords(self) -> list[str]:
        return list(self.raw["discovery"]["keywords"])

    @property
    def follow_scoring(self) -> dict[str, float]:
        return dict(self.raw["discovery"]["follow_scoring"])

    @property
    def weekly_limit(self) -> int:
        return int(self.raw["discovery"]["weekly_limit"])


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}")
    return data


def load_profile_config(path: str | Path = "config/profile.yaml") -> ProfileConfig:
    return ProfileConfig(raw=_load_yaml(path))


def load_seeds_config(path: str | Path = "config/seeds.yaml") -> SeedsConfig:
    return SeedsConfig(raw=_load_yaml(path))
