from __future__ import annotations

import argparse
import json
import sys

from .workflows import doctor, generate_weekly_outputs, process_telegram_updates, publish_queued, run_draft_cycle, send_alert


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2, sort_keys=True))
        return 0
    if args.command == "process-telegram":
        print(json.dumps(process_telegram_updates(), indent=2, sort_keys=True))
        return 0
    if args.command == "run-drafts":
        print(json.dumps(run_draft_cycle(force=args.force), indent=2, sort_keys=True))
        return 0
    if args.command == "publish-queued":
        print(json.dumps(publish_queued(force=args.force), indent=2, sort_keys=True))
        return 0
    if args.command == "weekly-digests":
        print(json.dumps(generate_weekly_outputs(force=args.force), indent=2, sort_keys=True))
        return 0
    if args.command == "alert":
        send_alert(args.message)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
