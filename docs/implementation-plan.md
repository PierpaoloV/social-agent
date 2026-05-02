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

## Upgrade: Multi-LLM Content Pipeline

### When
The upgraded content pipeline runs only during `run-drafts`, whether scheduled or manually forced. It does not run during Telegram polling, queued publishing, or weekly digest generation.

### What
The draft cycle becomes `scout -> drafter -> critic -> Telegram review`.

- The scout LLM finds public, sourced idea candidates from configured web topics and safe summaries of fresh local ideas.
- The existing drafter LLM turns ranked candidates into draft options.
- The critic LLM revises or rejects drafts for privacy, source grounding, voice fit, novelty, and specificity before Telegram delivery.

### Why
The original pipeline could only draft from material already captured by Telegram, GitHub, or backlog state. That made drafts more likely to become stale, repetitive, or weakly sourced. The upgrade adds fresh public material and a second quality gate while keeping human approval as the publishing control.

### How
The scout uses OpenAI Responses with web search and stores source links in idea metadata. The drafter continues to produce draft batches from `IdeaCandidate` records. The critic returns revised passing drafts or a reject-all result. If no draft passes, the cycle skips and notifies the operator instead of sending a low-quality batch.
