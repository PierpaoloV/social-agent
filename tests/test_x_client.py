from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.x_client import XAPIError, XClient


class XClientTest(unittest.TestCase):
    def test_create_post_surfaces_structured_x_error_details(self) -> None:
        error = HTTPError(
            url="https://api.twitter.com/2/tweets",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(
                b'{"title":"Client Forbidden","detail":"This request must be made using an approved developer account.","reason":"client-not-enrolled","type":"https://api.x.com/2/problems/client-forbidden"}'
            ),
        )
        client = XClient(
            api_key="api-key",
            api_secret="api-secret",
            access_token="access-token",
            access_token_secret="access-secret",
        )

        with patch("social_agent.x_client.urlopen", side_effect=error):
            with self.assertRaises(XAPIError) as ctx:
                client.create_post("hello world")

        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(ctx.exception.problem_reason, "client-not-enrolled")
        self.assertEqual(ctx.exception.title, "Client Forbidden")
        self.assertIn("approved developer account", ctx.exception.detail or "")

    def test_recent_search_uses_supported_minimum_result_count(self) -> None:
        response = Mock()
        response.read.return_value = b'{"data":[]}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)

        with patch("social_agent.x_client.urlopen", return_value=response) as urlopen:
            client = XClient(
                api_key=None,
                api_secret=None,
                access_token=None,
                access_token_secret=None,
                bearer_token="token",
            )
            client.search_recent_posts("agent engineering", max_results=2)

        request = urlopen.call_args.args[0]
        self.assertIn("max_results=10", request.full_url)


if __name__ == "__main__":
    unittest.main()
