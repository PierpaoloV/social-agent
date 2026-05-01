from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import ActionType, ApprovalAction, DraftKind, InboxItem, make_id, utc_now_iso
from .telegram import TelegramUpdate


@dataclass(slots=True)
class ReviewCommand:
    action: str
    batch_id: str
    draft_id: str | None = None
    tags: list[str] = field(default_factory=list)
    note: str | None = None
    edited_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": self.action, "batch_id": self.batch_id}
        if self.draft_id is not None:
            payload["draft_id"] = self.draft_id
        if self.tags:
            payload["tags"] = list(self.tags)
        if self.note:
            payload["note"] = self.note
        if self.edited_text:
            payload["edited_text"] = self.edited_text
        return payload


def parse_review_command(text: str) -> ReviewCommand | None:
    if not text or not text.startswith("/"):
        return None
    command, _, remainder = text.partition(" ")
    command_name = command.lstrip("/").strip().lower()
    if command_name not in {"approve", "reject", "edit", "regenerate", "skip"}:
        return None
    if command_name in {"regenerate", "skip"}:
        return ReviewCommand(action=command_name, batch_id=remainder.strip())
    if command_name == "approve":
        parts = remainder.split()
        if len(parts) < 2:
            raise ValueError("approve command requires batch_id and draft_id")
        return ReviewCommand(action=command_name, batch_id=parts[0], draft_id=parts[1])
    if command_name == "reject":
        head, _, note = remainder.partition("|")
        parts = head.strip().split(maxsplit=2)
        if len(parts) < 3:
            raise ValueError("reject command requires batch_id, draft_id, and tags")
        tags = [tag.strip() for tag in parts[2].split(",") if tag.strip()]
        return ReviewCommand(action=command_name, batch_id=parts[0], draft_id=parts[1], tags=tags, note=note.strip() or None)
    head, _, edited_text = remainder.partition("|")
    parts = head.strip().split()
    if len(parts) < 2 or not edited_text.strip():
        raise ValueError("edit command requires batch_id, draft_id, and edited text")
    return ReviewCommand(action=command_name, batch_id=parts[0], draft_id=parts[1], edited_text=edited_text.strip())


