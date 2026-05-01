from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def make_short_id(prefix: str, length: int = 4) -> str:
    return f"{prefix}{uuid4().hex[:length]}"


def make_option_id(index: int) -> str:
    return f"d{index}"


class SourceType(str, Enum):
    TELEGRAM = "telegram_inbox"
    GITHUB = "github_milestone"
    BACKLOG = "backlog"
    EXTERNAL = "external_scan"


class DraftKind(str, Enum):
    ORIGINAL = "original"
    REPLY = "reply"
    QUOTE_POST = "quote_post"


class ActionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REGENERATE = "regenerate"
    SKIP = "skip"


@dataclass(slots=True)
class InboxItem:
    item_id: str
    source: str
    content_text: str
    created_at: str
    media_paths: list[str] = field(default_factory=list)
    media_keep: bool = False
    status: str = "unprocessed"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> InboxItem:
        return cls(
            item_id=str(payload["item_id"]),
            source=str(payload["source"]),
            content_text=str(payload.get("content_text", "")),
            created_at=str(payload["created_at"]),
            media_paths=[str(item) for item in payload.get("media_paths", [])],
            media_keep=bool(payload.get("media_keep", False)),
            status=str(payload.get("status", "unprocessed")),
            metadata=dict(payload.get("metadata") or {}),
        )

    def mark_processed(self) -> None:
        self.status = "processed"

    def validate(self) -> None:
        if not self.item_id:
            raise ValueError("InboxItem.item_id is required")
        if not self.content_text and not self.media_paths:
            raise ValueError("InboxItem requires text or media")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(slots=True)
class IdeaCandidate:
    idea_id: str
    title: str
    summary: str
    source_type: str
    source_ids: list[str]
    topic_class: str
    novelty_score: float
    authenticity_score: float
    relevance_score: float
    source_weight: float
    provenance: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IdeaCandidate:
        return cls(
            idea_id=str(payload["idea_id"]),
            title=str(payload["title"]),
            summary=str(payload["summary"]),
            source_type=str(payload["source_type"]),
            source_ids=[str(item) for item in payload.get("source_ids", [])],
            topic_class=str(payload["topic_class"]),
            novelty_score=float(payload["novelty_score"]),
            authenticity_score=float(payload["authenticity_score"]),
            relevance_score=float(payload["relevance_score"]),
            source_weight=float(payload["source_weight"]),
            provenance=[str(item) for item in payload.get("provenance", [])],
            metadata=dict(payload.get("metadata") or {}),
        )

    @property
    def source_key(self) -> tuple[str, tuple[str, ...]]:
        return self.source_type, tuple(sorted(str(source_id) for source_id in self.source_ids))

    @property
    def overall_score(self) -> float:
        return round(
            (self.novelty_score * 0.30)
            + (self.authenticity_score * 0.35)
            + (self.relevance_score * 0.25)
            + (self.source_weight * 0.10),
            4,
        )

    def mark_drafted(self) -> None:
        self.metadata["last_drafted_at"] = utc_now_iso()
        if self.source_type == SourceType.BACKLOG.value and not self.metadata.get("allow_reuse"):
            self.metadata["consumed_at"] = utc_now_iso()

    def validate(self) -> None:
        if not self.idea_id or not self.title:
            raise ValueError("IdeaCandidate requires idea_id and title")
        if self.source_type not in {item.value for item in SourceType}:
            raise ValueError(f"Unsupported source type: {self.source_type}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["overall_score"] = self.overall_score
        return payload


@dataclass(slots=True)
class DraftOption:
    draft_id: str
    batch_id: str
    kind: str
    topic_class: str
    language: str
    text: str
    source_provenance: list[str]
    created_at: str
    model_name: str
    score: float = 0.0
    thread_posts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DraftOption:
        return cls(
            draft_id=str(payload["draft_id"]),
            batch_id=str(payload["batch_id"]),
            kind=str(payload["kind"]),
            topic_class=str(payload["topic_class"]),
            language=str(payload["language"]),
            text=str(payload["text"]),
            source_provenance=[str(item) for item in payload.get("source_provenance", [])],
            created_at=str(payload["created_at"]),
            model_name=str(payload["model_name"]),
            score=float(payload.get("score", 0.0)),
            thread_posts=[str(item) for item in payload.get("thread_posts", [])],
            metadata=dict(payload.get("metadata") or {}),
        )

    def apply_edit(self, edited_text: str) -> str:
        previous_text = self.text
        self.text = edited_text
        return previous_text

    def validate(self) -> None:
        if not self.draft_id or not self.batch_id:
            raise ValueError("DraftOption requires draft_id and batch_id")
        if self.kind not in {item.value for item in DraftKind}:
            raise ValueError(f"Unsupported draft kind: {self.kind}")
        if self.language not in {"en", "it", "es"}:
            raise ValueError(f"Unsupported language: {self.language}")
        if not self.text:
            raise ValueError("DraftOption.text is required")
        if self.thread_posts and len(self.thread_posts) > 3:
            raise ValueError("DraftOption thread size exceeds 3")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(slots=True)
class DraftBatch:
    batch_id: str
    created_at: str
    scheduled_for: str
    cycle_key: str
    regenerate_count: int = 0
    delivered_message_id: str | None = None
    status: str = "drafted"
    options: list[DraftOption] = field(default_factory=list)
    idea_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DraftBatch:
        return cls(
            batch_id=str(payload["batch_id"]),
            created_at=str(payload["created_at"]),
            scheduled_for=str(payload["scheduled_for"]),
            cycle_key=str(payload["cycle_key"]),
            regenerate_count=int(payload.get("regenerate_count", 0)),
            delivered_message_id=payload.get("delivered_message_id"),
            status=str(payload.get("status", "drafted")),
            options=[DraftOption.from_dict(item) for item in payload.get("options", [])],
            idea_ids=[str(item) for item in payload.get("idea_ids", [])],
        )

    def find_option(self, draft_id: str) -> DraftOption:
        for option in self.options:
            if option.draft_id == draft_id:
                return option
        raise ValueError(f"Unknown draft_id: {draft_id}")

    def regenerate(self) -> None:
        if self.regenerate_count >= 1:
            raise ValueError("Batch already regenerated once")
        self.regenerate_count += 1

    def mark_skipped(self) -> None:
        self.status = "skipped"

    def mark_approved(self, draft_id: str) -> DraftOption:
        option = self.find_option(draft_id)
        self.status = "approved"
        return option

    def edit_option(self, draft_id: str, edited_text: str) -> tuple[DraftOption, str]:
        option = self.find_option(draft_id)
        previous_text = option.apply_edit(edited_text)
        return option, previous_text

    def validate(self) -> None:
        if not self.batch_id or not self.cycle_key:
            raise ValueError("DraftBatch requires batch_id and cycle_key")
        if self.regenerate_count > 1:
            raise ValueError("DraftBatch.regenerate_count cannot exceed 1")
        if len(self.options) > 3:
            raise ValueError("DraftBatch supports up to 3 options")
        for option in self.options:
            option.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "batch_id": self.batch_id,
            "created_at": self.created_at,
            "scheduled_for": self.scheduled_for,
            "cycle_key": self.cycle_key,
            "regenerate_count": self.regenerate_count,
            "delivered_message_id": self.delivered_message_id,
            "status": self.status,
            "idea_ids": list(self.idea_ids),
            "options": [option.to_dict() for option in self.options],
        }


