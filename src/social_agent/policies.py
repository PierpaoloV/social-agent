from __future__ import annotations

from .config import ProfileConfig, SeedsConfig, SocialAgentPolicy


def is_language_allowed(profile: ProfileConfig, kind: str, language: str) -> bool:
    return SocialAgentPolicy(profile=profile, seeds=SeedsConfig((), (), (), {}, 0)).allows_language(kind, language)


def is_thread_allowed(profile: ProfileConfig, topic_class: str, thread_posts: list[str]) -> bool:
    return SocialAgentPolicy(profile=profile, seeds=SeedsConfig((), (), (), {}, 0)).allows_thread(topic_class, thread_posts)


def external_query_budget(seeds: SeedsConfig, strict_read_budget: bool) -> list[str]:
    if strict_read_budget:
        return seeds.keywords[:3]
    return seeds.keywords
