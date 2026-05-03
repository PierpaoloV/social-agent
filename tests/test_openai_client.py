from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.openai_client import OpenAIAPIError, OpenAIClient


class OpenAIClientTest(unittest.TestCase):
    def test_web_search_uses_simple_responses_payload(self) -> None:
        captured_payloads: list[dict[str, object]] = []

        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"output": [{"content": [{"type": "output_text", "text": "{\"candidates\": []}"}]}]}).encode("utf-8")

        def fake_urlopen(request: object, timeout: int) -> FakeResponse:
            captured_payloads.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        client = OpenAIClient(api_key="test-key")
        with patch("social_agent.openai_client.urlopen", side_effect=fake_urlopen):
            result = client.generate_json_with_web_search("gpt-5.4-mini", "Return JSON.", "{\"query\": \"agent evaluation\"}")
        self.assertEqual(result["candidates"], [])
        payload = captured_payloads[0]
        self.assertEqual(payload["instructions"], "Return JSON.")
        self.assertEqual(payload["input"], "{\"query\": \"agent evaluation\"}")
        self.assertEqual(payload["tools"], [{"type": "web_search", "search_context_size": "low"}])
        self.assertNotIn("text", payload)

    def test_web_search_error_includes_response_body(self) -> None:
        error = HTTPError(
            url="https://api.openai.com/v1/responses",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"Unsupported parameter"}}'),
        )
        client = OpenAIClient(api_key="test-key")
        with patch("social_agent.openai_client.urlopen", side_effect=error):
            with self.assertRaises(OpenAIAPIError) as raised:
                client.generate_json_with_web_search("gpt-5.4-mini", "Return JSON.", "{}")
        self.assertIn("OpenAI API HTTP 400", str(raised.exception))
        self.assertIn("Unsupported parameter", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
