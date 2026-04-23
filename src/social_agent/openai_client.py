from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


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
        with urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text_parts: list[str] = []
        for output in raw.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
        return json.loads("".join(text_parts) or "{}")

