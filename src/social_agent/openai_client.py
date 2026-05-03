from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class OpenAIAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class OpenAIClient:
    api_key: str
    dry_run: bool = False

    def generate_json(self, model: str, instructions: str, prompt: str) -> dict[str, Any]:
        if self.dry_run:
            return {}
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
                {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
            ],
            "text": {"format": {"type": "json_object"}},
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _openai_api_error(exc) from exc
        return _extract_json_output(raw)

    def generate_json_with_web_search(self, model: str, instructions: str, prompt: str) -> dict[str, Any]:
        if self.dry_run:
            return {}
        payload = {
            "model": model,
            "instructions": instructions,
            "input": prompt,
            "tools": [{"type": "web_search", "search_context_size": "low"}],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _openai_api_error(exc) from exc
        parsed = _extract_json_output(raw)
        parsed.setdefault("web_sources", _extract_web_sources(raw))
        return parsed


def _openai_api_error(exc: HTTPError) -> OpenAIAPIError:
    detail = ""
    if exc.fp is not None:
        try:
            detail = exc.fp.read().decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
    message = f"OpenAI API HTTP {exc.code}: {exc.reason}"
    if detail:
        message = f"{message}: {detail}"
    return OpenAIAPIError(message)


def _extract_json_output(raw: dict[str, Any]) -> dict[str, Any]:
    text_parts: list[str] = []
    for output in raw.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
    return json.loads("".join(text_parts) or "{}")


def _extract_web_sources(raw: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for output in raw.get("output", []):
        action = (output.get("action") or {})
        for source in action.get("sources", []) or []:
            if isinstance(source, dict):
                sources.append(source)
    return sources