@dataclass(slots=True)
class ReviewLifecycle:
    state: object
    notifier: object
    publication_manager: object
    fixed_feedback_tags: tuple[str, ...]
    regenerate_batch: Callable[[], None]

    def apply(self, command: ReviewCommand) -> None:
        batch = self.state.drafts.get(command.batch_id)
        if batch is None:
            raise ValueError(f"Unknown batch_id: {command.batch_id}")
        if command.action == ActionType.REGENERATE.value:
            batch.regenerate()
            self.state.drafts.save(batch)
            self.notifier.send(f"Regenerating `{batch.batch_id}` now. A fresh batch will arrive in this chat.")
            self.regenerate_batch()
            self.state.approvals.save(
                ApprovalAction(
                    action_id=make_id("action"),
                    action_type=ActionType.REGENERATE.value,
                    target_batch_id=batch.batch_id,
                    draft_id=None,
                    created_at=utc_now_iso(),
                )
            )
            return
        if command.action == ActionType.SKIP.value:
            batch.mark_skipped()
            self.state.drafts.save(batch)
            self.notifier.send(f"Skipped batch `{batch.batch_id}`.")
            self.state.approvals.save(
                ApprovalAction(
                    action_id=make_id("action"),
                    action_type=ActionType.SKIP.value,
                    target_batch_id=batch.batch_id,
                    draft_id=None,
                    created_at=utc_now_iso(),
                )
            )
            return
        if command.draft_id is None:
            raise ValueError("Draft-level review command requires draft_id")
        if command.action == ActionType.APPROVE.value:
            option = batch.mark_approved(command.draft_id)
            publication_status = self.publication_manager.queue_or_publish(option)
            self.state.drafts.save(batch)
            if publication_status == "published":
                self.notifier.send(f"Approved `{option.draft_id}` from `{batch.batch_id}` and published it immediately.")
            else:
                self.notifier.send(f"Approved `{option.draft_id}` from `{batch.batch_id}`. It is queued for the next publish window.")
            self.state.approvals.save(
                ApprovalAction(
                    action_id=make_id("action"),
                    action_type=ActionType.APPROVE.value,
                    target_batch_id=batch.batch_id,
                    draft_id=option.draft_id,
                    created_at=utc_now_iso(),
                    publish_now=option.kind == DraftKind.REPLY.value,
                )
            )
            return
        if command.action == ActionType.REJECT.value:
            option = batch.find_option(command.draft_id)
            self.notifier.send(f"Logged rejection for `{option.draft_id}` from `{batch.batch_id}`.")
            self.state.approvals.save(
                ApprovalAction(
                    action_id=make_id("action"),
                    action_type=ActionType.REJECT.value,
                    target_batch_id=batch.batch_id,
                    draft_id=option.draft_id,
                    created_at=utc_now_iso(),
                    feedback_tags=[tag for tag in command.tags if tag in self.fixed_feedback_tags],
                    note=command.note,
                )
            )
            return
        option, before = batch.edit_option(command.draft_id, command.edited_text or "")
        self.state.drafts.save(batch)
        self.notifier.send(f"Saved your edit for `{option.draft_id}` in `{batch.batch_id}`.")
        self.state.approvals.save(
            ApprovalAction(
                action_id=make_id("action"),
                action_type=ActionType.EDIT.value,
                target_batch_id=batch.batch_id,
                draft_id=option.draft_id,
                created_at=utc_now_iso(),
                edited_text_before=before,
                edited_text_after=command.edited_text,
            )
        )


@dataclass(slots=True)
class TelegramReviewProcessor:
    telegram_client: object
    state: object
    notifier: object
    lifecycle: ReviewLifecycle

    def process_updates(self) -> dict[str, Any]:
        state = self.state.runtime.get("telegram_updates", {"last_update_id": 0}) or {"last_update_id": 0}
        try:
            updates = self.telegram_client.get_updates(offset=state["last_update_id"] + 1)
        except Exception as exc:
            return {"status": "error", "reason": "telegram getUpdates failed", "error": str(exc)}
        inbox_count = 0
        action_count = 0
        action_errors: list[str] = []
        for update in updates:
            state["last_update_id"] = max(state["last_update_id"], update.update_id)
            try:
                message_text = update.text or update.caption or ""
                try:
                    command = parse_review_command(message_text) if message_text else None
                except ValueError as exc:
                    action_errors.append(str(exc))
                    self.notifier.send(f"Review command skipped: {exc}")
                    continue
                if command:
                    try:
                        self.lifecycle.apply(command)
                        action_count += 1
                    except ValueError as exc:
                        action_errors.append(str(exc))
                        self.notifier.send(f"Review command skipped: {exc}")
                    except Exception as exc:
                        action_errors.append(f"Update {update.update_id} failed: {exc}")
                        self.notifier.send(f"Review command failed for update {update.update_id}: {exc}")
                    continue
                if not message_text and not update.photo_file_id:
                    continue
                self.state.inbox.save(_inbox_item_from_update(update, message_text))
                inbox_count += 1
            finally:
                self.state.runtime.write("telegram_updates", state)
        return {"status": "ok", "inbox_count": inbox_count, "action_count": action_count, "action_errors": action_errors}


def _inbox_item_from_update(update: TelegramUpdate, message_text: str) -> InboxItem:
    return InboxItem(
        item_id=make_id("inbox"),
        source="telegram",
        content_text=message_text,
        created_at=utc_now_iso(),
        media_paths=[update.photo_file_id] if update.photo_file_id else [],
        metadata={"chat_id": update.chat_id, "message_id": update.message_id},
    )
