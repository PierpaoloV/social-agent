from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from .config import ProfileConfig, SeedsConfig, load_profile_config, load_seeds_config
from .drafting import DraftGenerator
from .github_sources import GitHubMilestoneDetector
from .learning import build_preference_snapshot
from .models import (
    ActionType,
    ApprovalAction,
    DraftBatch,
    DraftKind,
    EngagementSuggestion,
    FollowSuggestion,
    IdeaCandidate,
    InboxItem,
    PublishedPost,
    SourceType,
    make_id,
    utc_now_iso,
)
from .openai_client import OpenAIClient
from .policies import external_query_budget
from .ranking import rank_candidates
from .runtime import RuntimeSettings, load_runtime_settings
from .scheduling import current_cycle_key, iso_utc_now, now_in_timezone, should_run_every_n_days, week_key
from .state_store import JsonStateStore
from .summary import build_weekly_summary
from .telegram import TelegramClient, format_draft_batch_message, parse_review_command
from .x_client import XClient


def build_context() -> tuple[ProfileConfig, SeedsConfig, RuntimeSettings, JsonStateStore]:
    profile = load_profile_config()
    seeds = load_seeds_config()
    runtime = load_runtime_settings()
    store = JsonStateStore(runtime.state_dir)
    return profile, seeds, runtime, store


def doctor() -> dict[str, Any]:
    profile, seeds, runtime, _ = build_context()
    return {
        "timezone": profile.timezone,
        "draft_every_days": profile.draft_every_days,
        "repo_allowlist": profile.repo_allowlist,
        "must_follow_count": len(seeds.must_follow),
        "state_dir": str(runtime.state_dir),
        "dry_run": runtime.dry_run,
        "telegram_configured": bool(runtime.telegram_bot_token and runtime.telegram_chat_id),
        "openai_configured": bool(runtime.openai_api_key),
        "x_write_configured": bool(runtime.x_api_key and runtime.x_api_secret and runtime.x_access_token and runtime.x_access_token_secret),
    }


def process_telegram_updates() -> dict[str, Any]:
    profile, _, runtime, store = build_context()
    if not runtime.telegram_bot_token:
        return {"status": "skipped", "reason": "telegram not configured"}
    telegram = TelegramClient(runtime.telegram_bot_token, dry_run=runtime.dry_run)
    state = store.get("runtime", "telegram_updates") or {"last_update_id": 0}
    updates = telegram.get_updates(offset=state["last_update_id"] + 1)
    inbox_count = 0
    action_count = 0
    action_errors: list[str] = []
    for update in updates:
        state["last_update_id"] = max(state["last_update_id"], update.update_id)
        message_text = update.text or update.caption or ""
        command = parse_review_command(message_text) if message_text else None
        if command:
            try:
                _apply_review_command(command, profile, runtime, store)
                action_count += 1
            except ValueError as exc:
                action_errors.append(str(exc))
                _notify(runtime, f"Review command skipped: {exc}")
            continue
        if not message_text and not update.photo_file_id:
            continue
        item = InboxItem(
            item_id=make_id("inbox"),
            source="telegram",
            content_text=message_text,
            created_at=utc_now_iso(),
            media_paths=[update.photo_file_id] if update.photo_file_id else [],
            metadata={"chat_id": update.chat_id, "message_id": update.message_id},
        )
        store.put("inbox", item.item_id, item.to_dict())
        inbox_count += 1
    store.write_runtime("telegram_updates", state)
    return {"status": "ok", "inbox_count": inbox_count, "action_count": action_count, "action_errors": action_errors}


