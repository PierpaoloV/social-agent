from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.telegram import format_draft_batch_message


class TelegramFormattingTest(unittest.TestCase):
    def test_draft_batch_message_includes_model_name(self) -> None:
        message = format_draft_batch_message(
            {
                "batch_id": "b1234",
                "options": [
                    {
                        "draft_id": "d1",
                        "kind": "original",
                        "language": "en",
                        "topic_class": "research_reflection",
                        "model_name": "gpt-5.4-mini",
                        "source_provenance": ["telegram inbox", "inbox_123"],
                        "text": "Draft text",
                    }
                ],
            }
        )
        self.assertIn("Model: `gpt-5.4-mini`", message)


if __name__ == "__main__":
    unittest.main()
