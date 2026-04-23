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

