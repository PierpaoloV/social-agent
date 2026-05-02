# Decision Log

## Logging Convention

For every meaningful product, workflow, or implementation change, log these three things explicitly:

### Problem
What was going wrong, missing, or confusing in the current system.

### Proposed Change
What we intended to change before implementation.

### Actual Solution
What shipped in code, including any meaningful difference from the original proposal.

## 2026-04-23

### Decision
Initialize the repository as a public Python project with a private companion state repo, Telegram as both inbox and approval surface, and GitHub Actions as the scheduler.

### Status
Accepted

### Rationale
This keeps the public repo clean, cheap to run, and easy to open-source while preserving privacy for notes, images, approvals, and learning state.

### Impact
- Public repo stores code, docs, config, and assets only.
- Runtime state is synchronized separately through `SOCIAL_AGENT_STATE_DIR`.
- The CLI and workflows are built around scheduled batch processing instead of a long-running server.

## 2026-04-23 (implementation)

### Decision
Implement the application as a standard-library-first Python package with YAML config, CLI jobs, dry-run support, and a filesystem state store that is safe to mirror into a private companion repo.

### Status
Accepted

### Rationale
This keeps setup lightweight, makes local testing easy, and avoids adding infrastructure or third-party runtime dependencies before they are truly needed.

### Impact
- Telegram, X, GitHub, and OpenAI integrations are adapter-based and easy to mock.
- The repo includes a deterministic test suite for policy rules and workflow scenarios.
- Dry-run mode makes the pipeline usable before secrets are configured.

## 2026-04-24 (operations)

### Decision
Shorten Telegram-facing identifiers and optimize the review UX around human-speed commands.

### Status
Accepted

### Rationale
Live testing showed that long machine IDs made Telegram approvals unnecessarily error-prone and slow.

### Impact
- Draft batches now use short batch IDs such as `b3811`.
- Draft options now use fixed slot IDs `d1`, `d2`, and `d3`.
- Telegram messages include concrete example commands instead of generic placeholders.

## 2026-04-24 (free-tier resilience)

### Decision
Treat X read/search failures as non-fatal and continue weekly digest generation with empty engagement suggestions when the current X tier does not allow search access.

### Status
Accepted

### Rationale
The low-cost operating model intentionally avoids paid X read access. Weekly digests should not break the whole workflow when X returns `402 Payment Required` or similar access-limit responses.

### Impact
- The workflow can still draft, publish, summarize, and learn even when X search is unavailable.
- Weekly engagement suggestions may be empty on restricted X plans.
- Follow digests and weekly summaries remain available.

## 2026-04-24 (state durability)

### Decision
Always commit private companion state back to the private repo, even if a later workflow step fails, and downgrade stale Telegram review commands from fatal errors to soft operator warnings.

### Status
Accepted

### Rationale
Operational testing showed that a workflow failure after draft generation could prevent newly created batches from being persisted, which then made subsequent `/approve` commands reference missing state and fail again.

### Impact
- `Commit private companion state changes` now runs with `if: always()`.
- Unknown or stale batch IDs no longer crash `process-telegram`.
- The bot reports skipped review commands back to Telegram so the user can rerun the workflow and work from a fresh batch.

## 2026-04-24 (operator feedback)

### Decision
Poll Telegram commands every 15 minutes, expose draft model names in Telegram, and acknowledge approval/edit/skip/regenerate actions directly in chat.

### Status
Accepted

### Rationale
Live testing showed two operator pain points: `/regenerate` felt too latent when it depended on manual runs, and it was too hard to tell when the workflow had silently fallen back from OpenAI to heuristic drafting.

### Impact
- Telegram updates are now polled on a short cron in addition to the existing scheduled jobs.
- Draft batch messages now show which model generated each option.
- The bot now confirms whether an approved draft was queued or published immediately, and confirms edit/skip/regenerate actions in chat.

## 2026-04-24 (secret naming incident)

### Decision
Record the OpenAI secret-name typo that caused GitHub Actions to miss the API key during live testing.

### Status
Accepted

### Rationale
The public repo secret was saved as `OPENAI_APY_KEY` instead of `OPENAI_API_KEY`, which made the workflow environment look correctly wired in code while still leaving `OPENAI_API_KEY` blank at runtime.

### Impact
- Draft generation fell back to the heuristic path instead of `gpt-5.4-mini`.
- Telegram batches looked repetitive and model fallback was easy to misdiagnose as a code issue.
- Future troubleshooting should check secret names first whenever a configured runtime variable appears blank in Actions logs.

## 2026-04-24 (model output normalization)

### Decision
Normalize loose draft-kind labels from the LLM before validation instead of assuming the model will always emit the internal enum values.

### Status
Accepted

### Rationale
Live testing with the correctly wired OpenAI key showed the model returning `single_post`, which is semantically valid for the product but did not match the strict internal `DraftKind` enum and caused the draft cycle to fail.

### Impact
- LLM outputs such as `single_post`, `post`, and `quote_tweet` are now mapped to supported internal kinds.
- Unexpected kind labels now degrade safely to `original` rather than crashing the workflow.
- The system is more resilient to harmless wording drift in model-generated JSON.

## 2026-04-24 (X write access failure handling)

### Decision
Record X write failures as failed publication state and notify the operator instead of letting `publish-queued` crash the entire workflow.

### Status
Accepted

### Rationale
Live publishing returned `HTTP 402: Payment Required` from X when calling the create-post endpoint. The approval and queueing logic worked, but the workflow failed during the X write call and left the operator without a clear state-level explanation.

### Impact
- Queued publications that hit an X HTTP error are marked `failed` with the HTTP code, reason, and timestamp.
- Telegram receives an operator alert explaining that the post was not published.
- The workflow can complete and persist state even when X refuses a write request.

