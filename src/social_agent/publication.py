from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError

from .config import SocialAgentPolicy
from .models import DraftOption, PublishedPost
from .state import SocialAgentState


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
            except HTTPError as exc:
                publication.mark_failed(exc.code, exc.reason)
                self.state.publications.save(publication)
                failed += 1
                self.notifier.send(
                    f"Publishing `{publication.publication_id}` failed with X HTTP {exc.code}: {exc.reason}. "
                    "The post was not published and is marked failed in private state."
                )
                continue
            publication.mark_published(response.get("data", {}).get("id"))
            self.state.publications.save(publication)
            published += 1
        return published, failed
