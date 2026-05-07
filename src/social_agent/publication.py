from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError

from .config import SocialAgentPolicy
from .models import DraftOption, PublishedPost
from .state import SocialAgentState
from .x_client import XAPIError


@dataclass(slots=True)
class PublicationManager:
    policy: SocialAgentPolicy
    state: SocialAgentState
    x_client: object
    notifier: object

    def queue_or_publish(self, option: DraftOption) -> str:
        publication = PublishedPost.queue_from_option(option)
        mode = self.policy.publish_mode_for(option.kind)
        if mode == "immediate":
            response = self.x_client.create_post(option.text, reply_to_id=option.metadata.get("reply_to_id"))
            publication.mark_published(response.get("data", {}).get("id"))
        self.state.publications.save(publication)
        return publication.status

    def flush_queue(self) -> tuple[int, int]:
        published = 0
        failed = 0
        for publication in self.state.publications.list_queued():
            try:
                response = self.x_client.create_post(
                    publication.text,
                    quote_post_id=publication.metadata.get("quote_post_id"),
                )
            except (HTTPError, XAPIError) as exc:
                if isinstance(exc, XAPIError):
                    publication.mark_failed(
                        exc.code,
                        exc.reason,
                        title=exc.title,
                        detail=exc.detail,
                        problem_type=exc.problem_type,
                        problem_reason=exc.problem_reason,
                        response_body=exc.response_body,
                    )
                    extra_context = ""
                    if exc.problem_reason:
                        extra_context = f" ({exc.problem_reason})"
                    elif exc.title:
                        extra_context = f" ({exc.title})"
                    detail_suffix = f" Detail: {exc.detail}" if exc.detail else ""
                else:
                    publication.mark_failed(exc.code, exc.reason)
                    extra_context = ""
                    detail_suffix = ""
                self.state.publications.save(publication)
                failed += 1
                self.notifier.send(
                    f"Publishing `{publication.publication_id}` failed with X HTTP {exc.code}: {exc.reason}{extra_context}. "
                    f"The post was not published and is marked failed in private state.{detail_suffix}"
                )
                continue
            publication.mark_published(response.get("data", {}).get("id"))
            self.state.publications.save(publication)
            published += 1
        return published, failed
