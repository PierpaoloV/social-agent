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
            self._publish(publication)
        self.state.publications.save(publication)
        return publication.status

    def _publish(self, publication: PublishedPost) -> None:
        response = self.x_client.create_post(
            publication.text,
            reply_to_id=publication.metadata.get("reply_to_id"),
            quote_post_id=publication.metadata.get("quote_post_id"),
        )
        publication.mark_published(response.get("data", {}).get("id"))

    def _record_failure(self, publication: PublishedPost, exc: HTTPError | XAPIError) -> None:
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
        self.notifier.send(
            f"Publishing `{publication.publication_id}` failed with X HTTP {exc.code}: {exc.reason}{extra_context}. "
            f"The post was not published and is marked failed in private state.{detail_suffix}"
        )

    def flush_queue(self) -> tuple[int, int]:
        published = 0
        failed = 0
        for publication in self.state.publications.list_queued():
            try:
                self._publish(publication)
            except (HTTPError, XAPIError) as exc:
                self._record_failure(publication, exc)
                failed += 1
                continue
            self.state.publications.save(publication)
            published += 1
        return published, failed

    def retry_failed_publications(self, publication_ids: list[str]) -> tuple[int, int, list[str]]:
        published = 0
        failed = 0
        errors: list[str] = []
        for publication_id in publication_ids:
            publication = self.state.publications.get(publication_id)
            if publication is None:
                errors.append(f"{publication_id}: not found")
                continue
            if publication.status != "failed":
                errors.append(f"{publication_id}: status is {publication.status}, not failed")
                continue
            try:
                self._publish(publication)
            except (HTTPError, XAPIError) as exc:
                self._record_failure(publication, exc)
                failed += 1
                continue
            self.state.publications.save(publication)
            published += 1
        return published, failed, errors
