from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.config import load_profile_config
from social_agent.draft_review import DraftCritic, PassthroughDraftCritic
from social_agent.models import DraftBatch, DraftKind, DraftOption, utc_now_iso


class FakeCriticClient:
    def __init__(self, response: dict) -> None:
        self.response = response

    def generate_json(self, model: str, instructions: str, prompt: str) -> dict:
        return self.response


def _batch() -> DraftBatch:
    return DraftBatch(
        batch_id="b1234",
        created_at=utc_now_iso(),
        scheduled_for="2026-05-02T11:00",
        cycle_key="2026-05-02",
        idea_ids=["idea_1"],
        options=[
            DraftOption(
                draft_id="d1",
                batch_id="b1234",
                kind=DraftKind.ORIGINAL.value,
                topic_class="technical_breakdown",
                language="en",
                text="Original text",
                source_provenance=["web scout"],
                created_at=utc_now_iso(),
                model_name="test",
            )
        ],
    )


class DraftReviewTest(unittest.TestCase):
    def test_critic_revises_passing_draft(self) -> None:
        profile = load_profile_config()
        critic = DraftCritic(
            profile=profile,
            openai_client=FakeCriticClient(
                {
                    "drafts": [
                        {
                            "draft_id": "d1",
                            "revised_text": "Revised public-safe text",
                            "recommendation": "accept",
                            "privacy_pass": True,
                            "fact_risk_pass": True,
                            "scores": {
                                "privacy": 0.95,
                                "fact_risk": 0.9,
                                "voice_fit": 0.8,
                                "novelty": 0.75,
                                "specificity": 0.8,
                            },
                            "issues": [],
                        }
                    ]
                }
            ),
        )
        result = critic.review_batch(_batch(), recent_drafts=[])
        self.assertTrue(result.accepted)
        self.assertEqual(result.batch.options[0].text, "Revised public-safe text")
        self.assertEqual(result.batch.options[0].metadata["critic_recommendation"], "accept")

    def test_critic_rejects_all_when_scores_fail(self) -> None:
        profile = load_profile_config()
        critic = DraftCritic(
            profile=profile,
            openai_client=FakeCriticClient(
                {
                    "reason": "Too generic",
                    "drafts": [
                        {
                            "draft_id": "d1",
                            "revised_text": "Still generic",
                            "recommendation": "reject",
                            "privacy_pass": True,
                            "fact_risk_pass": True,
                            "scores": {
                                "privacy": 0.9,
                                "fact_risk": 0.9,
                                "voice_fit": 0.4,
                                "novelty": 0.3,
                                "specificity": 0.2,
                            },
                            "issues": ["too generic"],
                        }
                    ],
                }
            ),
        )
        result = critic.review_batch(_batch(), recent_drafts=[])
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "Too generic")

    def test_passthrough_critic_preserves_batch(self) -> None:
        batch = _batch()
        result = PassthroughDraftCritic().review_batch(batch, recent_drafts=[])
        self.assertTrue(result.accepted)
        self.assertIs(result.batch, batch)


if __name__ == "__main__":
    unittest.main()
