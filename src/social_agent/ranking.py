from __future__ import annotations

from collections import Counter

from .models import IdeaCandidate


def dedupe_candidates(candidates: list[IdeaCandidate]) -> list[IdeaCandidate]:
    seen: set[tuple[str, str]] = set()
    unique: list[IdeaCandidate] = []
    for candidate in candidates:
        key = (candidate.title.lower().strip(), candidate.topic_class)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def rank_candidates(candidates: list[IdeaCandidate], recent_topics: list[str] | None = None) -> list[IdeaCandidate]:
    recent_topics = recent_topics or []
    topic_counts = Counter(recent_topics)
    scored: list[tuple[float, IdeaCandidate]] = []
    for candidate in dedupe_candidates(candidates):
        topic_penalty = min(topic_counts.get(candidate.topic_class, 0) * 0.08, 0.24)
        score = candidate.overall_score - topic_penalty
        scored.append((score, candidate))
    return [candidate for _, candidate in sorted(scored, key=lambda item: item[0], reverse=True)]

