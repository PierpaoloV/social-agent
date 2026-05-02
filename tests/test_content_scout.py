from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.config import load_policy
from social_agent.content_scout import WebContentScout, derive_safe_query, parse_scout_candidates
from social_agent.models import IdeaCandidate, SourceType


class FakeScoutClient:
    def generate_json_with_web_search(self, model: str, instructions: str, prompt: str) -> dict:
        return {"candidates": []}


class ContentScoutTest(unittest.TestCase):
    def test_build_queries_uses_topics_and_safe_terms_from_fresh_ideas(self) -> None:
        policy = load_policy()
        scout = WebContentScout(policy=policy, openai_client=FakeScoutClient())
        idea = IdeaCandidate(
            idea_id="idea_1",
            title="Private note from message 12345 about agent workflow debugging",
            summary="chat_id 12345 photo-file private demo about agent workflow evaluation",
            source_type=SourceType.TELEGRAM.value,
            source_ids=["inbox_1"],
            topic_class="technical_breakdown",
            novelty_score=0.8,
            authenticity_score=0.9,
            relevance_score=0.8,
            source_weight=1.0,
            metadata={"chat_id": 12345, "message_id": 99, "photo_file_id": "photo-file"},
        )
        queries = scout.build_queries([idea])
        joined = " ".join(queries).lower()
        self.assertIn("agent engineering", joined)
        self.assertTrue(any("agent" in query and "workflow" in query for query in queries))
        self.assertNotIn("12345", joined)
        self.assertNotIn("photo-file", joined)
        self.assertNotIn("private note", joined)

    def test_derive_safe_query_filters_private_words(self) -> None:
        idea = IdeaCandidate(
            idea_id="idea_1",
            title="A private hospital project about workflow evaluation",
            summary="message 12345 with personal details and agent tooling notes",
            source_type=SourceType.TELEGRAM.value,
            source_ids=["inbox_1"],
            topic_class="technical_breakdown",
            novelty_score=0.8,
            authenticity_score=0.9,
            relevance_score=0.8,
            source_weight=1.0,
        )
        query = derive_safe_query(idea)
        self.assertEqual(query, "workflow evaluation agent tooling")

    def test_parse_scout_candidates_preserves_sources_and_caps_count(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "Agent evaluation lessons",
                    "summary": "A concrete evaluation lesson from public agent tooling.",
                    "topic_class": "technical_breakdown",
                    "source_references": [
                        {"url": "https://example.com/a", "title": "A", "summary": "First source"},
                        {"url": "https://example.com/b", "title": "B", "summary": "Second source"},
                    ],
                    "source_summary": "Two public sources discuss evaluation.",
                    "public_safety_note": "No private details.",
                }
            ]
        }
        candidates = parse_scout_candidates(response, "agent evaluation", 0.4, max_sources_per_candidate=1)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_type, SourceType.EXTERNAL.value)
        self.assertEqual(candidates[0].metadata["source_references"][0]["url"], "https://example.com/a")
        self.assertEqual(len(candidates[0].metadata["source_references"]), 1)


if __name__ == "__main__":
    unittest.main()
