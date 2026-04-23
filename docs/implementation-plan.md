# Implementation Plan

## Goal

Ship a public codebase that powers a private, AI-assisted X workflow with Telegram approvals, cheap defaults, and a companion private state repo.

## Scope
- Python package with CLI entrypoints for all scheduled jobs.
- Public YAML config for persona, cadence, sources, and discovery seeds.
- Filesystem-backed state store designed to sync with a private companion GitHub repo.
- Telegram inbox capture and review-action parsing.
- GitHub repo milestone detection for approved repositories.
- Draft generation, approval handling, queueing, publishing, and learning summaries.
- Weekly engagement, follow, and summary outputs.
- GitHub Actions automation and tests.

## Delivery Order
1. Create repo docs, config, package layout, and pipeline asset.
2. Implement core schemas, config loading, state store, and utilities.
3. Implement idea collection, ranking, and drafting.
4. Implement Telegram adapters and approval workflows.
5. Implement X publishing and queue handling.
6. Implement weekly digests and preference summaries.
7. Add GitHub Actions and verification tests.

## Acceptance Criteria
- Draft batches of three options can be generated and sent.
- Replies can publish immediately after approval.
- Original posts and quote-posts can be queued and published later.
- Structured feedback is stored with optional note and before/after edits.
- Weekly summary and digest artifacts are generated without writing private data to the public repo.

