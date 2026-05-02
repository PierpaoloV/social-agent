from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import ProfileConfig
from .models import DraftBatch, DraftOption


QUALITY_THRESHOLD = 0.70


@dataclass(slots=True)
class DraftReviewResult:
    batch: DraftBatch | None
    accepted_count: int
    rejected_count: int
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.batch is not None and self.accepted_count > 0


@dataclass(slots=True)
class DraftCritic:
    profile: ProfileConfig
    openai_client: object

    def review_batch(self, batch: DraftBatch, recent_drafts: list[str]) -> DraftReviewResult:
        response = self._call_critic(batch, recent_drafts)
        reviewed_options = response.get("drafts", [])
        accepted_options: list[DraftOption] = []
        rejected_count = 0
        options_by_id = {option.draft_id: option for option in batch.options}
        for item in reviewed_options:
            if not isinstance(item, dict):
                continue
            draft_id = str(item.get("draft_id", ""))
            original = options_by_id.get(draft_id)
            if original is None:
                continue
            if not _passes_review(item):
                rejected_count += 1
                continue
            revised = DraftOption.from_dict(original.to_dict())
            revised.text = str(item.get("revised_text") or original.text).strip()
            revised.metadata = {
                **dict(revised.metadata or {}),
                "critic_scores": dict(item.get("scores") or {}),
                "critic_issues": [str(issue) for issue in item.get("issues", [])],
                "critic_recommendation": str(item.get("recommendation") or "accept"),
            }
            accepted_options.append(revised)
        if not accepted_options:
            return DraftReviewResult(
                batch=None,
                accepted_count=0,
                rejected_count=max(rejected_count, len(batch.options)),
                reason=str(response.get("reason") or "No safe, high-quality draft was produced."),
            )
        for index, option in enumerate(accepted_options[:3], start=1):
            option.draft_id = f"d{index}"
            option.batch_id = batch.batch_id
        batch.options = accepted_options[:3]
        batch.idea_ids = list(batch.idea_ids)
        return DraftReviewResult(
            batch=batch,
            accepted_count=len(batch.options),
            rejected_count=max(rejected_count, len(options_by_id) - len(batch.options)),
        )

    def _call_critic(self, batch: DraftBatch, recent_drafts: list[str]) -> dict[str, Any]:
        instructions = (
            "You are the final critic for X draft options before human Telegram review. "
            "Revise only when the source material supports the claim. Remove private or identifying details. "
            "Reject drafts that expose private facts, lack source support, sound like marketing, repeat recent drafts, or are too generic. "
            "Return only JSON with key 'drafts'. Each item must include draft_id, revised_text, recommendation, scores, issues, privacy_pass, and fact_risk_pass. "
            "Scores must include privacy, fact_risk, voice_fit, novelty, and specificity from 0 to 1."
        )
        prompt = {
            "account_identity": self.profile.account_identity,
            "tone_rules": list(self.profile.tone_rules),
            "forbidden_topics": list(self.profile.forbidden_topics),
            "recent_drafts": recent_drafts[:6],
            "drafts": [option.to_dict() for option in batch.options],
            "quality_threshold": QUALITY_THRESHOLD,
        }
        return self.openai_client.generate_json(self.profile.critic_model_name, instructions, json.dumps(prompt))


class PassthroughDraftCritic:
    def review_batch(self, batch: DraftBatch, recent_drafts: list[str]) -> DraftReviewResult:
        return DraftReviewResult(batch=batch, accepted_count=len(batch.options), rejected_count=0)


def _passes_review(item: dict[str, Any]) -> bool:
    if not bool(item.get("privacy_pass", False)):
        return False
    if not bool(item.get("fact_risk_pass", False)):
        return False
    scores = dict(item.get("scores") or {})
    values = [
        float(scores.get("privacy", 0.0)),
        float(scores.get("fact_risk", 0.0)),
        float(scores.get("voice_fit", 0.0)),
        float(scores.get("novelty", 0.0)),
        float(scores.get("specificity", 0.0)),
    ]
    return sum(values) / len(values) >= QUALITY_THRESHOLD
