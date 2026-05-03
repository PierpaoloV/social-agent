from __future__ import annotations

from dataclasses import dataclass

from .config import SocialAgentPolicy
from .models import IdeaCandidate, InboxItem, SourceType, make_id, utc_now_iso
from .state import SocialAgentState


@dataclass(slots=True)
class IdeaInventory:
    policy: SocialAgentPolicy
    state: SocialAgentState
    github_source: object
    web_scout: object | None = None

    def collect_fresh_ideas(self) -> list[IdeaCandidate]:
        archived_source_keys = self.state.ideas.archived_source_keys()
        ideas: list[IdeaCandidate] = []
        for item in self.state.inbox.list_unprocessed():
            candidate = self._idea_from_inbox_item(item)
            if candidate.source_key not in archived_source_keys:
                ideas.append(candidate)
        for candidate in self.github_source.collect_candidates(
            list(self.policy.profile.repo_allowlist),
            self.policy.source_weight_for(SourceType.GITHUB.value, 0.9),
        ):
            if candidate.source_key not in archived_source_keys:
                ideas.append(candidate)
        ideas.extend(self.state.ideas.list_reusable_backlog())
        if self.web_scout is not None:
            try:
                scout_candidates = self.web_scout.collect_candidates(ideas)
            except Exception as exc:
                self.state.runtime.write(
                    "latest_web_scout_error",
                    {
                        "status": "degraded",
                        "created_at": utc_now_iso(),
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                scout_candidates = []
            for candidate in scout_candidates:
                if candidate.source_key not in archived_source_keys:
                    ideas.append(candidate)
        for idea in ideas:
            if idea.source_type != SourceType.BACKLOG.value:
                self.state.ideas.save(idea)
        return ideas

    def mark_drafted(self, idea_ids: list[str]) -> None:
        processed_inbox_ids = self.state.ideas.mark_drafted(idea_ids)
        for source_id in processed_inbox_ids:
            self.state.inbox.mark_processed(source_id)

    def _idea_from_inbox_item(self, item: InboxItem) -> IdeaCandidate:
        text = item.content_text.strip()
        topic_class = infer_topic_class(text)
        novelty = 0.86 if item.media_paths else 0.74
        authenticity = 0.96
        relevance = 0.82 if len(text) > 12 else 0.66
        title = text[:70] if text else "Photo-based update"
        return IdeaCandidate(
            idea_id=make_id("idea"),
            title=title,
            summary=text or "A personal milestone shared through a private photo inbox item.",
            source_type=SourceType.TELEGRAM.value,
            source_ids=[item.item_id],
            topic_class=topic_class,
            novelty_score=novelty,
            authenticity_score=authenticity,
            relevance_score=relevance,
            source_weight=self.policy.source_weight_for(SourceType.TELEGRAM.value, 1.0),
            provenance=["telegram inbox", item.item_id],
            metadata={"has_media": bool(item.media_paths)},
        )


def infer_topic_class(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["defended", "phd", "paper", "study", "research"]):
        return "research_reflection"
    if any(token in lowered for token in ["release", "feature", "demo", "workflow", "repo", "agent"]):
        return "project_milestone"
    if any(token in lowered for token in ["lesson", "noticed", "thing i learned", "why"]):
        return "technical_breakdown"
    return "project_milestone"
