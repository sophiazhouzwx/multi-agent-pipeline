"""1-line file purpose summaries via Claude Haiku 4.5.

Used by the indexer on first run + any time a file's content hash changes.
Bounded concurrency keeps the Anthropic proxy happy on large repos.
"""

from __future__ import annotations

import asyncio

from pydantic_ai import Agent

from src.config import ROUTER_MODEL


_SUMMARIZER_INSTRUCTIONS = (
    "You write a SINGLE-SENTENCE purpose line for a source file in a codebase. "
    "Given the file path and its contents, describe what role this file plays "
    "in the project — what it provides, not how it works. "
    "Constraints: at most ~120 characters; one sentence; start directly with the "
    "role (no leading 'This file' / 'Module that'). "
    "Output only the sentence, no quotes, no prefix."
)


_MAX_INPUT_CHARS = 8000


def make_summarizer_agent() -> Agent:
    """Construct a fresh summarizer agent. Tests can use ``agent.override``."""
    return Agent(
        ROUTER_MODEL,
        output_type=str,
        instructions=_SUMMARIZER_INSTRUCTIONS,
    )


# Module-level singleton so callers don't pay agent-construction cost per call.
summarizer_agent: Agent = make_summarizer_agent()


def _truncate(source: str) -> str:
    if len(source) <= _MAX_INPUT_CHARS:
        return source
    return source[:_MAX_INPUT_CHARS] + "\n...[truncated]"


async def summarize_file(path_rel: str, source: str) -> str:
    """Return a 1-line purpose for a single file."""
    prompt = f"File: {path_rel}\n\n```\n{_truncate(source)}\n```"
    result = await summarizer_agent.run(prompt)
    text = (result.output or "").strip().splitlines()
    return (text[0] if text else "").strip()[:200]


async def summarize_batch(
    items: list[tuple[str, str]], concurrency: int = 5
) -> list[str]:
    """Summarize many files with bounded concurrency. Preserves input order."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(path_rel: str, source: str) -> str:
        async with sem:
            return await summarize_file(path_rel, source)

    return await asyncio.gather(*(_one(p, s) for p, s in items))
