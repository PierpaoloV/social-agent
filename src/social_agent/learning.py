from __future__ import annotations

from collections import Counter

from .models import ApprovalAction, PreferenceSnapshot, make_id, utc_now_iso


def build_preference_snapshot(actions: list[ApprovalAction]) -> PreferenceSnapshot:
    approved_tones: list[str] = []
    preferred_sources: list[str] = []
    hook_patterns: list[str] = []
    rejection_patterns: list[str] = []
    notes: list[str] = []

    feedback_counter: Counter[str] = Counter()
    for action in actions:
        for tag in action.feedback_tags:
            feedback_counter[tag] += 1
        if action.action_type == "approve":
            approved_tones.append("technical")
        if action.action_type == "edit" and action.edited_text_after:
            hook_patterns.append(action.edited_text_after[:60])
        if action.note:
            notes.append(action.note)

    rejection_patterns = [tag for tag, _ in feedback_counter.most_common(4)]
    if not approved_tones:
        approved_tones = ["technical", "grounded", "sharp when useful"]
    if not preferred_sources:
        preferred_sources = ["telegram_inbox", "github_milestone"]
    if not hook_patterns:
        hook_patterns = ["clear lesson", "strong first sentence", "specific outcome"]

    return PreferenceSnapshot(
        snapshot_id=make_id("pref"),
        created_at=utc_now_iso(),
        approved_tones=approved_tones[:4],
        preferred_sources=preferred_sources[:4],
        rejection_patterns=rejection_patterns,
        hook_patterns=hook_patterns[:4],
        notes=notes[:5],
    )

