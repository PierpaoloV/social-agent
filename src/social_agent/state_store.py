from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStateStore:
    """Filesystem-backed state store designed for a synced private companion repo."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for folder in [
            "inbox",
            "ideas",
            "drafts",
            "approvals",
            "errors",
            "outbox",
            "publications",
            "suggestions",
            "summaries",
            "preferences",
            "runtime",
        ]:
            (self.root_dir / folder).mkdir(exist_ok=True)

    def put(self, category: str, object_id: str, payload: dict[str, Any]) -> Path:
        path = self.root_dir / category / f"{object_id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        return path

    def get(self, category: str, object_id: str) -> dict[str, Any] | None:
        path = self.root_dir / category / f"{object_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list(self, category: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted((self.root_dir / category).glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(json.load(handle))
        return items

    def delete(self, category: str, object_id: str) -> None:
        path = self.root_dir / category / f"{object_id}.json"
        if path.exists():
            path.unlink()

    def append_markdown(self, relative_path: str, content: str) -> Path:
        path = self.root_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def read_text(self, relative_path: str) -> str:
        path = self.root_dir / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_runtime(self, key: str, payload: dict[str, Any]) -> Path:
        return self.put("runtime", key, payload)