## 2026-04-24 (expense tracking)

### Decision
Track direct project costs in `docs/expense-log.md` separately from product and architecture decisions.

### Status
Accepted

### Rationale
The project is explicitly optimized for minimal cost, so prepaid credits, API spend, and other recurring expenses should be visible without mixing them into the decision log.

### Impact
- The initial `$25.00` X API credit load is recorded.
- Future direct expenses should be appended to `docs/expense-log.md`.
- The decision log remains focused on why the system changes.

## 2026-04-24 (X search request hardening)

### Decision
Normalize X recent-search request sizes and treat `400 Bad Request` from the optional engagement scan as non-fatal.

### Status
Accepted

### Rationale
Manual workflow testing after adding X credits showed that drafting and publishing checks could succeed while the weekly digest failed on the optional X recent-search step with `HTTP 400: Bad Request`.

### Impact
- X recent-search requests now use a supported minimum `max_results` value.
- Weekly digest generation returns empty engagement suggestions instead of failing the workflow when X rejects a read query.
- Original drafting and publishing are no longer blocked by optional engagement discovery.

## 2026-04-24 (manual workflow modes)

### Decision
Make manual GitHub Actions runs task-specific, with `process-and-publish` as the default manual task.

### Status
Accepted

### Rationale
Live testing showed that a manual run after approving a draft published the post successfully, but also forced a new draft batch and weekly digest. That made successful runs look noisy and confusing in Telegram.

### Impact
- Default manual runs now process Telegram commands and publish queued posts only.
- Manual draft generation must be selected explicitly with the `drafts` task.
- Manual weekly digest generation must be selected explicitly with the `weekly` task.
- The `all` task remains available for full end-to-end smoke tests.

## 2026-04-24 (publish window enforcement and actionable engagement digests)

### Decision
Enforce queued publishing against the configured local publish window in application code, and make weekly engagement digests actionable by including the target account and source post link.

### Status
Accepted

### Rationale
The repo configuration declared an `11:00` Amsterdam publish window, but the workflow was effectively governed by a fixed UTC cron, which drifted during daylight saving time. Separately, the weekly engagement digest surfaced generic copy without enough context to act on it, making the feature confusing in Telegram.

### Impact
- Queued publishing is now gated by `cadence.publish_window` and `cadence.timezone` instead of a fixed UTC assumption.
- GitHub Actions now checks for queued publications on a short interval, while the app only publishes during the local-time window.
- Successful queued publishing sends a Telegram confirmation instead of failing silently.
- Weekly engagement suggestions now include the target handle, direct X post URL, and clearer reply versus quote-post wording.

## 2026-04-27 (known Telegram weekly-digest UX gap)

### Decision
Record a known operator UX problem: weekly digest suggestions appear close enough to draft-review actions in Telegram that it is easy to try `/reject` on them even though they are not part of the draft approval workflow.

### Status
Accepted

### Rationale
Live use showed that weekly engagement suggestions and follow suggestions can read like actionable review items in chat, but the only supported slash commands still target draft batches. This mismatch is easy to hit during normal operator use and can create avoidable confusion.

### Impact
- Weekly digest suggestions remain advisory-only for now.
- Slash commands such as `/approve` and `/reject` should still be treated as draft-batch actions only.
- A future UX pass should give weekly suggestions their own explicit commands or clearer copy so they are not mistaken for draft-review items.

## 2026-05-01 (freshness and message-history handling)

### Problem
The bot could resend stale or low-variation content because it did not keep a durable record of outbound messages and it treated archived ideas as reusable input even when no genuinely new source material had arrived.

### Proposed Change
Make the communication layer freshness-aware by logging outbound messages, feeding recent sent copy back into drafting, and skipping draft generation when there is no new material instead of recycling old prompts.

### Actual Solution
Implemented an `outbox` state folder and an `OutboundMessage` model, recorded outbound Telegram draft batches and notifications, passed recent outbound draft text into the drafting prompt as anti-repetition context, and changed idea collection so archived Telegram and GitHub ideas are not automatically reused. The draft cycle now returns a skip when no fresh ideas are available and tests cover both non-reuse of old sources and inclusion of recent outbound text in prompt construction.

### Status
Accepted

### Impact
- The system now has durable memory of what it already sent to Telegram.
- Drafting is less likely to repeat the same hook or framing across cycles.
- No-input periods now produce an explicit skip instead of resurfacing old content as if it were new.

## 2026-05-02 (multi-LLM content pipeline)

### Problem
The draft cycle had one LLM role: turn already-collected ideas into posts. That left two gaps. First, the system could miss fresh public material unless the operator manually supplied it. Second, generated drafts went straight to Telegram without an automated privacy, source-grounding, and quality review pass.

### Proposed Change
Upgrade `run-drafts` into a staged content pipeline: a web-enabled scout LLM finds sourced public ideas, the existing drafter LLM writes draft options, and a critic LLM revises or rejects drafts before Telegram review. Keep the workflow low-cost by running the extra LLM stages only during scheduled or forced draft cycles with conservative query and candidate caps.

### Actual Solution
Implement a scout stage using OpenAI Responses web search, a critic stage that scores privacy, fact risk, voice fit, novelty, and specificity, and Telegram review messages that show compact source links for public-web candidates. If the critic finds no safe, high-quality draft, the cycle skips and notifies the operator instead of sending weak drafts.

### Status
Accepted

### Impact
- Draft cycles can use fresh, sourced public material without open-ended browsing.
- Telegram review has visible source links for web-scouted draft ideas.
- Draft batches get an automated privacy and quality pass before operator review.
- Existing approval, queueing, publication, and slash-command flows stay unchanged.
