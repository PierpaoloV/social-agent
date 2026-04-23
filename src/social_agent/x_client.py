from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def _percent_encode(value: str) -> str:
    return quote(value, safe="~-._")


@dataclass(slots=True)
class XClient:
    api_key: str | None
    api_secret: str | None
    access_token: str | None
    access_token_secret: str | None
    bearer_token: str | None = None
    dry_run: bool = False

    def _oauth_headers(self, method: str, url: str, extra_params: dict[str, str]) -> str:
        if not all([self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
            raise ValueError("X write credentials are incomplete")
        oauth_params = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": secrets.token_hex(8),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }
        signing_params = {**oauth_params, **extra_params}
        encoded_pairs = [( _percent_encode(k), _percent_encode(v)) for k, v in signing_params.items()]
        parameter_string = "&".join(f"{k}={v}" for k, v in sorted(encoded_pairs))
        base_string = "&".join([method.upper(), _percent_encode(url), _percent_encode(parameter_string)])
        signing_key = f"{_percent_encode(self.api_secret)}&{_percent_encode(self.access_token_secret)}"
        signature = base64.b64encode(hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")
        oauth_params["oauth_signature"] = signature
        header_params = ", ".join(f'{k}="{_percent_encode(v)}"' for k, v in sorted(oauth_params.items()))
        return f"OAuth {header_params}"

    def create_post(self, text: str, reply_to_id: str | None = None, quote_post_id: str | None = None) -> dict[str, Any]:
        if self.dry_run:
            return {"data": {"id": f"dry_{int(time.time())}", "text": text}}
        url = "https://api.twitter.com/2/tweets"
        payload: dict[str, Any] = {"text": text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        if quote_post_id:
            payload["quote_tweet_id"] = quote_post_id
        header = self._oauth_headers("POST", url, {})
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": header, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def search_recent_posts(self, query: str, max_results: int = 10) -> dict[str, Any]:
        if self.dry_run:
            return {"data": []}
        if not self.bearer_token:
            raise ValueError("X bearer token is required for read endpoints")
        params = urlencode({"query": query, "max_results": max_results, "tweet.fields": "author_id,created_at"})
        request = Request(
            f"https://api.twitter.com/2/tweets/search/recent?{params}",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            method="GET",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