@dataclass(slots=True)
class ApprovalAction:
    action_id: str
    action_type: str
    target_batch_id: str
    draft_id: str | None
    created_at: str
    feedback_tags: list[str] = field(default_factory=list)
    note: str | None = None
    edited_text_before: str | None = None
    edited_text_after: str | None = None
    publish_now: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ApprovalAction:
        return cls(
            action_id=str(payload["action_id"]),
            action_type=str(payload["action_type"]),
            target_batch_id=str(payload["target_batch_id"]),
            draft_id=payload.get("draft_id"),
            created_at=str(payload["created_at"]),
            feedback_tags=[str(item) for item in payload.get("feedback_tags", [])],
            note=payload.get("note"),
            edited_text_before=payload.get("edited_text_before"),
            edited_text_after=payload.get("edited_text_after"),
            publish_now=bool(payload.get("publish_now", False)),
            metadata=dict(payload.get("metadata") or {}),
        )

    def validate(self) -> None:
        if self.action_type not in {item.value for item in ActionType}:
            raise ValueError(f"Unsupported action type: {self.action_type}")
        if self.action_type in {ActionType.APPROVE.value, ActionType.REJECT.value, ActionType.EDIT.value} and not self.draft_id:
            raise ValueError("Draft-level actions require a draft_id")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(slots=True)
