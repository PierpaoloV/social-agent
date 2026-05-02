from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError

from .config import SeedsConfig, SocialAgentPolicy
from .history import build_x_post_url
from .models import EngagementSuggestion, FollowSuggestion, make_id, utc_now_iso


@dataclass(slots=True)
class XEngagementDiscovery:
    policy: SocialAgentPolicy
    x_client: object

    def build_engagement_suggestions(self) -> list[EngagementSuggestion]:
        suggestions: list[EngagementSuggestion] = []
        for index, query in enumerate(self.policy.engagement_keywords()[:3]):
            try:
                payload = self.x_client.search_recent_posts(query, max_results=2)
            except HTTPError as exc:
                if exc.code in {400, 401, 402, 403, 429}:
                    return []
                raise
            user_lookup = {user.get("id"): user.get("username", user.get("id", "unknown")) for user in payload.get("includes", {}).get("users", [])}
            for tweet in payload.get("data", [])[:1]:
                post_id = tweet.get("id")
                target_handle = user_lookup.get(tweet.get("author_id"), tweet.get("author_id", "unknown"))
                suggestions.append(
                    EngagementSuggestion(
                        suggestion_id=make_id("eng"),
                        suggestion_type="reply" if index < 2 else "quote_post",
                        target_handle=target_handle,
                        context_summary=f"Recent post by @{target_handle} matched query '{query}'" if target_handle != "unknown" else f"Recent post matched query '{query}'",
                        draft_text=f"Interesting angle on {query}. The part I care about most is whether this survives contact with real workflows.",
                        created_at=utc_now_iso(),
                        source_post_id=post_id,
                        metadata={"post_url": build_x_post_url(target_handle, post_id), "query": query},
                    )
                )
        return suggestions[:3]


def build_follow_suggestions(seeds: SeedsConfig) -> list[FollowSuggestion]:
    suggestions: list[FollowSuggestion] = []
    for item in list(seeds.must_follow)[: seeds.weekly_limit]:
        scoring = seeds.follow_scoring
        suggestions.append(
            FollowSuggestion(
                suggestion_id=make_id("follow"),
                handle=str(item["handle"]),
                display_name=str(item["handle"]),
                category=str(item["category"]),
                reason=str(item["reason"]),
                relevance_score=scoring["relevance_weight"],
                signal_score=scoring["signal_weight"],
                style_fit_score=scoring["style_fit_weight"],
                redundancy_penalty=scoring["redundancy_penalty"],
                created_at=utc_now_iso(),
            )
        )
    return suggestions[: seeds.weekly_limit]
