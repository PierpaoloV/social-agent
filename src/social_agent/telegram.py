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
    if not text or not text.startswith("/"):
        return None
    command, _, remainder = text.partition(" ")
    command_name = command.lstrip("/").strip().lower()
    if command_name not in {"approve", "reject", "edit", "regenerate", "skip"}:
        return None
    if command_name in {"regenerate", "skip"}:
        return {"action": command_name, "batch_id": remainder.strip()}
    if command_name == "approve":
        parts = remainder.split()
        if len(parts) < 2:
            raise ValueError("approve command requires batch_id and draft_id")
        return {"action": command_name, "batch_id": parts[0], "draft_id": parts[1]}
    if command_name == "reject":
        head, _, note = remainder.partition("|")
        parts = head.strip().split(maxsplit=2)
        if len(parts) < 3:
            raise ValueError("reject command requires batch_id, draft_id, and tags")
        tags = [tag.strip() for tag in parts[2].split(",") if tag.strip()]
        return {"action": command_name, "batch_id": parts[0], "draft_id": parts[1], "tags": tags, "note": note.strip() or None}
    head, _, edited_text = remainder.partition("|")
    parts = head.strip().split()
    if len(parts) < 2 or not edited_text.strip():
        raise ValueError("edit command requires batch_id, draft_id, and edited text")
    return {"action": command_name, "batch_id": parts[0], "draft_id": parts[1], "edited_text": edited_text.strip()}