def run_draft_cycle(force: bool = False) -> dict[str, Any]:
    profile, _, runtime, store = build_context()
    if not force and not should_run_every_n_days(profile.timezone, profile.draft_every_days):
        return {"status": "skipped", "reason": "not scheduled day"}
    ideas = _collect_idea_candidates(profile, runtime, store)
    ranked = rank_candidates(ideas, recent_topics=_recent_topics(store))
    if not ranked or ranked[0].overall_score < 0.62:
        _notify(runtime, "No strong post idea surfaced this cycle. Skipping instead of forcing content.")
        return {"status": "skipped", "reason": "no strong ideas"}
    openai_client = OpenAIClient(runtime.openai_api_key, dry_run=runtime.dry_run) if runtime.openai_api_key or runtime.dry_run else None
    draft_generator = DraftGenerator(profile=profile, openai_client=openai_client, dry_run=runtime.dry_run or not runtime.openai_api_key)
    preference_snapshot = _latest_preference_snapshot(store)
    batch = draft_generator.generate_batch(
        ideas=ranked[:3],
        cycle_key=current_cycle_key(profile.timezone),
        scheduled_for=f"{current_cycle_key(profile.timezone)}T{profile.publish_window}",
        preference_snapshot=preference_snapshot,
    )
    store.put("drafts", batch.batch_id, batch.to_dict())
    _mark_used_inbox_items(batch.idea_ids, store)
    for option in batch.options:
        if option.metadata is None:
            option.metadata = {}
    if runtime.telegram_bot_token and runtime.telegram_chat_id:
        telegram = TelegramClient(runtime.telegram_bot_token, dry_run=runtime.dry_run)
        telegram.send_markdown_message(runtime.telegram_chat_id, format_draft_batch_message(batch.to_dict()))
    return {"status": "ok", "batch_id": batch.batch_id, "option_count": len(batch.options)}


def publish_queued() -> dict[str, Any]:
    profile, _, runtime, store = build_context()
    x_client = XClient(
        api_key=runtime.x_api_key,
        api_secret=runtime.x_api_secret,
        access_token=runtime.x_access_token,
        access_token_secret=runtime.x_access_token_secret,
        bearer_token=runtime.x_api_bearer_token,
        dry_run=runtime.dry_run,
    )
    queued_records = [record for record in store.list("publications") if record.get("status") == "queued"]
    published = 0
    for record in queued_records:
        response = x_client.create_post(record["text"], quote_post_id=record.get("metadata", {}).get("quote_post_id"))
        record["status"] = "published"
        record["published_at"] = utc_now_iso()
        record["external_post_id"] = response.get("data", {}).get("id")
        store.put("publications", record["publication_id"], record)
        published += 1
    return {"status": "ok", "published": published}


def generate_weekly_outputs(force: bool = False) -> dict[str, Any]:
    profile, seeds, runtime, store = build_context()
    local_day = now_in_timezone(profile.timezone).strftime("%a").upper()[:3]
    if not force and local_day != profile.weekly_digest_day:
        return {"status": "skipped", "reason": "not weekly digest day"}
    week = week_key(profile.timezone)
    engagement = _build_engagement_digest(runtime)
    follow_suggestions = _build_follow_digest(seeds)
    preference_snapshot = _recompute_preference_snapshot(store)
    summary = _build_weekly_summary(store, week, preference_snapshot)

    store.put("suggestions", f"engagement_{week}", {"week_key": week, "items": [item.to_dict() for item in engagement]})
    store.put("suggestions", f"follow_{week}", {"week_key": week, "items": [item.to_dict() for item in follow_suggestions]})
    store.put("summaries", summary.summary_id, summary.to_dict())
    store.append_markdown(f"summaries/{week}.md", summary.markdown + "\n")

    if runtime.telegram_bot_token and runtime.telegram_chat_id:
        telegram = TelegramClient(runtime.telegram_bot_token, dry_run=runtime.dry_run)
        telegram.send_message(runtime.telegram_chat_id, _format_weekly_digest_message(engagement, follow_suggestions, summary.markdown))

    return {
        "status": "ok",
        "week_key": week,
        "engagement_count": len(engagement),
        "follow_count": len(follow_suggestions),
        "summary_id": summary.summary_id,
    }


