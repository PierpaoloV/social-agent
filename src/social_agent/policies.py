from __future__ import annotations

from .config import ProfileConfig, SeedsConfig


def is_language_allowed(profile: ProfileConfig, kind: str, language: str) -> bool:
    if kind == "reply":
        return language in profile.allowed_reply_languages
    return language in profile.allowed_post_languages


def is_thread_allowed(profile: ProfileConfig, topic_class: str, thread_posts: list[str]) -> bool:
    if not thread_posts:
        return True
    if len(thread_posts) > int(profile.thread_policy["max_thread_posts"]):
        return False
    return topic_class in profile.thread_policy["allowed_topic_classes"]


def external_query_budget(seeds: SeedsConfig, strict_read_budget: bool) -> list[str]:
    if strict_read_budget:
        return seeds.keywords[:3]
    return seeds.keywords

