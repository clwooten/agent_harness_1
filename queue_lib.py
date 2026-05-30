"""Shared queue helpers for the planner and worker.

The queue is a single JSON file on disk (`queue.json` at project root).
Every mutation goes through fcntl.flock on the file handle so two
workers — or a worker plus a planner re-plan — can't trample each
other's writes. This is intentionally a file, not Redis/SQLite:
`cat queue.json | jq .` mid-run is the primary debugging surface for
the tutorial.

Schema (current):

    {
      "meta": {
        "iteration":  int,                 # bumped each replan cycle
        "started_at": "ISO-8601 string",
        "taxonomy":   ["tag-1", "tag-2", ...]
      },
      "tasks": [
        {
          "id":            "t1",                                  # short, greppable
          "task_type":     "process_url" | "process_file" | "digest",
          "source":        "https://..." | "inbox/foo.md" | null,
          "status":        "pending" | "in_progress" | "done" | "failed",
          "result":        null | "processed/foo.md",             # on success
          "error":         null | "error string",                 # on failure
          "created_by":    "planner",
          "completed_by":  null | "worker-<pid>",
          "claimed_at":    null | "ISO-8601 string",
          "completed_at":  null | "ISO-8601 string"
        },
        ...
      ]
    }

`status` is a plain string rather than an enum / Literal — fine for
the tutorial. If we ever rework the schema mid-stream, the simplest
recovery is `rm queue.json` and re-run the planner. No version field.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

QUEUE_PATH = Path("queue.json")

VALID_TASK_TYPES = {"process_url", "process_file", "digest"}
VALID_STATUSES = {"pending", "in_progress", "done", "failed"}


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

@contextmanager
def _locked(mode: str = "r+") -> Iterator[Any]:
    """Open queue.json under an exclusive flock.

    Always use this for read-modify-write cycles. A bare `json.load` +
    `json.dump` is fine in a single process but races the moment a second
    worker shows up — Phase 5 deliberately demonstrates that race.
    """
    with open(QUEUE_PATH, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _now() -> str:
    # Bare ISO; no timezone shenanigans. Local time is fine for a tutorial.
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def read_queue() -> dict[str, Any]:
    """Return the full queue dict. Cheap to call; no lock needed for a snapshot."""
    with open(QUEUE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Planner-side writes
# ---------------------------------------------------------------------------

def init_queue(taxonomy: list[str]) -> None:
    """Create (or replace) queue.json with empty tasks and the given taxonomy.

    Phase 2 is one-shot: every planner run starts fresh. Watcher mode
    (Phase 6) would instead bump `iteration` and append.
    """
    payload = {
        "meta": {
            "iteration": 0,
            "started_at": _now(),
            "taxonomy": list(taxonomy),
        },
        "tasks": [],
    }
    # Write under lock so a worker that's already polling can't see a
    # half-written file.
    with open(QUEUE_PATH, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(payload, f, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def append_tasks(tasks: list[dict[str, Any]]) -> list[str]:
    """Append tasks to the queue. Assigns IDs, fills defaults. Returns IDs assigned.

    Each input task dict must have at least `task_type` and `source`. Other
    fields are filled in here. ID format is t1, t2, ... — sequence continues
    past whatever's already in the queue.
    """
    assigned: list[str] = []
    with _locked() as f:
        data = json.load(f)

        # Continue numbering past the highest existing id. Defensive in case
        # of deletions: scan, don't just count.
        existing_ids = [t["id"] for t in data["tasks"] if t["id"].startswith("t")]
        next_n = 1 + max((int(i[1:]) for i in existing_ids), default=0)

        for t in tasks:
            if t["task_type"] not in VALID_TASK_TYPES:
                raise ValueError(f"unknown task_type: {t['task_type']!r}")
            task_id = f"t{next_n}"
            next_n += 1
            data["tasks"].append({
                "id": task_id,
                "task_type": t["task_type"],
                "source": t.get("source"),
                "status": "pending",
                "result": None,
                "error": None,
                "created_by": "planner",
                "completed_by": None,
                "claimed_at": None,
                "completed_at": None,
            })
            assigned.append(task_id)

        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)

    return assigned


# ---------------------------------------------------------------------------
# Worker-side writes
# ---------------------------------------------------------------------------

def claim_next_task(worker_id: str) -> dict[str, Any] | None:
    """Atomically claim the first pending task. Returns the task dict, or None.

    The claim flips status pending → in_progress, stamps claimed_at, and
    records completed_by (used here as 'claimed_by' — the field name is
    forward-looking; whoever claims usually also completes).
    """
    with _locked() as f:
        data = json.load(f)
        for task in data["tasks"]:
            if task["status"] == "pending":
                task["status"] = "in_progress"
                task["claimed_at"] = _now()
                task["completed_by"] = worker_id
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
                return task
        return None


def mark_done(task_id: str, result: str | None) -> None:
    """Mark a task as done. `result` is typically the output filepath."""
    _finalize(task_id, status="done", result=result, error=None)


def mark_failed(task_id: str, error: str) -> None:
    """Mark a task as failed. `error` is a short human-readable string."""
    _finalize(task_id, status="failed", result=None, error=error)


def _finalize(task_id: str, *, status: str, result: str | None, error: str | None) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    with _locked() as f:
        data = json.load(f)
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["status"] = status
                task["result"] = result
                task["error"] = error
                task["completed_at"] = _now()
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
                return
        raise KeyError(f"task not found: {task_id!r}")
