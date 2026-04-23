from __future__ import annotations

import json
from dataclasses import dataclass

from .config import ProfileConfig
from .models import DraftBatch, DraftKind, DraftOption, IdeaCandidate, PreferenceSnapshot, make_id, make_option_id, make_short_id, utc_now_iso
from .openai_client import OpenAIClient
from .policies import is_language_allowed, is_thread_allowed


@dataclass(slots=True)
class DraftGenerator:
    profile: ProfileConfig
    openai_client: OpenAIClient | None = None
    dry_run: bool = False

    def generate_batch(self, ideas: list[IdeaCandidate], cycle_key: str, scheduled_for: str, preference_snapshot: PreferenceSnapshot | None = None) -> DraftBatch:
        batch_id = make_short_id("b")
        selected = self._pad_ideas(ideas[:3])
        options = self._generate_with_model(batch_id, selected, preference_snapshot)
        if not options:
            options = self._generate_heuristic(batch_id, selected)
        options = self._pad_options(batch_id, selected, options)
        options = self._normalize_option_ids(batch_id, options)
        batch = DraftBatch(
            batch_id=batch_id,
            created_at=utc_now_iso(),
            scheduled_for=scheduled_for,
            cycle_key=cycle_key,
            options=options[:3],
            idea_ids=[idea.idea_id for idea in selected],
        )
        batch.validate()
        return batch

    def _normalize_option_ids(self, batch_id: str, options: list[DraftOption]) -> list[DraftOption]:
        normalized: list[DraftOption] = []
        for index, option in enumerate(options[:3], start=1):
            option.draft_id = make_option_id(index)
            option.batch_id = batch_id
            normalized.append(option)
        return normalized

    def _pad_ideas(self, ideas: list[IdeaCandidate]) -> list[IdeaCandidate]:
        if not ideas:
            return []
        padded = list(ideas)
        while len(padded) < 3:
            source = padded[len(padded) % len(ideas)]
            padded.append(
                IdeaCandidate(
                    idea_id=make_id("idea"),
                    title=f"{source.title} variation {len(padded) + 1}",
                    summary=source.summary,
                    source_type=source.source_type,
                    source_ids=list(source.source_ids),
                    topic_class=source.topic_class,
                    novelty_score=max(source.novelty_score - 0.02 * len(padded), 0.55),
                    authenticity_score=source.authenticity_score,
                    relevance_score=source.relevance_score,
                    source_weight=source.source_weight,
                    provenance=source.provenance + [f"variation_{len(padded) + 1}"],
                    metadata={**source.metadata, "is_variation": True},
                )
            )
        return padded[:3]

    def _pad_options(self, batch_id: str, ideas: list[IdeaCandidate], options: list[DraftOption]) -> list[DraftOption]:
        padded = list(options)
        if not ideas:
            return padded
        while len(padded) < 3:
            source_idea = ideas[len(padded) % len(ideas)]
            padded.append(
                DraftOption(
                    draft_id="pending",
                    batch_id=batch_id,
                    kind=DraftKind.ORIGINAL.value,
                    topic_class=source_idea.topic_class,
                    language="en",
                    text=f"One thing I keep finding useful: {source_idea.summary}",
                    source_provenance=source_idea.provenance,
                    created_at=utc_now_iso(),
                    model_name="fallback-padding",
                    score=source_idea.overall_score,
                )
            )
        return padded[:3]

    def _generate_with_model(self, batch_id: str, ideas: list[IdeaCandidate], preference_snapshot: PreferenceSnapshot | None) -> list[DraftOption]:
        if self.dry_run or not self.openai_client or not ideas:
            return []
        instructions = (
            "You write X posts for a personal AI engineer account. "
            "Be concise, technical, and grounded. Use English by default. "
            "Avoid politics, flame wars, hype, and unsupported claims. "
            "Return JSON with key 'drafts', each having language, text, topic_class, kind, thread_posts."
        )
        prompt = {
            "ideas": [idea.to_dict() for idea in ideas],
            "preferences": preference_snapshot.to_dict() if preference_snapshot else None,
            "thread_policy": self.profile.thread_policy,
            "allowed_post_languages": self.profile.allowed_post_languages,
        }
        response = self.openai_client.generate_json(self.profile.model_name, instructions, json.dumps(prompt))
        drafts = response.get("drafts", [])
        options: list[DraftOption] = []
        for draft in drafts[:3]:
            language = draft.get("language", "en")
            thread_posts = list(draft.get("thread_posts", []))
            if not is_language_allowed(self.profile, draft.get("kind", DraftKind.ORIGINAL.value), language):
                language = "en"
            if not is_thread_allowed(self.profile, draft.get("topic_class", ideas[0].topic_class if ideas else "general"), thread_posts):
                thread_posts = []
            options.append(
                DraftOption(
                    draft_id="pending",
                    batch_id=batch_id,
                    kind=draft.get("kind", DraftKind.ORIGINAL.value),
                    topic_class=draft.get("topic_class", ideas[0].topic_class if ideas else "general"),
                    language=language,
                    text=draft["text"],
                    thread_posts=thread_posts,
                    source_provenance=ideas[0].provenance if ideas else [],
                    created_at=utc_now_iso(),
                    model_name=self.profile.model_name,
                    score=0.75,
                )
            )
        return options

    def _generate_heuristic(self, batch_id: str, ideas: list[IdeaCandidate]) -> list[DraftOption]:
        options: list[DraftOption] = []
        for idea in ideas:
            tone_prefix = {
                "project_milestone": "Small milestone, but an important one:",
                "technical_breakdown": "One practical thing I keep noticing:",
                "research_reflection": "A research lesson I keep coming back to:",
            }.get(idea.topic_class, "A useful thing I learned recently:")
            text = f"{tone_prefix} {idea.summary}\n\nWhat I care about most here is the bridge between research clarity and practical AI systems."
            thread_posts: list[str] = []
            options.append(
                DraftOption(
                    draft_id="pending",
                    batch_id=batch_id,
                    kind=DraftKind.ORIGINAL.value,
                    topic_class=idea.topic_class,
                    language="en",
                    text=text[:280],
                    source_provenance=idea.provenance,
                    created_at=utc_now_iso(),
                    model_name="heuristic-drafter",
                    score=idea.overall_score,
                    thread_posts=thread_posts,
                )
            )
        return options
