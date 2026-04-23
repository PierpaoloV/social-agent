from __future__ import annotations

from collections import Counter

from .models import ApprovalAction, PreferenceSnapshot, PublishedPost, WeeklySummary, make_id, utc_now_iso


def build_weekly_summary(week_key: str, batches: list[dict], actions: list[ApprovalAction], publications: list[PublishedPost], preference_snapshot: PreferenceSnapshot | None) -> WeeklySummary:
    feedback_counter: Counter[str] = Counter()
    for action in actions:
        feedback_counter.update(action.feedback_tags)
    approved_count = sum(1 for action in actions if action.action_type == "approve")
    rejected_count = sum(1 for action in actions if action.action_type == "reject")
    edited_count = sum(1 for action in actions if action.action_type == "edit")
    markdown = "\n".join(
        [
            f"# Weekly Summary - {week_key}",
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
    return WeeklySummary(
        summary_id=make_id("summary"),
        week_key=week_key,
        created_at=utc_now_iso(),
        drafted_batches=len(batches),
        approved_count=approved_count,
        rejected_count=rejected_count,
        edited_count=edited_count,
        published_count=len(publications),
        top_sources=["telegram_inbox", "github_milestone"],
        common_feedback_tags=[tag for tag, _ in feedback_counter.most_common(5)],
        preference_snapshot_id=preference_snapshot.snapshot_id if preference_snapshot else None,
        markdown=markdown,
    )
