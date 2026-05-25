# Two-Agent Harness Tutorial — Reading Queue Triager

## Purpose

This is a **learning exercise** for the human (Chris) that also produces a useful tool. The goal is to build a minimal but real two-agent system with a supervising harness so Chris can see, touch, and break the moving parts of an agent loop. **The harness is the star** — the agent work exists to give the harness something real to coordinate.

The real-world use case: a **reading queue triager**. Chris drops URLs and/or saved article files into an `inbox/` directory. The system reads through them, summarizes each, tags them against a coherent taxonomy, and writes the results to `processed/`. An optional digest task aggregates everything into a single overview.

Why this use case for a tutorial:

- The planner has real planning to do: scanning the inbox, deciding tag taxonomy, ordering tasks
- The worker has a bounded, well-defined job: fetch (if URL) → extract → summarize → tag → write file
- Output is human-meaningful — you can `cat queue.json` and immediately understand state
- Haiku is genuinely well-suited to the worker's job (summarization), Opus to the planner's (taxonomy design)
- It's something Chris might actually use after the tutorial ends

Chris already runs OpenClaw on a Mac Mini and is comfortable with Python, venvs, LaunchAgents, `.env` discipline, and shell debugging. Pitch explanations at that level. Do not over-explain Python basics, but do explain agent-loop concepts (planner/worker split, autonomy ceilings, message bus choices, etc.) the first time they come up.

## Working environment

- Host: M5 Max MacBook Pro (Apple Silicon, macOS)
- Project directory: '/Users/cwooten/Projects/Agent_Harness_1'
- Python: use `uv` for environment and dependency management. Chris already has `uv` installed. Initialize with `uv init` and add dependencies via `uv add`. The project-local venv lives at `.venv/` and `uv` manages it transparently — Chris does not need to `source` activate scripts when using `uv run`, but he can if he prefers.
- API key: read `ANTHROPIC_API_KEY` from a `.env` in the project root. **Never write the key into source files or commit it.** Add `.env` to `.gitignore` on day one.
- Development style: Chris prefers troubleshooting and exploration in **Jupyter notebooks**, with the actual agents/harness/library code in `.py` files. This is the standard professional pattern (notebooks as scratchpad, modules as the real artifact). Set up Jupyter as a dev dependency in Phase 0 and use notebooks deliberately throughout — see "Notebook usage" below.
- Git: initialize a repo at the project root. Commit after each working milestone so Chris can `git diff` to see what changed.

## Architecture

Two agents communicating through a **shared JSON queue file on disk**, supervised by a Python harness. Input comes from `inbox/`, output goes to `processed/`.

```
   inbox/                                    processed/
   ├── url_list.txt                          ├── article-1.md
   ├── article-1.md                          ├── article-2.md
   └── article-2.md                          └── digest-2025-05-25.md
        │                                          ▲
        │ reads                                    │ writes
        ▼                                          │
  ┌─────────┐     queue.json    ┌─────────┐       │
  │ Planner │ ────────────────► │ Worker  │ ──────┘
  │ (Opus)  │                   │ (Haiku) │
  └─────────┘                   └─────────┘
       ▲                             ▲
       │ spawns                      │ spawns
       └──────────┬──────────────────┘
                  │
            ┌──────────┐
            │ harness  │  autonomy ceilings, approval gates,
            │   .py    │  log tailing, signal handling
            └──────────┘
```

### Why this shape

- **File-based queue** instead of Redis/SQLite because Chris can `cat queue.json` mid-run and see exactly what the agents are saying to each other. Pedagogy beats production-realism here.
- **Different models per agent** (Opus for planning, Haiku for worker) — genuinely justified for this use case. Taxonomy design and ordering benefit from a stronger model; summarization is exactly what Haiku is built for.
- **Separate processes** so Chris can `kill -9` one and watch the other handle the disappearance. Threads would hide this.
- **Filesystem-based input/output** keeps everything inspectable and avoids external service auth.

## Inbox format

The inbox accepts two file types — the planner detects which is which by extension:

- **`*.txt`**: one URL per line, blank lines and `#` comments ignored. Each URL becomes a fetch-and-process task.
- **`*.md`**: pre-saved article content (e.g., output from a Readability bookmarklet, a Pocket export, or just `curl > foo.md`). Each file becomes a process-existing-content task.

## Output format

Each processed article lands at `processed/<slug>.md` with YAML frontmatter:

```markdown
---
title: "Article title here"
source: "https://example.com/article" # or "local:filename.md"
processed_at: "2025-05-25T14:30:00"
tags: [machine-learning, infrastructure, opinion]
---

## Summary

Three-sentence summary written by Haiku.

## Key points

- Bullet
- Bullet
- Bullet
```

Slugs are derived from titles, lowercased, hyphen-separated, deduped with a numeric suffix if needed.

