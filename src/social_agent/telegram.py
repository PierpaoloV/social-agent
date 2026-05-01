from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class TelegramUpdate:
    update_id: int
    message_id: int | None
    chat_id: int | None
    text: str | None
    caption: str | None
    photo_file_id: str | None
    raw: dict[str, Any]


class TelegramClient:
    def __init__(self, bot_token: str, dry_run: bool = False) -> None:
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.dry_run = dry_run

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.dry_run:
            return {"ok": True, "result": {"method": method, "payload": payload}}
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url=f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.dry_run:
            return {"ok": True, "result": []}
        query = urlencode(params)
        with urlopen(f"{self.base_url}/{method}?{query}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_updates(self, offset: int | None = None, timeout: int = 5) -> list[TelegramUpdate]:
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        result = self._get("getUpdates", params)
        updates: list[TelegramUpdate] = []
        for item in result.get("result", []):
            message = item.get("message", {})
            photo = message.get("photo", [])
            updates.append(
                TelegramUpdate(
                    update_id=item["update_id"],
                    message_id=message.get("message_id"),
                    chat_id=(message.get("chat") or {}).get("id"),
                    text=message.get("text"),
                    caption=message.get("caption"),
                    photo_file_id=photo[-1]["file_id"] if photo else None,
                    raw=item,
                )
            )
        return updates

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def send_markdown_message(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})


def format_draft_batch_message(batch: dict[str, Any]) -> str:
    lines = [
        "*Social Agent Draft Batch*",
        f"Batch: `{batch['batch_id']}`",
        "",
    ]
    for option in batch["options"]:
        lines.extend(
            [
                f"*Option* `{option['draft_id']}`",
                f"Kind: `{option['kind']}` | Language: `{option['language']}` | Topic: `{option['topic_class']}` | Model: `{option['model_name']}`",
                f"Sources: {_format_sources(option['source_provenance'])}",
                option["text"],
                "",
            ]
        )
    lines.extend(
        [
            "Quick actions:",
            f"`/approve {batch['batch_id']} d1`",
            f"`/reject {batch['batch_id']} d1 too generic,weak hook | optional note`",
            f"`/edit {batch['batch_id']} d1 | edited text`",
            f"`/regenerate {batch['batch_id']}`",
            f"`/skip {batch['batch_id']}`",
        ]
    )
    return "\n".join(lines)


def _format_sources(provenance: list[str]) -> str:
    cleaned: list[str] = []
    for item in provenance:
        if item.startswith("inbox"):
            continue
        if item.startswith("variation_"):
            cleaned.append(item.replace("_", " "))
            continue
        cleaned.append(item)
    return ", ".join(cleaned) if cleaned else "internal source"


def parse_review_command(text: str) -> dict[str, Any] | None:
    from .reviews import parse_review_command as parse_command

    command = parse_command(text)
    return None if command is None else command.to_dict()
