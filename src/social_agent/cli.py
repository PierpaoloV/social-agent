from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Callable
from typing import Any

from .workflows import doctor, generate_weekly_outputs, process_telegram_updates, publish_queued, run_draft_cycle, send_alert
from .models import make_id, utc_now_iso
from .runtime import load_runtime_settings
from .state_store import JsonStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="social-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor")
    subparsers.add_parser("process-telegram")

    run_drafts_parser = subparsers.add_parser("run-drafts")
    run_drafts_parser.add_argument("--force", action="store_true")

    publish_parser = subparsers.add_parser("publish-queued")
    publish_parser.add_argument("--force", action="store_true")

    weekly_parser = subparsers.add_parser("weekly-digests")
    weekly_parser.add_argument("--force", action="store_true")

    alert_parser = subparsers.add_parser("alert")
    alert_parser.add_argument("message")

    return parser


def _persist_command_error(command_name: str, exc: Exception) -> dict[str, Any]:
    error_id = make_id("err")
    payload: dict[str, Any] = {
        "error_id": error_id,
        "command": command_name,
        "status": "error",
        "created_at": utc_now_iso(),
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }
    try:
        runtime = load_runtime_settings()
        store = JsonStateStore(runtime.state_dir)
        store.put("errors", error_id, payload)
        store.write_runtime("latest_command_error", payload)
        payload["state_dir"] = str(runtime.state_dir)
    except Exception as tracking_exc:
        payload["tracking_error"] = f"{type(tracking_exc).__name__}: {tracking_exc}"
    return payload


def _run_command(command_name: str, handler: Callable[[], dict[str, Any] | None]) -> int:
    try:
        result = handler()
    except Exception as exc:
        print(json.dumps(_persist_command_error(command_name, exc), indent=2, sort_keys=True))
        return 1
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _run_command("doctor", doctor)
    if args.command == "process-telegram":
        return _run_command("process-telegram", process_telegram_updates)
    if args.command == "run-drafts":
        return _run_command("run-drafts", lambda: run_draft_cycle(force=args.force))
    if args.command == "publish-queued":
        return _run_command("publish-queued", lambda: publish_queued(force=args.force))
    if args.command == "weekly-digests":
        return _run_command("weekly-digests", lambda: generate_weekly_outputs(force=args.force))
    if args.command == "alert":
        return _run_command("alert", lambda: (send_alert(args.message), None)[1])
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
