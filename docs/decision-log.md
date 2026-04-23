# Decision Log

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
