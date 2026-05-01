from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from .learning import build_preference_snapshot
from .models import ApprovalAction, DraftKind, EngagementSuggestion, FollowSuggestion, PreferenceSnapshot, WeeklySummary, make_id, utc_now_iso


def matches_week(iso_timestamp: str | None, current_week: str) -> bool:
    if not iso_timestamp:
        return False
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    year, week_number, _ = dt.isocalendar()
    return current_week == f"{year}-W{week_number:02d}"


def build_x_post_url(target_handle: str | None, post_id: str | None) -> str:
    if not post_id:
        return ""
    if target_handle and target_handle not in {"", "unknown"} and not target_handle.isdigit():
        return f"https://x.com/{target_handle}/status/{post_id}"
    return f"https://x.com/i/web/status/{post_id}"


def format_weekly_digest_message(engagement: list[EngagementSuggestion], follows: list[FollowSuggestion], summary_markdown: str) -> str:
    lines = ["Weekly digest", ""]
    if engagement:
        lines.append("Engagement:")
        for item in engagement:
            action_hint = "Use as a reply:" if item.suggestion_type == DraftKind.REPLY.value else "Use as a quote-post:"
            target = f"@{item.target_handle}" if item.target_handle and item.target_handle != "unknown" else "the linked post"
            lines.append(f"- {item.suggestion_type} to {target}")
            if item.source_post_id:
                lines.append(f"  Post: {build_x_post_url(item.target_handle, item.source_post_id)}")
            lines.append(f"  Context: {item.context_summary}")
            lines.append(f"  {action_hint} {item.draft_text}")
    if follows:
        lines.append("")
        lines.append("Follow suggestions:")
        for item in follows:
            lines.append(f"- @{item.handle}: {item.reason}")
    lines.append("")
    lines.append(summary_markdown)
    return "\n".join(lines)


@dataclass(slots=True)
class HistoryManager:
    state: object

    def latest_preference_snapshot(self) -> PreferenceSnapshot | None:
        return self.state.preferences.latest()

    def recompute_preference_snapshot(self) -> PreferenceSnapshot:
        snapshot = build_preference_snapshot(self.state.approvals.list_all())
        self.state.preferences.save(snapshot)
        return snapshot

    def build_weekly_summary(self, current_week: str, preference_snapshot: PreferenceSnapshot | None) -> WeeklySummary:
        batches = [batch for batch in self.state.drafts.list_all() if matches_week(batch.created_at, current_week)]
        actions = [action for action in self.state.approvals.list_all() if matches_week(action.created_at, current_week)]
        publications = [
            publication
            for publication in self.state.publications.list_all()
            if matches_week(publication.published_at or publication.metadata.get("queued_at"), current_week)
        ]
        feedback_counter: Counter[str] = Counter()
        source_counter: Counter[str] = Counter()
        for action in actions:
            feedback_counter.update(action.feedback_tags)
        for batch in batches:
            for option in batch.options:
                for source in option.source_provenance:
                    source_counter.update([source])
        approved_count = sum(1 for action in actions if action.action_type == "approve")
        rejected_count = sum(1 for action in actions if action.action_type == "reject")
        edited_count = sum(1 for action in actions if action.action_type == "edit")
        markdown = "\n".join(
            [
                f"# Weekly Summary - {current_week}",
                "",
                f"- Draft batches: {len(batches)}",
                f"- Approved: {approved_count}",
                f"- Rejected: {rejected_count}",
                f"- Edited: {edited_count}",
                f"- Published: {len(publications)}",
                f"- Common feedback: {', '.join(tag for tag, _ in feedback_counter.most_common(5)) or 'none'}",
                f"- Preference snapshot: {preference_snapshot.snapshot_id if preference_snapshot else 'none'}",
            ]
        )
        summary = WeeklySummary(
            summary_id=make_id("summary"),
            week_key=current_week,
            created_at=utc_now_iso(),
            drafted_batches=len(batches),
            approved_count=approved_count,
            rejected_count=rejected_count,
            edited_count=edited_count,
            published_count=len(publications),
            top_sources=[source for source, _ in source_counter.most_common(5)] or ["telegram_inbox", "github_milestone"],
            common_feedback_tags=[tag for tag, _ in feedback_counter.most_common(5)],
            preference_snapshot_id=preference_snapshot.snapshot_id if preference_snapshot else None,
            markdown=markdown,
        )
        self.state.summaries.save(summary)
        return summary

    def recent_topics(self, limit: int = 5) -> list[str]:
        return self.state.drafts.recent_topics(limit=limit)

    def recent_outbound_draft_texts(self, limit: int = 6) -> list[str]:
        return self.state.outbox.recent_draft_texts(limit=limit)
