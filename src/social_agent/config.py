from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .models import DraftKind, SourceType


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}")
    return data


@dataclass(slots=True)
class ThreadPolicy:
    default_mode: str
    max_thread_posts: int
    allowed_topic_classes: tuple[str, ...]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ThreadPolicy:
        return cls(
            default_mode=str(raw["default_mode"]),
            max_thread_posts=int(raw["max_thread_posts"]),
            allowed_topic_classes=tuple(str(item) for item in raw.get("allowed_topic_classes", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_mode": self.default_mode,
            "max_thread_posts": self.max_thread_posts,
            "allowed_topic_classes": list(self.allowed_topic_classes),
        }


@dataclass(slots=True)
class ProfileConfig:
    account_identity: str
    timezone: str
    draft_every_days: int
    weekly_digest_day: str
    publish_window: str
    allowed_post_languages: tuple[str, ...]
    allowed_reply_languages: tuple[str, ...]
    tone_rules: tuple[str, ...]
    forbidden_topics: tuple[str, ...]
    fixed_feedback_tags: tuple[str, ...]
    repo_allowlist: tuple[str, ...]
    source_weights: dict[str, float]
    strict_read_budget: bool
    thread_policy_config: ThreadPolicy
    model_name: str
    immediate_types: tuple[str, ...]
    queued_types: tuple[str, ...]
    draft_anchor_date: date = date(2026, 4, 23)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ProfileConfig:
        source_policy = dict(raw["source_policy"])
        normalized_weights = {
            SourceType.GITHUB.value if key == "github_milestones" else str(key): float(value)
            for key, value in dict(source_policy.get("source_weights", {})).items()
        }
        return cls(
            account_identity=str(raw["persona"]["account_identity"]),
            timezone=str(raw["cadence"]["timezone"]),
            draft_every_days=int(raw["cadence"]["draft_every_days"]),
            weekly_digest_day=str(raw["cadence"]["weekly_digest_day"]),
            publish_window=str(raw["cadence"]["publish_window"]),
            allowed_post_languages=tuple(str(item) for item in raw["persona"]["voice"]["allowed_post_languages"]),
            allowed_reply_languages=tuple(str(item) for item in raw["persona"]["voice"]["allowed_reply_languages"]),
            tone_rules=tuple(str(item) for item in raw["persona"]["voice"].get("tone_rules", [])),
            forbidden_topics=tuple(str(item) for item in raw["persona"].get("forbidden_topics", [])),
            fixed_feedback_tags=tuple(str(item) for item in raw["feedback"]["fixed_tags"]),
            repo_allowlist=tuple(str(item) for item in source_policy["repo_allowlist"]),
            source_weights=normalized_weights,
            strict_read_budget=bool(source_policy.get("strict_read_budget", True)),
            thread_policy_config=ThreadPolicy.from_raw(dict(raw["thread_policy"])),
            model_name=str(raw["models"]["cheap_default"]["model"]),
            immediate_types=tuple(str(item) for item in raw["publishing"]["immediate_types"]),
            queued_types=tuple(str(item) for item in raw["publishing"]["queued_types"]),
        )

    @property
    def thread_policy(self) -> dict[str, Any]:
        return self.thread_policy_config.to_dict()


@dataclass(slots=True)
class SeedsConfig:
    must_follow: tuple[dict[str, Any], ...]
    starter_candidates: tuple[dict[str, Any], ...]
    keywords: tuple[str, ...]
    follow_scoring: dict[str, float]
    weekly_limit: int

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SeedsConfig:
        return cls(
            must_follow=tuple(dict(item) for item in raw["seed_accounts"]["must_follow"]),
            starter_candidates=tuple(dict(item) for item in raw["seed_accounts"]["starter_candidates"]),
            keywords=tuple(str(item) for item in raw["discovery"]["keywords"]),
            follow_scoring={str(key): float(value) for key, value in dict(raw["discovery"]["follow_scoring"]).items()},
            weekly_limit=int(raw["discovery"]["weekly_limit"]),
        )


@dataclass(slots=True)
class SocialAgentPolicy:
    profile: ProfileConfig
    seeds: SeedsConfig

    def source_weight_for(self, source_type: str, default: float = 0.0) -> float:
        return float(self.profile.source_weights.get(source_type, default))

    def allows_language(self, kind: str, language: str) -> bool:
        if kind == DraftKind.REPLY.value:
            return language in self.profile.allowed_reply_languages
        return language in self.profile.allowed_post_languages

    def allows_thread(self, topic_class: str, thread_posts: list[str]) -> bool:
        if not thread_posts:
            return True
        if len(thread_posts) > self.profile.thread_policy_config.max_thread_posts:
            return False
        return topic_class in self.profile.thread_policy_config.allowed_topic_classes

    def engagement_keywords(self) -> list[str]:
        if self.profile.strict_read_budget:
            return list(self.seeds.keywords[:3])
        return list(self.seeds.keywords)

    def publish_mode_for(self, kind: str) -> str:
        if kind in self.profile.immediate_types:
            return "immediate"
        if kind in self.profile.queued_types:
            return "queued"
        raise ValueError(f"Unsupported publish kind: {kind}")


def load_profile_config(path: str | Path = "config/profile.yaml") -> ProfileConfig:
    return ProfileConfig.from_raw(_load_yaml(path))


def load_seeds_config(path: str | Path = "config/seeds.yaml") -> SeedsConfig:
    return SeedsConfig.from_raw(_load_yaml(path))


def load_policy(
    profile_path: str | Path = "config/profile.yaml",
    seeds_path: str | Path = "config/seeds.yaml",
) -> SocialAgentPolicy:
    profile = load_profile_config(profile_path)
    seeds = load_seeds_config(seeds_path)
    return SocialAgentPolicy(profile=profile, seeds=seeds)
