from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import SocialAgentPolicy
from .models import IdeaCandidate, SourceType, make_id


SAFE_QUERY_TERMS = {
    "agent",
    "agents",
    "automation",
    "evaluation",
    "evaluations",
    "model",
    "models",
    "prompt",
    "prompts",
    "research",
    "systems",
    "tooling",
    "tools",
    "workflow",
    "workflows",
}


@dataclass(slots=True)
class SourceReference:
    url: str
    title: str
    summary: str
    published_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceReference | None:
        url = str(payload.get("url") or payload.get("uri") or "").strip()
        if not url:
            return None
        return cls(
            url=url,
            title=str(payload.get("title") or url).strip(),
            summary=str(payload.get("summary") or payload.get("snippet") or "").strip(),
            published_at=payload.get("published_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "published_at": self.published_at,
        }


@dataclass(slots=True)
class WebContentScout:
    policy: SocialAgentPolicy
    openai_client: object

    def build_queries(self, fresh_ideas: list[IdeaCandidate]) -> list[str]:
        configured_queries: list[str] = []
        for topic in self.policy.profile.web_scout.topics:
            query = topic.strip()
            if query:
                configured_queries.append(query)
        derived_queries: list[str] = []
        for idea in fresh_ideas:
            derived = derive_safe_query(idea)
            if derived:
                derived_queries.append(derived)
        if derived_queries and self.policy.profile.web_scout.max_queries > 1:
            queries = configured_queries[: self.policy.profile.web_scout.max_queries - 1] + derived_queries
        else:
            queries = configured_queries + derived_queries
        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            normalized = " ".join(query.lower().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(query)
        return deduped[: self.policy.profile.web_scout.max_queries]

    def collect_candidates(self, fresh_ideas: list[IdeaCandidate]) -> list[IdeaCandidate]:
        config = self.policy.profile.web_scout
        if not config.enabled or config.max_candidates <= 0:
            return []
        candidates: list[IdeaCandidate] = []
        for query in self.build_queries(fresh_ideas):
            response = self._search_for_candidates(query)
            candidates.extend(parse_scout_candidates(response, query, self.policy.source_weight_for(SourceType.EXTERNAL.value, 0.4), config.max_sources_per_query))
            if len(candidates) >= config.max_candidates:
                return candidates[: config.max_candidates]
        return candidates[: config.max_candidates]

    def _search_for_candidates(self, query: str) -> dict[str, Any]:
        instructions = (
            "Find public, source-grounded material that could become thoughtful X posts for an AI builder account. "
            "Prefer concrete technical lessons, research/tooling updates, evaluations, and workflow design tradeoffs. "
            "Avoid hype, politics, drama, personal facts, medical advice, and unsupported claims. "
            "Return only JSON with key 'candidates'. Each candidate must include title, summary, topic_class, source_references, source_summary, and public_safety_note."
        )
        prompt = {
            "query": query,
            "max_candidates": self.policy.profile.web_scout.max_candidates,
            "max_sources_per_candidate": self.policy.profile.web_scout.max_sources_per_query,
            "allowed_topic_classes": list(self.policy.profile.thread_policy_config.allowed_topic_classes),
        }
        return self.openai_client.generate_json_with_web_search(self.policy.profile.scout_model_name, instructions, json.dumps(prompt))


def derive_safe_query(idea: IdeaCandidate) -> str | None:
    text = f"{idea.topic_class} {idea.title} {idea.summary}".lower()
    tokens = [token for token in re.findall(r"[a-z][a-z0-9-]{2,}", text) if token in SAFE_QUERY_TERMS]
    if not tokens:
        return None
    deduped = list(dict.fromkeys(tokens))
    return " ".join(deduped[:4])


def parse_scout_candidates(response: dict[str, Any], query: str, source_weight: float, max_sources_per_candidate: int) -> list[IdeaCandidate]:
    fallback_sources = [_source.to_dict() for _source in _source_references_from_web_sources(response.get("web_sources", []), max_sources_per_candidate)]
    candidates: list[IdeaCandidate] = []
    for item in response.get("candidates", []) or []:
        if not isinstance(item, dict):
            continue
        references = _source_references_from_payload(item.get("source_references", []), max_sources_per_candidate)
        source_payloads = [source.to_dict() for source in references] or fallback_sources[:max_sources_per_candidate]
        source_ids = [source["url"] for source in source_payloads if source.get("url")] or [query]
        summary = str(item.get("summary") or "").strip()
        title = str(item.get("title") or summary[:70] or query).strip()
        if not summary:
            continue
        candidates.append(
            IdeaCandidate(
                idea_id=make_id("idea"),
                title=title[:120],
                summary=summary,
                source_type=SourceType.EXTERNAL.value,
                source_ids=source_ids,
                topic_class=str(item.get("topic_class") or "technical_breakdown"),
                novelty_score=float(item.get("novelty_score", 0.72)),
                authenticity_score=float(item.get("authenticity_score", 0.72)),
                relevance_score=float(item.get("relevance_score", 0.74)),
                source_weight=source_weight,
                provenance=["web scout", query],
                metadata={
                    "source_references": source_payloads,
                    "scout_query": query,
                    "source_summary": str(item.get("source_summary") or summary).strip(),
                    "public_safety_note": str(item.get("public_safety_note") or "Derived from public web sources.").strip(),
                },
            )
        )
    return candidates


def _source_references_from_payload(payload: Any, limit: int) -> list[SourceReference]:
    if not isinstance(payload, list):
        return []
    references: list[SourceReference] = []
    for item in payload[:limit]:
        if isinstance(item, dict):
            reference = SourceReference.from_dict(item)
            if reference is not None:
                references.append(reference)
    return references


def _source_references_from_web_sources(payload: Any, limit: int) -> list[SourceReference]:
    if not isinstance(payload, list):
        return []
    references: list[SourceReference] = []
    for item in payload[:limit]:
        if isinstance(item, dict):
            reference = SourceReference.from_dict(item)
            if reference is not None:
                references.append(reference)
    return references
