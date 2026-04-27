from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.cli import main
from social_agent.state_store import JsonStateStore


class CliErrorTrackingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name) / "private_state"
        self.env_patch = patch.dict(
            os.environ,
            {
                "SOCIAL_AGENT_STATE_DIR": str(self.state_dir),
                "SOCIAL_AGENT_DRY_RUN": "true",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_cli_persists_uncaught_command_errors(self) -> None:
        stdout = io.StringIO()
        with patch("social_agent.cli.process_telegram_updates", side_effect=RuntimeError("boom")):
            with redirect_stdout(stdout):
                exit_code = main(["process-telegram"])
        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["command"], "process-telegram")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertEqual(payload["message"], "boom")
        self.assertEqual(payload["status"], "error")
        store = JsonStateStore(self.state_dir)
        errors = store.list("errors")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["command"], "process-telegram")
        latest_error = store.get("runtime", "latest_command_error")
        self.assertEqual(latest_error["error_id"], errors[0]["error_id"])

    def test_cli_keeps_successful_command_output(self) -> None:
        stdout = io.StringIO()
        with patch("social_agent.cli.doctor", return_value={"status": "ok"}):
            with redirect_stdout(stdout):
                exit_code = main(["doctor"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload, {"status": "ok"})
