from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.github_sources import _looks_like_milestone
from social_agent.telegram import parse_review_command


class GitHubAndTelegramTest(unittest.TestCase):
    def test_milestone_detector_accepts_feature_work(self) -> None:
        self.assertTrue(_looks_like_milestone("feat: add demo workflow for agent inbox"))

    def test_milestone_detector_rejects_dependency_churn(self) -> None:
        self.assertFalse(_looks_like_milestone("chore: bump dependency versions"))

    def test_parse_reject_command_supports_tags_and_optional_note(self) -> None:
        parsed = parse_review_command("/reject batch123 draft456 too generic,weak hook | feels flat")
        self.assertEqual(parsed["action"], "reject")
        self.assertEqual(parsed["batch_id"], "batch123")
        self.assertEqual(parsed["draft_id"], "draft456")
        self.assertEqual(parsed["tags"], ["too generic", "weak hook"])
        self.assertEqual(parsed["note"], "feels flat")

    def test_parse_edit_command_requires_pipe_payload(self) -> None:
        parsed = parse_review_command("/edit batch123 draft456 | rewritten text")
        self.assertEqual(parsed["action"], "edit")
        self.assertEqual(parsed["edited_text"], "rewritten text")


if __name__ == "__main__":
    unittest.main()
