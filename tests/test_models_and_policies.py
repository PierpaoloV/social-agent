from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.config import load_profile_config, load_seeds_config
from social_agent.models import DraftBatch, DraftKind, DraftOption, make_id, utc_now_iso
from social_agent.policies import external_query_budget, is_language_allowed, is_thread_allowed


class ModelsAndPoliciesTest(unittest.TestCase):
    def test_draft_batch_rejects_more_than_one_regeneration(self) -> None:
        batch = DraftBatch(
            batch_id=make_id("batch"),
            created_at=utc_now_iso(),
            scheduled_for=utc_now_iso(),
            cycle_key="2026-04-23",
            regenerate_count=2,
        )
        with self.assertRaises(ValueError):
            batch.validate()

    def test_language_policy_allows_spanish_only_for_replies(self) -> None:
        profile = load_profile_config()
        self.assertTrue(is_language_allowed(profile, DraftKind.REPLY.value, "es"))
        self.assertFalse(is_language_allowed(profile, DraftKind.ORIGINAL.value, "es"))

    def test_thread_policy_limits_topic_class_and_length(self) -> None:
        profile = load_profile_config()
        self.assertTrue(is_thread_allowed(profile, "technical_breakdown", ["a", "b"]))
        self.assertFalse(is_thread_allowed(profile, "general", ["a", "b"]))
        self.assertFalse(is_thread_allowed(profile, "technical_breakdown", ["a", "b", "c", "d"]))

    def test_external_query_budget_caps_keywords_under_strict_budget(self) -> None:
        seeds = load_seeds_config()
        self.assertEqual(external_query_budget(seeds, strict_read_budget=True), seeds.keywords[:3])

    def test_draft_option_validation_enforces_supported_language(self) -> None:
        option = DraftOption(
            draft_id=make_id("draft"),
            batch_id=make_id("batch"),
            kind=DraftKind.ORIGINAL.value,
            topic_class="project_milestone",
            language="fr",
            text="hello",
            source_provenance=["test"],
            created_at=utc_now_iso(),
            model_name="test",
        )
        with self.assertRaises(ValueError):
            option.validate()


if __name__ == "__main__":
    unittest.main()
