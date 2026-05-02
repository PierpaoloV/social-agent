from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.models import DraftKind
from social_agent.state_store import JsonStateStore
from social_agent.telegram import TelegramUpdate
from social_agent.workflows import generate_weekly_outputs, process_telegram_updates, publish_queued, run_draft_cycle


class WorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name) / "private_state"
        self.env_patch = patch.dict(
            os.environ,
            {
                "SOCIAL_AGENT_STATE_DIR": str(self.state_dir),
                "SOCIAL_AGENT_DRY_RUN": "true",
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_process_telegram_captures_private_inbox_item(self) -> None:
        update = TelegramUpdate(
            update_id=1,
            message_id=11,
            chat_id=12345,
            text="I shipped a research workflow demo",
            caption=None,
            photo_file_id="photo-file",
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[update]):
            result = process_telegram_updates()
        self.assertEqual(result["inbox_count"], 1)
        store = JsonStateStore(self.state_dir)
        inbox_items = store.list("inbox")
        self.assertEqual(len(inbox_items), 1)
        self.assertTrue(str(self.state_dir) in str((self.state_dir / "inbox")))

    def test_run_draft_cycle_turns_phd_note_into_batch(self) -> None:
        update = TelegramUpdate(
            update_id=2,
            message_id=12,
            chat_id=12345,
            text="I shipped a research workflow demo and I want to reflect on what it taught me about systems.",
            caption=None,
            photo_file_id="photo-file",
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[update]):
            process_telegram_updates()
        result = run_draft_cycle(force=True)
        self.assertEqual(result["status"], "ok")
        store = JsonStateStore(self.state_dir)
        batches = store.list("drafts")
        self.assertEqual(len(batches), 1)
        self.assertTrue(batches[0]["batch_id"].startswith("b"))
        self.assertEqual([option["draft_id"] for option in batches[0]["options"]], ["d1", "d2", "d3"])
        self.assertEqual(len(batches[0]["options"]), 3)
        texts = [option["text"] for option in batches[0]["options"]]
        self.assertTrue(any("research" in text or "workflow" in text for text in texts))

    def test_run_draft_cycle_does_not_redraft_same_github_source_twice(self) -> None:
        first = run_draft_cycle(force=True)
        second = run_draft_cycle(force=True)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(second["reason"], "no fresh ideas")
        store = JsonStateStore(self.state_dir)
        self.assertEqual(len(store.list("drafts")), 1)

    def test_model_single_post_kind_is_normalized_to_original(self) -> None:
        update = TelegramUpdate(
            update_id=20,
            message_id=120,
            chat_id=12345,
            text="A note about shipping a practical AI workflow",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[update]):
            process_telegram_updates()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch(
                "social_agent.openai_client.OpenAIClient.generate_json",
                return_value={
                    "drafts": [
                        {
                            "kind": "single_post",
                            "language": "en",
                            "topic_class": "project_milestone",
                            "text": "Shipping practical AI systems is mostly about removing friction.",
                            "thread_posts": [],
                        }
                    ]
                },
            ):
                result = run_draft_cycle(force=True)
        self.assertEqual(result["status"], "ok")
        store = JsonStateStore(self.state_dir)
        batch = store.list("drafts")[0]
        self.assertEqual(batch["options"][0]["kind"], DraftKind.ORIGINAL.value)

    def test_run_draft_cycle_passes_recent_outbound_drafts_into_prompt(self) -> None:
        prompt_payloads: list[dict[str, object]] = []
        instructions_payloads: list[str] = []

        def fake_generate_json(model: str, instructions: str, prompt: str) -> dict[str, object]:
            instructions_payloads.append(instructions)
            prompt_payloads.append(json.loads(prompt))
            return {
                "drafts": [
                    {
                        "kind": "original",
                        "language": "en",
                        "topic_class": "project_milestone",
                        "text": f"Fresh framing #{len(prompt_payloads)}",
                        "thread_posts": [],
                    }
                ]
            }

        first_update = TelegramUpdate(
            update_id=30,
            message_id=130,
            chat_id=12345,
            text="A note about shipping a practical AI workflow",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        second_update = TelegramUpdate(
            update_id=31,
            message_id=131,
            chat_id=12345,
            text="Another note about evaluating agent workflows in practice",
            caption=None,
            photo_file_id=None,
            raw={},
        )

        with patch.dict(os.environ, {"SOCIAL_AGENT_DRY_RUN": "false", "OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("social_agent.workflows.GitHubMilestoneDetector.collect_candidates", return_value=[]):
                with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[first_update]):
                    process_telegram_updates()
                with patch("social_agent.openai_client.OpenAIClient.generate_json", side_effect=fake_generate_json):
                    with patch("social_agent.workflows.TelegramClient.send_markdown_message"):
                        run_draft_cycle(force=True)
                with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[second_update]):
                    process_telegram_updates()
                with patch("social_agent.openai_client.OpenAIClient.generate_json", side_effect=fake_generate_json):
                    with patch("social_agent.workflows.TelegramClient.send_markdown_message"):
                        run_draft_cycle(force=True)

        self.assertEqual(len(prompt_payloads), 2)
        self.assertEqual(prompt_payloads[0]["recent_drafts"], [])
        self.assertIn("Fresh framing #1", prompt_payloads[1]["recent_drafts"])
        self.assertIn("do not invent events", instructions_payloads[0])
        self.assertIn("public-safe technical lesson", instructions_payloads[0])
        self.assertIn("tone_rules", prompt_payloads[0])
        self.assertIn("forbidden_topics", prompt_payloads[0])
        store = JsonStateStore(self.state_dir)
        draft_batch_messages = [item for item in store.list("outbox") if item["kind"] == "draft_batch"]
        self.assertEqual(len(draft_batch_messages), 2)

    def test_edit_before_approve_is_stored_for_learning(self) -> None:
        update = TelegramUpdate(
            update_id=3,
            message_id=13,
            chat_id=12345,
            text="A useful lesson from building an agent pipeline",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[update]):
            process_telegram_updates()
        run_draft_cycle(force=True)
        store = JsonStateStore(self.state_dir)
        batch = store.list("drafts")[0]
        draft_id = batch["options"][0]["draft_id"]
        edit_update = TelegramUpdate(
            update_id=4,
            message_id=14,
            chat_id=12345,
            text=f"/edit {batch['batch_id']} {draft_id} | rewritten by hand",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[edit_update]):
            process_telegram_updates()
        actions = store.list("approvals")
        edit_actions = [item for item in actions if item["action_type"] == "edit"]
        self.assertEqual(len(edit_actions), 1)
        self.assertEqual(edit_actions[0]["edited_text_after"], "rewritten by hand")

    def test_regenerate_is_limited_to_one_time(self) -> None:
        update = TelegramUpdate(
            update_id=5,
            message_id=15,
            chat_id=12345,
            text="An update about an agent workflow release",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[update]):
            process_telegram_updates()
        run_draft_cycle(force=True)
        store = JsonStateStore(self.state_dir)
        batch = store.list("drafts")[0]
        regen_update = TelegramUpdate(
            update_id=6,
            message_id=16,
            chat_id=12345,
            text=f"/regenerate {batch['batch_id']}",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[regen_update]):
            process_telegram_updates()
        regenerated = store.get("drafts", batch["batch_id"])
        self.assertEqual(regenerated["regenerate_count"], 1)
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[regen_update]):
            result = process_telegram_updates()
        self.assertTrue(any("already regenerated once" in error for error in result["action_errors"]))

    def test_process_telegram_persists_offset_when_review_action_crashes(self) -> None:
        store = JsonStateStore(self.state_dir)
        batch = {
            "batch_id": "batch_reply",
            "created_at": "2026-04-23T00:00:00+00:00",
            "scheduled_for": "2026-04-23T11:00",
            "cycle_key": "2026-04-23",
            "regenerate_count": 0,
            "status": "drafted",
            "idea_ids": [],
            "options": [
                {
                    "draft_id": "draft_reply",
                    "batch_id": "batch_reply",
                    "kind": DraftKind.REPLY.value,
                    "topic_class": "technical_breakdown",
                    "language": "en",
                    "text": "Timely reply",
                    "source_provenance": ["test"],
                    "created_at": "2026-04-23T00:00:00+00:00",
                    "model_name": "test",
                    "metadata": {"reply_to_id": "123"},
                }
            ],
        }
        store.put("drafts", "batch_reply", batch)
        approval_update = TelegramUpdate(
            update_id=99,
            message_id=17,
            chat_id=12345,
            text="/approve batch_reply draft_reply",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[approval_update]):
            with patch("social_agent.workflows.XClient.create_post", side_effect=RuntimeError("x unavailable")):
                result = process_telegram_updates()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action_count"], 0)
        self.assertTrue(any("Update 99 failed: x unavailable" in error for error in result["action_errors"]))
        runtime_state = store.get("runtime", "telegram_updates")
        self.assertEqual(runtime_state["last_update_id"], 99)

    def test_process_telegram_handles_get_updates_failure(self) -> None:
        with patch("social_agent.workflows.TelegramClient.get_updates", side_effect=RuntimeError("telegram unavailable")):
            result = process_telegram_updates()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "telegram getUpdates failed")
        self.assertEqual(result["error"], "telegram unavailable")

    def test_weekly_outputs_generate_follow_digest_with_five_items(self) -> None:
        result = generate_weekly_outputs(force=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["follow_count"], 5)

    def test_weekly_outputs_do_not_fail_when_x_read_access_is_paywalled(self) -> None:
        with patch(
            "social_agent.workflows.XClient.search_recent_posts",
            side_effect=HTTPError(
                url="https://api.twitter.com/2/tweets/search/recent",
                code=402,
                msg="Payment Required",
                hdrs=None,
                fp=None,
            ),
        ):
            result = generate_weekly_outputs(force=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["engagement_count"], 0)

    def test_weekly_outputs_do_not_fail_when_x_search_request_is_rejected(self) -> None:
        with patch(
            "social_agent.workflows.XClient.search_recent_posts",
            side_effect=HTTPError(
                url="https://api.twitter.com/2/tweets/search/recent",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            ),
        ):
            result = generate_weekly_outputs(force=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["engagement_count"], 0)

    def test_approved_reply_publishes_immediately(self) -> None:
        store = JsonStateStore(self.state_dir)
        batch = {
            "batch_id": "batch_reply",
            "created_at": "2026-04-23T00:00:00+00:00",
            "scheduled_for": "2026-04-23T11:00",
            "cycle_key": "2026-04-23",
            "regenerate_count": 0,
            "status": "drafted",
            "idea_ids": [],
            "options": [
                {
                    "draft_id": "draft_reply",
                    "batch_id": "batch_reply",
                    "kind": DraftKind.REPLY.value,
                    "topic_class": "technical_breakdown",
                    "language": "en",
                    "text": "Timely reply",
                    "source_provenance": ["test"],
                    "created_at": "2026-04-23T00:00:00+00:00",
                    "model_name": "test",
                    "metadata": {"reply_to_id": "123"},
                }
            ],
        }
        store.put("drafts", "batch_reply", batch)
        approval_update = TelegramUpdate(
            update_id=7,
            message_id=17,
            chat_id=12345,
            text="/approve batch_reply draft_reply",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[approval_update]):
            process_telegram_updates()
        publications = store.list("publications")
        self.assertEqual(publications[0]["status"], "published")

    def test_publish_queued_promotes_original_post(self) -> None:
        store = JsonStateStore(self.state_dir)
        store.put(
            "publications",
            "queued_1",
            {
                "publication_id": "queued_1",
                "draft_id": "draft_original",
                "kind": DraftKind.ORIGINAL.value,
                "text": "Queued post",
                "published_at": "",
                "external_post_id": None,
                "status": "queued",
                "metadata": {},
            },
        )
        with patch("social_agent.workflows.is_publish_window_open", return_value=True):
            result = publish_queued()
        self.assertEqual(result["published"], 1)
        refreshed = store.get("publications", "queued_1")
        self.assertEqual(refreshed["status"], "published")

    def test_publish_queued_records_x_payment_required_failure(self) -> None:
        store = JsonStateStore(self.state_dir)
        store.put(
            "publications",
            "queued_402",
            {
                "publication_id": "queued_402",
                "draft_id": "draft_original",
                "kind": DraftKind.ORIGINAL.value,
                "text": "Queued post",
                "published_at": "",
                "external_post_id": None,
                "status": "queued",
                "metadata": {},
            },
        )
        with patch(
            "social_agent.workflows.XClient.create_post",
            side_effect=HTTPError(
                url="https://api.twitter.com/2/tweets",
                code=402,
                msg="Payment Required",
                hdrs=None,
                fp=None,
            ),
        ):
            with patch("social_agent.workflows.is_publish_window_open", return_value=True):
                result = publish_queued()
        self.assertEqual(result["published"], 0)
        self.assertEqual(result["failed"], 1)
        refreshed = store.get("publications", "queued_402")
        self.assertEqual(refreshed["status"], "failed")
        self.assertEqual(refreshed["metadata"]["publish_error"]["code"], 402)

    def test_publish_queued_skips_outside_window(self) -> None:
        store = JsonStateStore(self.state_dir)
        store.put(
            "publications",
            "queued_late",
            {
                "publication_id": "queued_late",
                "draft_id": "draft_original",
                "kind": DraftKind.ORIGINAL.value,
                "text": "Queued post",
                "published_at": "",
                "external_post_id": None,
                "status": "queued",
                "metadata": {},
            },
        )
        with patch("social_agent.workflows.is_publish_window_open", return_value=False):
            result = publish_queued()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "outside publish window")
        refreshed = store.get("publications", "queued_late")
        self.assertEqual(refreshed["status"], "queued")

    def test_publish_queued_force_bypasses_window(self) -> None:
        store = JsonStateStore(self.state_dir)
        store.put(
            "publications",
            "queued_force",
            {
                "publication_id": "queued_force",
                "draft_id": "draft_original",
                "kind": DraftKind.ORIGINAL.value,
                "text": "Queued post",
                "published_at": "",
                "external_post_id": None,
                "status": "queued",
                "metadata": {},
            },
        )
        with patch("social_agent.workflows.is_publish_window_open", return_value=False):
            result = publish_queued(force=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["published"], 1)
        refreshed = store.get("publications", "queued_force")
        self.assertEqual(refreshed["status"], "published")

    def test_weekly_digest_message_includes_actionable_engagement_context(self) -> None:
        with patch(
            "social_agent.workflows.XClient.search_recent_posts",
            return_value={
                "data": [{"id": "111", "author_id": "42"}],
                "includes": {"users": [{"id": "42", "username": "agentsmith"}]},
            },
        ):
            with patch("social_agent.workflows.TelegramClient.send_message") as send_message:
                result = generate_weekly_outputs(force=True)
        self.assertEqual(result["engagement_count"], 3)
        digest_text = send_message.call_args.args[1]
        self.assertIn("reply to @agentsmith", digest_text)
        self.assertIn("Post: https://x.com/agentsmith/status/111", digest_text)
        self.assertIn("Use as a reply:", digest_text)
        self.assertIn("Use as a quote-post:", digest_text)

    def test_unknown_batch_review_command_does_not_crash_processing(self) -> None:
        approval_update = TelegramUpdate(
            update_id=8,
            message_id=18,
            chat_id=12345,
            text="/approve b9999 d1",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[approval_update]):
            result = process_telegram_updates()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action_count"], 0)
        self.assertTrue(any("Unknown batch_id" in error for error in result["action_errors"]))

    def test_malformed_review_command_does_not_crash_processing(self) -> None:
        malformed_update = TelegramUpdate(
            update_id=9,
            message_id=19,
            chat_id=12345,
            text="/approve",
            caption=None,
            photo_file_id=None,
            raw={},
        )
        with patch("social_agent.workflows.TelegramClient.get_updates", return_value=[malformed_update]):
            result = process_telegram_updates()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action_count"], 0)
        self.assertTrue(any("approve command requires batch_id and draft_id" in error for error in result["action_errors"]))


if __name__ == "__main__":
    unittest.main()
