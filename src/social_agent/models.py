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

    def validate(self) -> None:
        if not self.idea_id or not self.title:
            raise ValueError("IdeaCandidate requires idea_id and title")
        if self.source_type not in {item.value for item in SourceType}:
            raise ValueError(f"Unsupported source type: {self.source_type}")

    @property
    def overall_score(self) -> float:
        return round(
            (self.novelty_score * 0.30)
            + (self.authenticity_score * 0.35)
            + (self.relevance_score * 0.25)
            + (self.source_weight * 0.10),
            4,
        )

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

    def to_dict(self) -> dict[str, Any]:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
