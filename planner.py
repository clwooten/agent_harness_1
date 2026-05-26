"""Planner agent (Phase 1).

Scans inbox/, asks Opus to design a tag taxonomy and ordered task list,
prints the result. Phase 1 only prints — Phase 2 will swap the print
for a write into queue.json via queue_lib.
"""

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# Opus is the planner because taxonomy design + ordering benefits from a
# stronger model. It is ~15x the cost of Haiku per token; we keep
# max_tokens tight to bound the bill.
MODEL = "claude-opus-4-7"
MAX_TOKENS = 500

INBOX = Path("inbox")


def scan_inbox() -> tuple[list[str], list[tuple[str, str]]]:
    """Return (urls, md_snippets). md_snippets is [(path, first_500_chars), ...]."""
    urls: list[str] = []
    for f in sorted(INBOX.glob("*.txt")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    md_snippets: list[tuple[str, str]] = []
    for f in sorted(INBOX.glob("*.md")):
        # 500 chars is enough for the planner to infer topic without
        # spending the worker's content budget here.
        md_snippets.append((str(f), f.read_text()[:500].rstrip()))

    return urls, md_snippets


def build_manifest(urls: list[str], md_snippets: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    if urls:
        lines.append("URLs to fetch and process:")
        lines.extend(f"  - {u}" for u in urls)
    if md_snippets:
        if lines:
            lines.append("")
        lines.append("Local markdown files (already saved):")
        for path, snippet in md_snippets:
            lines.append(f"  - {path}")
            lines.append(f"    snippet: {snippet!r}")
    return "\n".join(lines) if lines else "(inbox is empty)"


SYSTEM_PROMPT = """You are the planner for a two-agent reading-queue triage system.

You receive a manifest of items to process: URLs to fetch and pre-saved markdown files.
Your job has two parts:

1. Design a COHERENT tag taxonomy of 5-10 tags appropriate to this batch of content.
   Prefer broad consistent tags over many narrow ones. If the inbox has 3 ML papers and
   2 cooking blogs, that's ["machine-learning", "cooking"] — NOT ["AI", "ml",
   "neural-nets", "food", "recipes"]. Tags are lowercase, hyphen-separated.

2. Produce an ORDERED task list. One task per URL or per markdown file. If there are
   3 or more content tasks, append a final "digest" task that will summarize them all.

Respond with ONLY a JSON object (no prose, no code fences) with this shape:
{
  "taxonomy": ["tag-1", "tag-2", ...],
  "tasks": [
    {"task_type": "process_url",  "source": "https://..."},
    {"task_type": "process_file", "source": "inbox/foo.md"},
    {"task_type": "digest",       "source": null}
  ]
}"""


def main() -> None:
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set. Put it in .env at the project root.")

    urls, md_snippets = scan_inbox()
    manifest = build_manifest(urls, md_snippets)

    print("=== Inbox manifest ===")
    print(manifest)
    print()

    client = Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f"Inbox manifest:\n\n{manifest}\n\n"
                              "Design the taxonomy and the ordered task list."}],
    )

    print("=== Planner response ===")
    for block in resp.content:
        if block.type == "text":
            print(block.text)
    print()
    print(f"=== Usage: in={resp.usage.input_tokens} tokens, "
          f"out={resp.usage.output_tokens} tokens "
          f"(stop_reason={resp.stop_reason}) ===")


if __name__ == "__main__":
    main()
