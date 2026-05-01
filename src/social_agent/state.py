from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    ApprovalAction,
    DraftBatch,
    IdeaCandidate,
    InboxItem,
    OutboundMessage,
    PreferenceSnapshot,
    PublishedPost,
    WeeklySummary,
)
from .state_store import JsonStateStore


class InboxRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, item: InboxItem) -> None:
        self.store.put("inbox", item.item_id, item.to_dict())

    def list_unprocessed(self) -> list[InboxItem]:
        return [InboxItem.from_dict(item) for item in self.store.list("inbox") if item.get("status") == "unprocessed"]

    def get(self, item_id: str) -> InboxItem | None:
        payload = self.store.get("inbox", item_id)
        return None if payload is None else InboxItem.from_dict(payload)

    def mark_processed(self, item_id: str) -> None:
        item = self.get(item_id)
        if item is None:
            return
        item.mark_processed()
        self.save(item)


class IdeaRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, idea: IdeaCandidate) -> None:
        self.store.put("ideas", idea.idea_id, idea.to_dict())

    def get(self, idea_id: str) -> IdeaCandidate | None:
        payload = self.store.get("ideas", idea_id)
        return None if payload is None else IdeaCandidate.from_dict(payload)

    def list_all(self) -> list[IdeaCandidate]:
        return [IdeaCandidate.from_dict(item) for item in self.store.list("ideas")]

    def archived_source_keys(self) -> set[tuple[str, tuple[str, ...]]]:
        return {idea.source_key for idea in self.list_all()}

    def list_reusable_backlog(self) -> list[IdeaCandidate]:
        reusable: list[IdeaCandidate] = []
        for idea in self.list_all():
            if idea.source_type != "backlog":
                continue
            if idea.metadata.get("consumed_at"):
                continue
            reusable.append(idea)
        return reusable

    def mark_drafted(self, idea_ids: list[str]) -> list[str]:
        processed_inbox_ids: set[str] = set()
        for idea_id in idea_ids:
            idea = self.get(idea_id)
            if idea is None:
                continue
            idea.mark_drafted()
            self.save(idea)
            if idea.source_type == "telegram_inbox":
                processed_inbox_ids.update(idea.source_ids)
        return sorted(processed_inbox_ids)


class DraftRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, batch: DraftBatch) -> None:
        self.store.put("drafts", batch.batch_id, batch.to_dict())

    def get(self, batch_id: str) -> DraftBatch | None:
        payload = self.store.get("drafts", batch_id)
        return None if payload is None else DraftBatch.from_dict(payload)

    def list_all(self) -> list[DraftBatch]:
        return [DraftBatch.from_dict(item) for item in self.store.list("drafts")]

    def recent_topics(self, limit: int = 5) -> list[str]:
        topics: list[str] = []
        for batch in self.list_all()[-limit:]:
            for option in batch.options:
                if option.topic_class:
                    topics.append(option.topic_class)
        return topics


class ApprovalRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, action: ApprovalAction) -> None:
        self.store.put("approvals", action.action_id, action.to_dict())

    def list_all(self) -> list[ApprovalAction]:
        return [ApprovalAction.from_dict(item) for item in self.store.list("approvals")]


class PublicationRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, publication: PublishedPost) -> None:
        self.store.put("publications", publication.publication_id, publication.to_dict())

    def get(self, publication_id: str) -> PublishedPost | None:
        payload = self.store.get("publications", publication_id)
        return None if payload is None else PublishedPost.from_dict(payload)

    def list_all(self) -> list[PublishedPost]:
        return [PublishedPost.from_dict(item) for item in self.store.list("publications")]

    def list_queued(self) -> list[PublishedPost]:
        return [item for item in self.list_all() if item.status == "queued"]


class OutboxRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, message: OutboundMessage) -> None:
        self.store.put("outbox", message.message_id, message.to_dict())

    def list_all(self) -> list[OutboundMessage]:
        return [OutboundMessage.from_dict(item) for item in self.store.list("outbox")]

    def recent_draft_texts(self, limit: int = 6) -> list[str]:
        texts: list[str] = []
        for item in reversed(self.list_all()):
            if item.kind != "draft_batch":
                continue
            option_texts = list(item.metadata.get("option_texts") or [])
            for text in option_texts:
                if text:
                    texts.append(str(text))
            if len(texts) >= limit:
                return texts[:limit]
        return texts[:limit]


class PreferenceRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, snapshot: PreferenceSnapshot) -> None:
        self.store.put("preferences", snapshot.snapshot_id, snapshot.to_dict())
        self.store.write_runtime("latest_preference_snapshot", snapshot.to_dict())

    def latest(self) -> PreferenceSnapshot | None:
        payload = self.store.get("runtime", "latest_preference_snapshot")
        return None if payload is None else PreferenceSnapshot.from_dict(payload)


class SummaryRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, summary: WeeklySummary) -> None:
        self.store.put("summaries", summary.summary_id, summary.to_dict())
        self.store.append_markdown(f"summaries/{summary.week_key}.md", summary.markdown + "\n")


class SuggestionRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def save(self, suggestion_id: str, payload: dict[str, Any]) -> None:
        self.store.put("suggestions", suggestion_id, payload)


class RuntimeRepository:
    def __init__(self, store: JsonStateStore) -> None:
        self.store = store

    def get(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any] | None:
        payload = self.store.get("runtime", key)
        if payload is None and default is not None:
            return dict(default)
        return payload

    def write(self, key: str, payload: dict[str, Any]) -> None:
        self.store.write_runtime(key, payload)


@dataclass(slots=True)
class SocialAgentState:
    store: JsonStateStore
    inbox: InboxRepository
    ideas: IdeaRepository
    drafts: DraftRepository
    approvals: ApprovalRepository
    publications: PublicationRepository
    outbox: OutboxRepository
    preferences: PreferenceRepository
    summaries: SummaryRepository
    suggestions: SuggestionRepository
    runtime: RuntimeRepository


def build_state(store: JsonStateStore) -> SocialAgentState:
    return SocialAgentState(
        store=store,
        inbox=InboxRepository(store),
        ideas=IdeaRepository(store),
        drafts=DraftRepository(store),
        approvals=ApprovalRepository(store),
        publications=PublicationRepository(store),
        outbox=OutboxRepository(store),
        preferences=PreferenceRepository(store),
        summaries=SummaryRepository(store),
        suggestions=SuggestionRepository(store),
        runtime=RuntimeRepository(store),
    )
