from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from .models import IdeaCandidate, SourceType, make_id


@dataclass(slots=True)
class GitHubMilestoneDetector:
    github_token: str | None = None
    dry_run: bool = False

    def _get_json(self, url: str) -> Any:
        if self.dry_run:
            return []
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "social-agent"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        request = Request(url, headers=headers, method="GET")
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def collect_candidates(self, repos: list[str], source_weight: float) -> list[IdeaCandidate]:
        candidates: list[IdeaCandidate] = []
        for repo in repos:
            if self.dry_run:
                candidates.append(
                    IdeaCandidate(
                        idea_id=make_id("idea"),
                        title=f"Meaningful update in {repo}",
                        summary=f"{repo} shipped a meaningful workflow change worth turning into a post.",
                        source_type=SourceType.GITHUB.value,
                        source_ids=[repo],
                        topic_class="project_milestone",
                        novelty_score=0.82,
                        authenticity_score=0.94,
                        relevance_score=0.88,
                        source_weight=source_weight,
                        provenance=[repo, "dry-run milestone detector"],
                        metadata={"repo": repo, "event_type": "dry_run"},
                    )
                )
                continue
            releases = self._get_json(f"https://api.github.com/repos/{repo}/releases?per_page=1")
            if isinstance(releases, list) and releases:
                release = releases[0]
                candidates.append(
                    IdeaCandidate(
                        idea_id=make_id("idea"),
                        title=f"Release from {repo}",
                        summary=release.get("name") or release.get("tag_name") or f"New release in {repo}",
                        source_type=SourceType.GITHUB.value,
                        source_ids=[str(release.get("id", repo))],
                        topic_class="project_milestone",
                        novelty_score=0.80,
                        authenticity_score=0.90,
                        relevance_score=0.86,
                        source_weight=source_weight,
                        provenance=[repo, "release"],
                        metadata={"repo": repo, "url": release.get("html_url")},
                    )
                )
                continue
            commits = self._get_json(f"https://api.github.com/repos/{repo}/commits?per_page=3")
            if isinstance(commits, list) and commits:
                message = commits[0]["commit"]["message"].splitlines()[0]
                if _looks_like_milestone(message):
                    candidates.append(
                        IdeaCandidate(
                            idea_id=make_id("idea"),
                            title=f"Milestone commit in {repo}",
                            summary=message,
                            source_type=SourceType.GITHUB.value,
                            source_ids=[commits[0]["sha"]],
                            topic_class="project_milestone",
                            novelty_score=0.72,
                            authenticity_score=0.86,
                            relevance_score=0.80,
                            source_weight=source_weight,
                            provenance=[repo, "commit"],
                            metadata={"repo": repo, "sha": commits[0]["sha"]},
                        )
                    )
        return candidates


def _looks_like_milestone(message: str) -> bool:
    lowered = message.lower()
    positive_terms = ("feat", "release", "launch", "demo", "workflow", "milestone", "support", "add")
    negative_terms = ("typo", "bump", "deps", "dependency", "refactor", "lint", "format", "fix readme")
    return any(term in lowered for term in positive_terms) and not any(term in lowered for term in negative_terms)

