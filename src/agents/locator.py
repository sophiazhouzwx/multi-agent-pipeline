"""Locator agent (Sonnet).

Given a typed Intent and a Catalog, picks 1-5 files most relevant to the
user's request. Uses Sonnet (rather than Haiku) because the relevance
judgement benefits from broader reasoning across the catalog.

The returned paths are filtered against catalog membership so a model
hallucination can never produce a path that doesn't exist on disk.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src._retry import run_with_retry
from src.config import EVALUATOR_MODEL
from src.schemas import Catalog, Intent, LocatedFiles


_LOCATOR_INSTRUCTIONS = (
    "You select files from a code repository's catalog that are most relevant "
    "to a user request.\n\n"
    "You are given:\n"
    "- the user's Intent (kind, canonical_request, rationale)\n"
    "- the Catalog: each file has a path, a one-line purpose, and a list of public symbols\n\n"
    "Output:\n"
    "- paths: 1-5 file paths (use the EXACT 'path' string from the catalog, "
    "NEVER invent new paths). Order by relevance.\n"
    "- reasoning: a short paragraph explaining why these files were chosen.\n\n"
    "If the request is unclear or no files look relevant, return the closest "
    "plausible matches and explain the uncertainty in 'reasoning'."
)


locator_agent = Agent(
    EVALUATOR_MODEL,
    output_type=LocatedFiles,
    instructions=_LOCATOR_INSTRUCTIONS,
)


def _format_catalog_for_prompt(catalog: Catalog) -> str:
    """Render the catalog compactly for the locator prompt."""
    lines: list[str] = []
    for f in catalog.files:
        lines.append(f"- {f.path}")
        if f.purpose:
            lines.append(f"    purpose: {f.purpose}")
        if f.public_symbols:
            sym_names = ", ".join(s.name for s in f.public_symbols[:10])
            lines.append(f"    symbols: {sym_names}")
    return "\n".join(lines)


async def locate(catalog: Catalog, intent: Intent) -> LocatedFiles:
    """Return the 1-5 files most relevant to ``intent``.

    The model's output is filtered against the catalog so any hallucinated
    paths are dropped before the result reaches downstream agents.
    """
    prompt = (
        f"Intent kind: {intent.kind}\n"
        f"Canonical request: {intent.canonical_request}\n"
        f"Rationale: {intent.rationale}\n\n"
        f"Catalog ({len(catalog.files)} files):\n{_format_catalog_for_prompt(catalog)}"
    )
    result = await run_with_retry(
        lambda: locator_agent.run(prompt), label="locator"
    )
    valid_paths = {f.path for f in catalog.files}
    filtered = [p for p in result.output.paths if p in valid_paths]
    return LocatedFiles(paths=filtered, reasoning=result.output.reasoning)
