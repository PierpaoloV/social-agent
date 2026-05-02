from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.config import SeedsConfig, load_profile_config, load_seeds_config
from social_agent.engagement import build_follow_suggestions
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

    def test_seed_config_allows_must_follow_without_starter_candidates(self) -> None:
        seeds = load_seeds_config()
        self.assertEqual(seeds.starter_candidates, ())
        self.assertGreaterEqual(len(seeds.must_follow), seeds.weekly_limit)

    def test_follow_suggestions_use_must_follow_only(self) -> None:
        seeds = SeedsConfig(
            must_follow=(
                {"handle": "must_one", "category": "research", "reason": "Must follow."},
                {"handle": "must_two", "category": "builder", "reason": "Must follow."},
            ),
            starter_candidates=({"handle": "starter_one", "category": "builder", "reason": "Starter."},),
            keywords=(),
            follow_scoring={
                "relevance_weight": 0.45,
                "signal_weight": 0.35,
                "style_fit_weight": 0.15,
                "redundancy_penalty": 0.05,
            },
            weekly_limit=3,
        )
        handles = [suggestion.handle for suggestion in build_follow_suggestions(seeds)]
        self.assertEqual(handles, ["must_one", "must_two"])

    def test_profile_loads_editorial_context_for_prompts(self) -> None:
        profile = load_profile_config()
        context = profile.editorial_context
        self.assertIn("inspectable", " ".join(context["point_of_view"]))
        self.assertIn("viral LinkedIn cadence", context["banned_style"])
        self.assertEqual(context["content_pillars"][0]["id"], "medical_ai_and_pathology")
        self.assertEqual(context["post_archetypes"][0]["id"], "lesson")

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