def _collect_idea_candidates(profile: ProfileConfig, runtime: RuntimeSettings, store: JsonStateStore) -> list[IdeaCandidate]:
    ideas: list[IdeaCandidate] = []
    inbox_items = [item for item in store.list("inbox") if item.get("status") == "unprocessed"]
    for item in inbox_items:
        ideas.append(_idea_from_inbox_item(item, profile.source_weights.get(SourceType.TELEGRAM.value, 1.0)))
    github_detector = GitHubMilestoneDetector(github_token=runtime.github_token, dry_run=runtime.dry_run or not runtime.github_token)
    ideas.extend(github_detector.collect_candidates(profile.repo_allowlist, profile.source_weights.get(SourceType.GITHUB.value, 0.9)))
    backlog = store.list("ideas")
    for item in backlog:
        ideas.append(
            IdeaCandidate(
                idea_id=item["idea_id"],
                title=item["title"],
                summary=item["summary"],
                source_type=item["source_type"],
                source_ids=item["source_ids"],
                topic_class=item["topic_class"],
                novelty_score=item["novelty_score"],
                authenticity_score=item["authenticity_score"],
                relevance_score=item["relevance_score"],
                source_weight=item["source_weight"],
                provenance=item.get("provenance", []),
                metadata=item.get("metadata", {}),
            )
        )
    for idea in ideas:
        store.put("ideas", idea.idea_id, idea.to_dict())
    return ideas


def _idea_from_inbox_item(item: dict[str, Any], source_weight: float) -> IdeaCandidate:
    text = item.get("content_text", "").strip()
    topic_class = _infer_topic_class(text)
    novelty = 0.86 if item.get("media_paths") else 0.74
    authenticity = 0.96
    relevance = 0.82 if len(text) > 12 else 0.66
    title = text[:70] if text else "Photo-based update"
    return IdeaCandidate(
        idea_id=make_id("idea"),
        title=title,
        summary=text or "A personal milestone shared through a private photo inbox item.",
        source_type=SourceType.TELEGRAM.value,
        source_ids=[item["item_id"]],
        topic_class=topic_class,
        novelty_score=novelty,
        authenticity_score=authenticity,
        relevance_score=relevance,
        source_weight=source_weight,
        provenance=["telegram inbox", item["item_id"]],
        metadata={"has_media": bool(item.get("media_paths"))},
    )


def _infer_topic_class(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["defended", "phd", "paper", "study", "research"]):
        return "research_reflection"
    if any(token in lowered for token in ["release", "feature", "demo", "workflow", "repo", "agent"]):
        return "project_milestone"
    if any(token in lowered for token in ["lesson", "noticed", "thing i learned", "why"]):
        return "technical_breakdown"
    return "project_milestone"


def _apply_review_command(command: dict[str, Any], profile: ProfileConfig, runtime: RuntimeSettings, store: JsonStateStore) -> None:
    action_name = command["action"]
    batch = store.get("drafts", command["batch_id"])
    if not batch:
        raise ValueError(f"Unknown batch_id: {command['batch_id']}")
    if action_name == ActionType.REGENERATE.value:
        if batch["regenerate_count"] >= 1:
            raise ValueError("Batch already regenerated once")
        batch["regenerate_count"] += 1
        store.put("drafts", batch["batch_id"], batch)
        run_draft_cycle(force=True)
        action = ApprovalAction(
            action_id=make_id("action"),
            action_type=ActionType.REGENERATE.value,
            target_batch_id=batch["batch_id"],
            draft_id=None,
            created_at=utc_now_iso(),
        )
        store.put("approvals", action.action_id, action.to_dict())
        return
    if action_name == ActionType.SKIP.value:
        batch["status"] = "skipped"
        store.put("drafts", batch["batch_id"], batch)
        action = ApprovalAction(
            action_id=make_id("action"),
            action_type=ActionType.SKIP.value,
            target_batch_id=batch["batch_id"],
            draft_id=None,
            created_at=utc_now_iso(),
        )
        store.put("approvals", action.action_id, action.to_dict())
        return
    option = next((option for option in batch["options"] if option["draft_id"] == command["draft_id"]), None)
    if not option:
        raise ValueError(f"Unknown draft_id: {command['draft_id']}")
    if action_name == ActionType.APPROVE.value:
        _queue_or_publish(option, runtime, store)
        batch["status"] = "approved"
        store.put("drafts", batch["batch_id"], batch)
        action = ApprovalAction(
            action_id=make_id("action"),
            action_type=ActionType.APPROVE.value,
            target_batch_id=batch["batch_id"],
            draft_id=option["draft_id"],
            created_at=utc_now_iso(),
            publish_now=option["kind"] == DraftKind.REPLY.value,
        )
        store.put("approvals", action.action_id, action.to_dict())
        return
    if action_name == ActionType.REJECT.value:
        action = ApprovalAction(
            action_id=make_id("action"),
            action_type=ActionType.REJECT.value,
            target_batch_id=batch["batch_id"],
            draft_id=option["draft_id"],
            created_at=utc_now_iso(),
            feedback_tags=[tag for tag in command.get("tags", []) if tag in profile.fixed_feedback_tags],
            note=command.get("note"),
        )
        store.put("approvals", action.action_id, action.to_dict())
        return
    edited_text = command["edited_text"]
    before = option["text"]
    option["text"] = edited_text
    store.put("drafts", batch["batch_id"], batch)
    action = ApprovalAction(
        action_id=make_id("action"),
        action_type=ActionType.EDIT.value,
        target_batch_id=batch["batch_id"],
        draft_id=option["draft_id"],
        created_at=utc_now_iso(),
        edited_text_before=before,
        edited_text_after=edited_text,
    )
    store.put("approvals", action.action_id, action.to_dict())