## Build order

Build in these phases. **After each phase, stop and have Chris run it himself before moving on.** This is a tutorial, not a delivery — he needs to feel each layer.

### Phase 0 — Scaffold

- `cd` into the project directory and run `uv init` to create `pyproject.toml` and `.venv/`.
- Add runtime deps: `uv add anthropic python-dotenv httpx trafilatura python-slugify pyyaml`.
  - `httpx` for fetching URLs
  - `trafilatura` for extracting article content from HTML (handles boilerplate, paywalls, byline detection — much better than hand-rolled BeautifulSoup)
  - `python-slugify` for output filename generation
  - `pyyaml` for frontmatter
- Add dev deps for the notebook workflow: `uv add --dev jupyter ipykernel`.
- Register the project's venv as a Jupyter kernel:
  ```
  uv run python -m ipykernel install --user --name reading-triager --display-name "reading-triager"
  ```
- Create `.env` (with `ANTHROPIC_API_KEY=...` placeholder) and `.gitignore` (must include `.env`, `.venv/`, `__pycache__/`, `*.ipynb_checkpoints/`, `logs/`, `queue.json`, `inbox/`, `processed/`).
- Create empty `planner.py`, `worker.py`, `harness.py`, `queue_lib.py`, `fetch_lib.py`, and these directories: `logs/`, `notebooks/`, `inbox/`, `processed/`.
- Drop a sample `inbox/sample_urls.txt` with 2–3 real URLs Chris picks (suggest something stable like Wikipedia articles or well-known blog posts) so there's content to work with from Phase 1 onward.
- Initial `git commit`.
- **Checkpoint**: `uv run python -c "import anthropic, trafilatura; print('ok')"` succeeds. `uv run jupyter lab` opens and the `reading-triager` kernel is selectable.

### Phase 1 — One agent talking to the API

- Build `planner.py` as a standalone script first. It should:
  - Load `ANTHROPIC_API_KEY` from `.env`.
  - Scan `inbox/` for `*.txt` and `*.md` files.
  - Build a description of what's in the inbox (URL list, content snippets from `.md` files).
  - Call Claude (Opus) with a system prompt explaining its job: design a tag taxonomy (5–10 tags) appropriate to this batch, then produce an ordered task list (one task per URL or per `.md` file).
  - Print the resulting taxonomy and task list to stdout.
- Do NOT yet write to the queue. Just print. Get the API call working first.
- The planner's prompt should encourage **coherent taxonomy** — e.g., if the inbox has 3 ML papers and 2 cooking blogs, that's `[machine-learning, cooking]` not `[AI, ml, neural-nets, food, recipes]`. This is the planner's actual job, and it's where the Opus model earns its keep.
- **Checkpoint**: `uv run python planner.py` reads the sample inbox and prints a sensible taxonomy + task list.

### Phase 2 — Queue file as a shared bus

- Define the queue schema in a comment at the top of `queue_lib.py`:
  ```
  {
    "tasks": [
      {
        "id": "t1",
        "task_type": "process_url" | "process_file" | "digest",
        "source": "https://..." | "inbox/article.md" | null,
        "status": "pending|in_progress|done|failed",
        "result": null,
        "error": null,
        "created_by": "planner",
        "completed_by": null,
        "claimed_at": null,
        "completed_at": null
      }
    ],
    "meta": {
      "iteration": 0,
      "started_at": "...",
      "taxonomy": ["tag1", "tag2", "..."]
    }
  }
  ```
- Write helper functions in `queue_lib.py`: `read_queue()`, `init_queue(taxonomy)`, `append_tasks(tasks)`, `claim_next_task(worker_id)`, `mark_done(task_id, result)`, `mark_failed(task_id, error)`. Use file locking (`fcntl.flock`) — this is the kind of detail Chris will appreciate seeing done right.
- Modify `planner.py` to call `init_queue()` with its taxonomy then `append_tasks()` with the task list, instead of printing.
- **Checkpoint**: Run planner, then `cat queue.json | jq .` and see the taxonomy in `meta` and structured tasks in `tasks`.

### Phase 3 — Worker agent

First build `fetch_lib.py` — a small module with two functions:
- `fetch_url(url) -> (title, content)`: uses `httpx` to GET the URL (with a reasonable User-Agent and 10s timeout), then `trafilatura.extract()` to pull clean article text. Returns the extracted title and body. Raises on network errors or empty extraction.
- `load_local(path) -> (title, content)`: reads a `.md` file, treats the first `# heading` as title (or filename as fallback), returns the rest as content.

