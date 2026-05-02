from __future__ import annotations

from typing import Any

from .bootstrap import build_application
from .engagement import XEngagementDiscovery, build_follow_suggestions
from .github_sources import GitHubMilestoneDetector
from .history import HistoryManager, format_weekly_digest_message
from .idea_inventory import IdeaInventory
from .publication import PublicationManager
from .ranking import rank_candidates
from .reviews import ReviewLifecycle, TelegramReviewProcessor
from .scheduling import current_cycle_key, is_publish_window_open, now_in_timezone, should_run_every_n_days, week_key
from .telegram import TelegramClient, format_draft_batch_message
from .x_client import XClient


def build_context() -> tuple[Any, Any, Any, Any]:
    app = build_application()
    return app.profile, app.seeds, app.runtime, app.state.store


def doctor() -> dict[str, Any]:
    app = build_application()
    return {
        "timezone": app.profile.timezone,
        "draft_every_days": app.profile.draft_every_days,
        "repo_allowlist": list(app.profile.repo_allowlist),
        "must_follow_count": len(app.seeds.must_follow),
        "state_dir": str(app.runtime.state_dir),
        "dry_run": app.runtime.dry_run,
        "telegram_configured": bool(app.runtime.telegram_bot_token and app.runtime.telegram_chat_id),
        "openai_configured": bool(app.runtime.openai_api_key),
        "x_write_configured": bool(
            app.runtime.x_api_key and app.runtime.x_api_secret and app.runtime.x_access_token and app.runtime.x_access_token_secret
        ),
    }


def process_telegram_updates() -> dict[str, Any]:
    app = build_application()
    if not app.runtime.telegram_bot_token:
        return {"status": "skipped", "reason": "telegram not configured"}
    publication_manager = PublicationManager(
        policy=app.policy,
        state=app.state,
        x_client=app.x_client(),
        notifier=app.notifier,
    )
    lifecycle = ReviewLifecycle(
        state=app.state,
        notifier=app.notifier,
        publication_manager=publication_manager,
        fixed_feedback_tags=app.profile.fixed_feedback_tags,
        regenerate_batch=lambda: run_draft_cycle(force=True),
    )
    processor = TelegramReviewProcessor(
        telegram_client=app.telegram_client(),
        state=app.state,
        notifier=app.notifier,
        lifecycle=lifecycle,
    )
    return processor.process_updates()


def run_draft_cycle(force: bool = False) -> dict[str, Any]:
    app = build_application()
    if not force and not should_run_every_n_days(app.profile.timezone, app.profile.draft_every_days, app.profile.draft_anchor_date):
        return {"status": "skipped", "reason": "not scheduled day"}
    idea_inventory = IdeaInventory(
        policy=app.policy,
        state=app.state,
        github_source=app.github_detector(),
        web_scout=app.web_scout(),
    )
    ideas = idea_inventory.collect_fresh_ideas()
    history = HistoryManager(app.state)
    if not ideas:
        app.notifier.send("No new source material surfaced this cycle, so I skipped drafting instead of recycling older prompts.")
        return {"status": "skipped", "reason": "no fresh ideas"}
    ranked = rank_candidates(ideas, recent_topics=history.recent_topics())
    if not ranked or ranked[0].overall_score < 0.62:
        app.notifier.send("No strong new post idea surfaced this cycle. Skipping instead of forcing content.")
        return {"status": "skipped", "reason": "no strong ideas"}
    batch = app.draft_generator().generate_batch(
        ideas=ranked[:3],
        cycle_key=current_cycle_key(app.profile.timezone),
        scheduled_for=f"{current_cycle_key(app.profile.timezone)}T{app.profile.publish_window}",
        preference_snapshot=history.latest_preference_snapshot(),
        recent_drafts=history.recent_outbound_draft_texts(),
    )
    review = app.draft_critic().review_batch(batch, history.recent_outbound_draft_texts())
    if not review.accepted or review.batch is None:
        app.notifier.send(f"No safe, high-quality draft was produced this cycle. {review.reason or 'Skipping Telegram review.'}")
        return {"status": "skipped", "reason": "no safe high-quality drafts"}
    batch = review.batch
    if not app.runtime.openai_api_key and not app.runtime.dry_run:
        app.notifier.send("OpenAI key is missing in the workflow environment, so this batch used the heuristic fallback instead of gpt-5.4-mini.")
    app.state.drafts.save(batch)
    idea_inventory.mark_drafted(batch.idea_ids)
    if app.runtime.telegram_bot_token and app.runtime.telegram_chat_id:
        telegram = app.telegram_client()
        message_text = format_draft_batch_message(batch.to_dict())
        telegram.send_markdown_message(app.runtime.telegram_chat_id, message_text)
        app.notifier.record_outbound_message(
            channel="telegram",
            kind="draft_batch",
            text=message_text,
            metadata={
                "batch_id": batch.batch_id,
                "option_texts": [option.text for option in batch.options],
                "idea_ids": batch.idea_ids,
            },
        )
    return {"status": "ok", "batch_id": batch.batch_id, "option_count": len(batch.options)}


def publish_queued(force: bool = False) -> dict[str, Any]:
    app = build_application()
    local_now = now_in_timezone(app.profile.timezone)
    if not force and not is_publish_window_open(app.profile.timezone, app.profile.publish_window, reference_time=local_now):
        return {
            "status": "skipped",
            "reason": "outside publish window",
            "local_time": local_now.strftime("%H:%M"),
            "publish_window": app.profile.publish_window,
            "timezone": app.profile.timezone,
        }
    publication_manager = PublicationManager(
        policy=app.policy,
        state=app.state,
        x_client=app.x_client(),
        notifier=app.notifier,
    )
    published, failed = publication_manager.flush_queue()
    if published:
        app.notifier.send(f"Published {published} queued post(s) during the {app.profile.publish_window} {app.profile.timezone} window.")
    return {"status": "ok", "published": published, "failed": failed}


def generate_weekly_outputs(force: bool = False) -> dict[str, Any]:
    app = build_application()
    local_day = now_in_timezone(app.profile.timezone).strftime("%a").upper()[:3]
    if not force and local_day != app.profile.weekly_digest_day:
        return {"status": "skipped", "reason": "not weekly digest day"}
    week = week_key(app.profile.timezone)
    engagement = XEngagementDiscovery(policy=app.policy, x_client=app.x_client(discovery=True)).build_engagement_suggestions()
    follow_suggestions = build_follow_suggestions(app.seeds)
    history = HistoryManager(app.state)
    preference_snapshot = history.recompute_preference_snapshot()
    summary = history.build_weekly_summary(week, preference_snapshot)
    app.state.suggestions.save(f"engagement_{week}", {"week_key": week, "items": [item.to_dict() for item in engagement]})
    app.state.suggestions.save(f"follow_{week}", {"week_key": week, "items": [item.to_dict() for item in follow_suggestions]})
    if app.runtime.telegram_bot_token and app.runtime.telegram_chat_id:
        telegram = app.telegram_client()
        digest_text = format_weekly_digest_message(engagement, follow_suggestions, summary.markdown)
        telegram.send_message(app.runtime.telegram_chat_id, digest_text)
        app.notifier.record_outbound_message(
            channel="telegram",
            kind="weekly_digest",
            text=digest_text,
            metadata={"week_key": week},
        )
    return {
        "status": "ok",
        "week_key": week,
        "engagement_count": len(engagement),
        "follow_count": len(follow_suggestions),
        "summary_id": summary.summary_id,
    }


def send_alert(message: str) -> None:
    app = build_application()
    app.notifier.send(f"[alert] {message}")