def _queue_or_publish(option: dict[str, Any], runtime: RuntimeSettings, store: JsonStateStore) -> None:
    publication = PublishedPost(
        publication_id=make_id("pub"),
        draft_id=option["draft_id"],
        kind=option["kind"],
        text=option["text"],
        published_at="",
        external_post_id=None,
        status="queued",
        metadata={},
    )
    if option["kind"] == DraftKind.REPLY.value:
        x_client = XClient(
            api_key=runtime.x_api_key,
            api_secret=runtime.x_api_secret,
            access_token=runtime.x_access_token,
            access_token_secret=runtime.x_access_token_secret,
            bearer_token=runtime.x_api_bearer_token,
            dry_run=runtime.dry_run,
        )
        response = x_client.create_post(option["text"], reply_to_id=option.get("metadata", {}).get("reply_to_id"))
        publication.status = "published"
        publication.published_at = utc_now_iso()
        publication.external_post_id = response.get("data", {}).get("id")
    store.put("publications", publication.publication_id, publication.to_dict())


def _build_engagement_digest(runtime: RuntimeSettings) -> list[EngagementSuggestion]:
    _, seeds, _, _ = build_context()
    x_client = XClient(
        api_key=runtime.x_api_key,
        api_secret=runtime.x_api_secret,
        access_token=runtime.x_access_token,
        access_token_secret=runtime.x_access_token_secret,
        bearer_token=runtime.x_api_bearer_token,
        dry_run=runtime.dry_run or not runtime.x_api_bearer_token,
    )
    suggestions: list[EngagementSuggestion] = []
    queries = external_query_budget(seeds, strict_read_budget=True)
    for index, query in enumerate(queries[:3]):
        try:
            payload = x_client.search_recent_posts(query, max_results=2)
        except HTTPError as exc:
            if exc.code in {401, 402, 403, 429}:
                return []
            raise
        for tweet in payload.get("data", [])[:1]:
            draft_text = f"Interesting angle on {query}. The part I care about most is whether this survives contact with real workflows."
            suggestions.append(
                EngagementSuggestion(
                    suggestion_id=make_id("eng"),
                    suggestion_type="reply" if index < 2 else "quote_post",
                    target_handle=tweet.get("author_id", "unknown"),
                    context_summary=f"Recent post matched query '{query}'",
                    draft_text=draft_text,
                    created_at=utc_now_iso(),
                    source_post_id=tweet.get("id"),
                )
            )
    return suggestions[:3]


def _mark_used_inbox_items(idea_ids: list[str], store: JsonStateStore) -> None:
    relevant_source_ids: set[str] = set()
    for idea_id in idea_ids:
        idea = store.get("ideas", idea_id)
        if idea and idea.get("source_type") == SourceType.TELEGRAM.value:
            relevant_source_ids.update(idea.get("source_ids", []))
    for source_id in relevant_source_ids:
        inbox = store.get("inbox", source_id)
        if not inbox:
            continue
        inbox["status"] = "processed"
        store.put("inbox", source_id, inbox)