Then build `worker.py`:
- Polls `queue.json` every 2 seconds.
- Claims the next `pending` task (atomically — set to `in_progress` under lock, with `claimed_at` timestamp and `completed_by` set to the worker's PID).
- Based on `task_type`:
  - `process_url`: call `fetch_url(source)`, then pass content to Haiku for summarization + tag selection from the taxonomy in `meta`.
  - `process_file`: call `load_local(source)`, same downstream handling.
  - `digest`: read all completed `process_*` tasks, pass their summaries to Haiku for an overall digest.
- The Haiku call uses **tool use** to force a structured response. Define a single tool (e.g., `record_summary`) with an input schema specifying `summary` (string), `key_points` (array of strings), and `tags` (array of strings, with the taxonomy values listed in the description so Haiku stays inside the vocabulary). Pass `tool_choice={"type": "tool", "name": "record_summary"}` to force the tool call. Parse the tool input from the response — no JSON-string parsing needed.
- Write the result to `processed/<slug>.md` with YAML frontmatter, set `result` in the queue to the output filepath, mark `done`.
- Loops.

**On structured output**: we're using tool use from the start rather than prompt-and-parse. Prompt-and-parse JSON works most of the time but breaks unpredictably — Haiku will occasionally wrap responses in markdown fences, add explanatory preamble, or hallucinate keys. Tool use enforces the schema at the SDK level. Mention this tradeoff briefly in comments so Chris understands *why* the tool-use scaffolding exists, but don't dwell on it.

- **Checkpoint**: Run planner once, then run worker in a separate terminal. Watch `queue.json` update in real time with `watch -n 1 'jq . queue.json'`, and see files appear in `processed/`.

### Phase 4 — The harness

This is the meat of the tutorial. Build `harness.py`:

- Spawns `planner.py` and `worker.py` as subprocesses using `subprocess.Popen`.
- Redirects their stdout/stderr to `logs/planner.log` and `logs/worker.log`.
- Enforces autonomy ceilings — **make these prominent constants at the top of the file**:
  ```python
  MAX_ITERATIONS = 5          # how many planner cycles before forced stop
  MAX_WALL_CLOCK_SEC = 120    # total runtime cap
  MAX_TASKS_IN_QUEUE = 20     # circuit breaker if planner runs amok
  REQUIRE_APPROVAL = True     # human-in-the-loop toggle
  ```
- If `REQUIRE_APPROVAL` is True, before the worker executes each task, print the task to the harness's stdout and wait for Chris to press Enter (or type `n` to skip).
- On Ctrl-C, terminate both subprocesses cleanly (SIGTERM, then SIGKILL after 3s if they don't die).
- Tail both log files to the harness's stdout with `[planner]` and `[worker]` prefixes — use a simple thread or `select` loop.
- **Checkpoint**: `uv run python harness.py` reads the inbox, runs planner then worker(s), shows both agents' output interleaved, prompts for approval per task, and stops cleanly on Ctrl-C or when ceilings hit. Files appear in `processed/` as tasks complete.

### Phase 5 — Break it on purpose

Once Phase 4 works, walk Chris through deliberately breaking things so he sees the failure modes. Add a few "junk" URLs to the inbox first to make some of these fire naturally:
- A dead URL (e.g., `https://example.com/this-does-not-exist-404`)
- A URL that times out (a slow site, or use httpx's timeout to force it)
- A URL pointing to a non-article (homepage, login page) where trafilatura returns nothing

Then walk through:

1. **Unbounded autonomy**: Set `MAX_ITERATIONS = 1000` and `REQUIRE_APPROVAL = False` with a big inbox (20+ URLs). Let it run wild for 30 seconds. Show him the cost in the Anthropic console afterward. This is the lesson that justifies the autonomy ceilings.
2. **Stuck claims**: Kill the worker mid-task with `kill <pid>`. Show that tasks stay `in_progress` forever — this is exactly why we added the `claimed_at` timestamp. Sketch (don't implement) a stale-claim recovery: any task `in_progress` for >5min gets reset to `pending`.
3. **Fetch failures**: The junk URLs above will fail in `fetch_lib`. Show how the worker handles them (marks `failed` with the error, continues to next task) vs. how a naive implementation would crash the whole worker. This is the case for explicit per-task error boundaries.
4. **Race condition**: Run two workers simultaneously (`uv run python worker.py &` twice). With `fcntl.flock`, they should cleanly split tasks. Then comment out the locking and re-run — show the race where both grab the same task. This is the case for atomic claim operations.

Each of these is a 5-minute exercise, not a re-implementation.

## Code style

- **Flat, sequential code over abstracted functions.** Chris has stated this preference. A long `main()` that reads top-to-bottom beats a dozen tiny helpers for tutorial code.
- **Comments explain *why*, not *what*.** `# claim under lock to prevent two workers grabbing the same task` is good. `# open the file` is noise.
- **No premature framework adoption.** No LangChain, no LangGraph, no CrewAI. Raw `anthropic` SDK only. The point is to understand what those frameworks are abstracting.
- **Print, don't log (mostly).** A `logging` setup is overkill for Phase 1–3. Introduce it only in the harness if it helps with the tail-multiple-files problem.

## Notebook usage

Notebooks live in `notebooks/` and are for exploration, prompt iteration, and post-run inspection. They are **not** where agents run from — subprocesses spawn from `.py` files. Use this split:

| Belongs in `.py` | Belongs in `.ipynb` |
|---|---|
| `planner.py`, `worker.py`, `harness.py` | Trying out a planner prompt before committing it |
| `queue_lib.py` (shared helpers) | Inspecting `queue.json` while the harness runs |
| Anything that gets imported or spawned | Post-mortem analysis of `logs/*.log` |
| | Phase 5 break-it-on-purpose experiments |

Create these notebooks alongside the corresponding phase:

- **`notebooks/01_planner_prompt_iteration.ipynb`** (Phase 1): cells for loading `.env`, calling Claude with different planner system prompts, and inspecting the taxonomy/task list output. Iterate here until the prompt produces good taxonomies on the sample inbox, then paste the winner into `planner.py`.
- **`notebooks/03a_fetch_smoke_test.ipynb`** (Phase 3): try `fetch_url` against a few different sites — a blog post, a Wikipedia article, a news site, a paywall, a dead URL. See what trafilatura does and doesn't handle. This is the right place to discover trafilatura's quirks before they bite the worker.
- **`notebooks/03b_queue_inspector.ipynb`** (Phase 3): load `queue.json`, pretty-print it, optionally render as a pandas DataFrame for `status` summary. Chris re-runs the cell while the worker is running to watch state evolve. Bonus: a cell that reads `processed/*.md` and renders the frontmatter as a table.
- **`notebooks/05_breaking_things.ipynb`** (Phase 5): one cell per failure mode from Phase 5. Cell 1 manually inserts a stuck `in_progress` task and shows it sitting there. Cell 2 reads `logs/worker.log` and pulls out the error lines. Cell 3 simulates a stale claim and shows what a recovery routine *would* do (without actually implementing it in the worker).

Notebook hygiene:
- **Clear outputs before committing.** Add `notebooks/*.ipynb` to git with cleared outputs, or use `nbstripout` if Chris wants automatic cleanup. Notebook diffs are painful otherwise.
- **Imports at the top.** Even in scratch notebooks, keep imports in cell 1 so re-running is predictable.
- **No magic state.** If a cell depends on a previous cell having been run, comment it. Notebooks where cells must run in a specific non-obvious order are a debugging nightmare.
- **`%load_ext autoreload` + `%autoreload 2`** in the first cell of any notebook that imports from `queue_lib.py` or the agent modules. This way edits to `.py` files show up in the notebook without restarting the kernel.

## Models and cost

- Planner: `claude-opus-4-7` (the current top model)
- Worker: `claude-haiku-4-5-20251001` (cheap, fast, fine for fake work)
- Set `max_tokens` low everywhere — 500 for the planner, 200 for the worker. This is a tutorial; tokens add up.
- Mention the cost trade-off out loud when you write the model strings — Chris cares about this.

## What NOT to do

- Do not build a web UI. Terminal only.
- Do not add a database. The JSON file is the point.
- Do not add retries or exponential backoff in Phases 1–4 — Phase 5 is where Chris discovers he needs them.
- Do not over-engineer error handling. A bare `except Exception as e: print(f"agent died: {e}"); raise` is fine for tutorial code. Verbose error taxonomies obscure the lesson.
- Do not write tests. This is exploratory code Chris will throw away.

## Handoff protocol

1. Read this file end to end before doing anything.
2. Confirm the project directory location with Chris.
3. Build Phase 0, stop, hand back to Chris to verify.
4. Same for each subsequent phase. **Do not run ahead.** This is paced learning, not delivery.
5. When Chris asks a "why" question, answer it before writing more code. The conceptual layer is the whole point.

## Open design questions for Chris (ask before Phase 4)

- Polling interval for the worker? (Suggest 2s.)
- Should the planner re-plan after the worker finishes a batch (e.g., handle a new URL someone dropped in the inbox mid-run), or one-shot? (Suggest one-shot for tutorial simplicity; mention "watcher mode" as a Phase 6 extension.)
- Approval mode default — approve every task, only network-fetching tasks, or none? (For real use, network-only is a reasonable default since URL fetches are the only "external action." But every-task is the better teaching default for Phase 4.)
- Digest task — auto-generate at the end of every run, or only on demand? (Suggest auto-generate when there are 3+ completed tasks. It's the most useful capstone output.)
- After Chris is comfortable: optional Phase 6 extension ideas — watcher mode (poll the inbox), digest scheduling (daily cron), Obsidian-compatible output format, multiple worker pool.