from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from social_agent.x_client import XClient


class XClientTest(unittest.TestCase):
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