def _build_follow_digest(seeds: SeedsConfig) -> list[FollowSuggestion]:
    candidates = seeds.must_follow + seeds.starter_candidates
    suggestions: list[FollowSuggestion] = []
    for item in candidates[: seeds.weekly_limit]:
        scoring = seeds.follow_scoring
        suggestions.append(
            FollowSuggestion(
                suggestion_id=make_id("follow"),
                handle=item["handle"],
                display_name=item["handle"],
                category=item["category"],
                reason=item["reason"],
                relevance_score=scoring["relevance_weight"],
                signal_score=scoring["signal_weight"],
                style_fit_score=scoring["style_fit_weight"],
                redundancy_penalty=scoring["redundancy_penalty"],
                created_at=utc_now_iso(),
            )
        )
    return suggestions[: seeds.weekly_limit]


def _build_weekly_summary(store: JsonStateStore, current_week: str, preference_snapshot) -> Any:
    batches = [batch for batch in store.list("drafts") if _matches_week(batch.get("created_at"), current_week)]
    actions = [_approval_from_dict(item) for item in store.list("approvals") if _matches_week(item.get("created_at"), current_week)]
    publications = [_publication_from_dict(item) for item in store.list("publications") if _matches_week(item.get("published_at") or item.get("metadata", {}).get("queued_at"), current_week)]
    return build_weekly_summary(current_week, batches, actions, publications, preference_snapshot)


def _recompute_preference_snapshot(store: JsonStateStore):
    actions = [_approval_from_dict(item) for item in store.list("approvals")]
    snapshot = build_preference_snapshot(actions)
    store.put("preferences", snapshot.snapshot_id, snapshot.to_dict())
    store.write_runtime("latest_preference_snapshot", snapshot.to_dict())
    return snapshot


def _latest_preference_snapshot(store: JsonStateStore):
    snapshot = store.get("runtime", "latest_preference_snapshot")
    return None if not snapshot else _snapshot_from_dict(snapshot)


def _approval_from_dict(payload: dict[str, Any]) -> ApprovalAction:
    return ApprovalAction(**payload)


def _publication_from_dict(payload: dict[str, Any]) -> PublishedPost:
    return PublishedPost(**payload)


def _snapshot_from_dict(payload: dict[str, Any]):
    from .models import PreferenceSnapshot

    return PreferenceSnapshot(**payload)


def _matches_week(iso_timestamp: str | None, current_week: str) -> bool:
    if not iso_timestamp:
        return False
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    year, week_number, _ = dt.isocalendar()
    return current_week == f"{year}-W{week_number:02d}"


def _recent_topics(store: JsonStateStore) -> list[str]:
    topics: list[str] = []
    for batch in store.list("drafts")[-5:]:
        for option in batch.get("options", []):
            topics.append(option.get("topic_class", ""))
    return [topic for topic in topics if topic]


def _notify(runtime: RuntimeSettings, message: str) -> None:
    if runtime.telegram_bot_token and runtime.telegram_chat_id:
        telegram = TelegramClient(runtime.telegram_bot_token, dry_run=runtime.dry_run)
        telegram.send_message(runtime.telegram_chat_id, message)


def send_alert(message: str) -> None:
    _, _, runtime, _ = build_context()
    _notify(runtime, f"[alert] {message}")


def _format_weekly_digest_message(engagement: list[EngagementSuggestion], follows: list[FollowSuggestion], summary_markdown: str) -> str:
    lines = ["Weekly digest", ""]
    if engagement:
        lines.append("Engagement:")
        for item in engagement:
            lines.append(f"- {item.suggestion_type}: {item.draft_text}")
    if follows:
        lines.append("")
        lines.append("Follow suggestions:")
        for item in follows:
            lines.append(f"- @{item.handle}: {item.reason}")
    lines.append("")
    lines.append(summary_markdown)
    return "\n".join(lines)