class EngagementSuggestion:
    suggestion_id: str
    suggestion_type: str
    target_handle: str
    context_summary: str
    draft_text: str
    created_at: str
    source_post_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EngagementSuggestion:
        return cls(
            suggestion_id=str(payload["suggestion_id"]),
            suggestion_type=str(payload["suggestion_type"]),
            target_handle=str(payload["target_handle"]),
            context_summary=str(payload["context_summary"]),
            draft_text=str(payload["draft_text"]),
            created_at=str(payload["created_at"]),
            source_post_id=payload.get("source_post_id"),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FollowSuggestion:
    suggestion_id: str
    handle: str
    display_name: str
    category: str
    reason: str
    relevance_score: float
    signal_score: float
    style_fit_score: float
    redundancy_penalty: float
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FollowSuggestion:
        return cls(
            suggestion_id=str(payload["suggestion_id"]),
            handle=str(payload["handle"]),
            display_name=str(payload["display_name"]),
            category=str(payload["category"]),
            reason=str(payload["reason"]),
            relevance_score=float(payload["relevance_score"]),
            signal_score=float(payload["signal_score"]),
            style_fit_score=float(payload["style_fit_score"]),
            redundancy_penalty=float(payload["redundancy_penalty"]),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata") or {}),
        )

    @property
    def total_score(self) -> float:
        return round(self.relevance_score + self.signal_score + self.style_fit_score - self.redundancy_penalty, 4)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_score"] = self.total_score
        return payload


@dataclass(slots=True)
class PublishedPost:
    publication_id: str
    draft_id: str
    kind: str
    text: str
    published_at: str
    external_post_id: str | None
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublishedPost:
        return cls(
            publication_id=str(payload["publication_id"]),
            draft_id=str(payload["draft_id"]),
            kind=str(payload["kind"]),
            text=str(payload["text"]),
            published_at=str(payload.get("published_at", "")),
            external_post_id=payload.get("external_post_id"),
            status=str(payload["status"]),
            metadata=dict(payload.get("metadata") or {}),
        )

    @classmethod
    def queue_from_option(cls, option: DraftOption) -> PublishedPost:
        metadata = dict(option.metadata or {})
        metadata["queued_at"] = utc_now_iso()
        return cls(
            publication_id=make_id("pub"),
            draft_id=option.draft_id,
            kind=option.kind,
            text=option.text,
            published_at="",
            external_post_id=None,
            status="queued",
            metadata=metadata,
        )

    def mark_published(self, external_post_id: str | None) -> None:
        self.status = "published"
        self.published_at = utc_now_iso()
        self.external_post_id = external_post_id

    def mark_failed(self, code: int, reason: str) -> None:
        self.status = "failed"
        self.metadata["publish_error"] = {
            "code": code,
            "reason": reason,
            "failed_at": utc_now_iso(),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutboundMessage:
    message_id: str
    channel: str
    kind: str
    text: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OutboundMessage:
        return cls(
            message_id=str(payload["message_id"]),
            channel=str(payload["channel"]),
            kind=str(payload["kind"]),
            text=str(payload["text"]),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata") or {}),
        )

    def validate(self) -> None:
        if not self.message_id or not self.channel or not self.kind:
            raise ValueError("OutboundMessage requires message_id, channel, and kind")
        if not self.text:
            raise ValueError("OutboundMessage.text is required")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(slots=True)
class PreferenceSnapshot:
    snapshot_id: str
    created_at: str
    approved_tones: list[str]
    preferred_sources: list[str]
    rejection_patterns: list[str]
    hook_patterns: list[str]
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PreferenceSnapshot:
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            created_at=str(payload["created_at"]),
            approved_tones=[str(item) for item in payload.get("approved_tones", [])],
            preferred_sources=[str(item) for item in payload.get("preferred_sources", [])],
            rejection_patterns=[str(item) for item in payload.get("rejection_patterns", [])],
            hook_patterns=[str(item) for item in payload.get("hook_patterns", [])],
            notes=[str(item) for item in payload.get("notes", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WeeklySummary:
    summary_id: str
    week_key: str
    created_at: str
    drafted_batches: int
    approved_count: int
    rejected_count: int
    edited_count: int
    published_count: int
    top_sources: list[str]
    common_feedback_tags: list[str]
    preference_snapshot_id: str | None
    markdown: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WeeklySummary:
        return cls(
            summary_id=str(payload["summary_id"]),
            week_key=str(payload["week_key"]),
            created_at=str(payload["created_at"]),
            drafted_batches=int(payload["drafted_batches"]),
            approved_count=int(payload["approved_count"]),
            rejected_count=int(payload["rejected_count"]),
            edited_count=int(payload["edited_count"]),
            published_count=int(payload["published_count"]),
            top_sources=[str(item) for item in payload.get("top_sources", [])],
            common_feedback_tags=[str(item) for item in payload.get("common_feedback_tags", [])],
            preference_snapshot_id=payload.get("preference_snapshot_id"),
            markdown=str(payload["markdown"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
