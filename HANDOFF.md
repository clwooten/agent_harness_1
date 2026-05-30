# Handoff — current state

Updated: 2026-05-29 (end of Phase 2)

## Where we are

- **Phase 0**: complete.
- **Phase 1**: complete. `planner.py` calls Opus, taxonomy + task list verified coherent.
- **Phase 2**: complete. `queue_lib.py` (schema + 6 helpers under `fcntl.flock`), `planner.py` parses + validates + writes `queue.json`. Smoke-tested with init/append/claim/mark_done/mark_failed and live planner run.
- **Phase 3+**: not started.

## Next action

Build Phase 3: `fetch_lib.py` + `worker.py` + two notebooks.

- `fetch_lib.py`: `fetch_url(url) -> (title, content)` via httpx + trafilatura; `load_local(path) -> (title, content)` for .md files.
- `worker.py`: polls `queue.json` every 2s, claims next pending task, dispatches by `task_type`, calls Haiku with **tool use** (`record_summary` tool, forced `tool_choice`) for structured output, writes `processed/<slug>.md` with YAML frontmatter, marks done/failed.
- `notebooks/03a_fetch_smoke_test.ipynb` — try `fetch_url` on a blog, Wikipedia, a news index, a dead URL.
- `notebooks/03b_queue_inspector.ipynb` — re-runnable cells for watching `queue.json` state while the worker runs.

Checkpoint: run planner once, run worker in another terminal, watch with `watch -n 1 'jq . queue.json'`, files appear in `processed/`.

### Decisions locked for Phase 3

- **Digest task**: worker runs it when claimed, even if sibling tasks aren't done yet. If it runs early it'll digest only what's currently `done`. Ordering/dependency lesson saved for Phase 5.
- **Worker logging**: print only — no separate `logs/worker.log` write inside `worker.py`. Harness in Phase 4 will be the one redirecting subprocess stdout/stderr to log files.

## Inbox at handoff time

Unchanged from previous handoff:
- `inbox/sample_urls.txt` — 4 URLs (Economist homepage, Anthropic news, Anthropic research piece, Wikipedia/New Order)
- `inbox/SKILL.md` — wearable-data skill spec

`queue.json` exists at project root with 6 pending tasks from the last planner run. Worker (when built) will start consuming it. Re-running `planner.py` overwrites the queue from scratch.

## Notes / gotchas

- `.env` contains the real `ANTHROPIC_API_KEY`. Gitignored.
- GitHub auth: PAT cached in macOS keychain.
- **Planner is non-deterministic**: taxonomy + order will vary run-to-run (no temperature=0). Tag set varies (e.g. `tools` ↔ `reference`, `research` ↔ `anthropic`). Worker reads `meta.taxonomy` at task time, so this is internally consistent within a single planner run.
- **Validation in planner is loud**: bad JSON or unknown task_type → `SystemExit` with raw response visible. Tighten the prompt rather than silently coercing.
- Shell working directory does not reliably persist across Bash tool calls — use absolute paths or `git -C <path>` when scripting from outside the project dir.
- Model strings: planner = `claude-opus-4-7`, worker (Phase 3) = `claude-haiku-4-5-20251001`. `max_tokens` 500/200 for cost.

## Open questions to settle before Phase 4

(In CLAUDE.md "Open design questions for Chris" — revisit at Phase 4 start.)
