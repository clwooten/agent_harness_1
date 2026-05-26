# Handoff — current state

Updated: 2026-05-25 (pause mid-Phase-1)

## Where we are

- **Phase 0**: complete. `uv` project, deps installed, Jupyter kernel `reading-triager` registered, scaffold files + dirs created, initial commit pushed to `github.com/clwooten/agent_harness_1` (main).
- **Phase 1**: code written, **not yet user-verified**.
  - `planner.py` — scans inbox, calls Opus, prints JSON (no queue write yet)
  - `notebooks/01_planner_prompt_iteration.ipynb` — for prompt A/B
  - Dry-run (inbox scan, no API call) confirmed working
  - User has not yet run `uv run python planner.py` against the live API
- **Phase 2+**: not started.

## Next action

User to run:

```bash
cd /Users/cwooten/Projects/Agent_Harness_1
uv run python planner.py
```

Then judge the taxonomy + task list output. Iterate the prompt in the notebook if needed. When the taxonomy looks coherent and the JSON parses cleanly, move to Phase 2 (queue_lib + queue.json).

## Inbox at pause time

- `inbox/sample_urls.txt` — 4 URLs (Economist homepage, Anthropic news, Anthropic research piece, Wikipedia/New Order)
- `inbox/SKILL.md` — wearable-data skill spec (~7KB, has YAML frontmatter)

Two of the URLs (Economist homepage, Anthropic news index) are not articles; trafilatura will likely return thin content in Phase 3 — that's expected and useful for Phase 5 break-it-on-purpose.

## Notes / gotchas

- `.env` contains the real `ANTHROPIC_API_KEY`. Gitignored. Do not commit.
- GitHub auth: pushes use HTTPS + a PAT cached in macOS keychain (Username `clwooten`, "password" = PAT). Subsequent `git push` should not re-prompt.
- Shell working directory does not reliably persist across Bash tool calls in this session — use absolute paths or `git -C <path>` when scripting from outside the project dir.
- Model strings: planner = `claude-opus-4-7`, worker (Phase 3) = `claude-haiku-4-5-20251001`. `max_tokens` deliberately small (500 / 200) for tutorial cost.

## Open questions to settle before Phase 4

(Already noted in CLAUDE.md "Open design questions for Chris" — re-read at Phase 4 start.)
