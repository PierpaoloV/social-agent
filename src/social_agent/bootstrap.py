from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ProfileConfig, SeedsConfig, SocialAgentPolicy, load_policy
from .content_scout import WebContentScout
from .draft_review import DraftCritic, PassthroughDraftCritic
from .drafting import DraftGenerator, HeuristicDraftModel, OpenAIDraftModel
from .github_sources import GitHubMilestoneDetector
from .models import OutboundMessage, make_id, utc_now_iso
from .openai_client import OpenAIClient
from .runtime import RuntimeSettings, load_runtime_settings
from .state import SocialAgentState, build_state
from .state_store import JsonStateStore
from .telegram import TelegramClient
from .x_client import XClient


class Notifier:
    def __init__(self, runtime: RuntimeSettings, state: SocialAgentState) -> None:
        self.runtime = runtime
        self.state = state

    def send(self, message: str, kind: str = "notification") -> None:
        if not self.runtime.telegram_bot_token or not self.runtime.telegram_chat_id:
            return
        telegram = TelegramClient(self.runtime.telegram_bot_token, dry_run=self.runtime.dry_run)
        try:
            telegram.send_message(self.runtime.telegram_chat_id, message)
        except Exception:
            return
        self.record_outbound_message(channel="telegram", kind=kind, text=message)

    def record_outbound_message(
        self,
        channel: str,
        kind: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.state.outbox.save(
            OutboundMessage(
                message_id=make_id("out"),
                channel=channel,
                kind=kind,
                text=text,
                created_at=utc_now_iso(),
                metadata=metadata or {},
            )
        )


@dataclass(slots=True)
class ApplicationContext:
    profile: ProfileConfig
    seeds: SeedsConfig
    policy: SocialAgentPolicy
    runtime: RuntimeSettings
    state: SocialAgentState
    notifier: Notifier

    def maybe_telegram_client(self) -> TelegramClient | None:
        if not self.runtime.telegram_bot_token:
            return None
        return TelegramClient(self.runtime.telegram_bot_token, dry_run=self.runtime.dry_run)

    def telegram_client(self) -> TelegramClient:
        client = self.maybe_telegram_client()
        if client is None:
            raise ValueError("Telegram is not configured")
        return client

    def github_detector(self) -> GitHubMilestoneDetector:
        return GitHubMilestoneDetector(
            github_token=self.runtime.github_token,
            dry_run=self.runtime.dry_run or not self.runtime.github_token,
        )

    def x_client(self, *, discovery: bool = False) -> XClient:
        return XClient(
            api_key=self.runtime.x_api_key,
            api_secret=self.runtime.x_api_secret,
            access_token=self.runtime.x_access_token,
            access_token_secret=self.runtime.x_access_token_secret,
            bearer_token=self.runtime.x_api_bearer_token,
            dry_run=self.runtime.dry_run or (discovery and not self.runtime.x_api_bearer_token),
        )

    def draft_generator(self) -> DraftGenerator:
        heuristic_model = HeuristicDraftModel()
        if self.runtime.dry_run or not self.runtime.openai_api_key:
            return DraftGenerator(profile=self.profile, primary_model=heuristic_model, fallback_model=heuristic_model)
        openai_client = OpenAIClient(self.runtime.openai_api_key, dry_run=False)
        return DraftGenerator(
            profile=self.profile,
            primary_model=OpenAIDraftModel(openai_client),
            fallback_model=heuristic_model,
        )

    def web_scout(self) -> WebContentScout | None:
        if self.runtime.dry_run or not self.runtime.openai_api_key or not self.profile.web_scout.enabled:
            return None
        return WebContentScout(
            policy=self.policy,
            openai_client=OpenAIClient(self.runtime.openai_api_key, dry_run=False),
        )

    def draft_critic(self) -> DraftCritic | PassthroughDraftCritic:
        if self.runtime.dry_run or not self.runtime.openai_api_key:
            return PassthroughDraftCritic()
        return DraftCritic(
            profile=self.profile,
            openai_client=OpenAIClient(self.runtime.openai_api_key, dry_run=False),
        )


def build_application() -> ApplicationContext:
    policy = load_policy()
    runtime = load_runtime_settings()
    store = JsonStateStore(runtime.state_dir)
    state = build_state(store)
    notifier = Notifier(runtime=runtime, state=state)
    return ApplicationContext(
        profile=policy.profile,
        seeds=policy.seeds,
        policy=policy,
        runtime=runtime,
        state=state,
        notifier=notifier,
    )
