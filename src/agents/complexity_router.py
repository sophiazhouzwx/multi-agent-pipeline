"""Complexity Router (Haiku).

Distinct from ``src/agents/router.py`` (which classifies *intent*: question
vs implement), this router classifies the *complexity* of an implement
request so the orchestrator can pick the cheapest generator tier that's
still adequate:

  easy   -> Haiku
  medium -> Sonnet
  hard   -> Opus

This is the cost-vs-quality lever: we pay one cheap Haiku call up front
to potentially save ~10x on the generator.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.config import ROUTER_MODEL
from src.schemas import Intent, TaskComplexity


_COMPLEXITY_INSTRUCTIONS = (
    "You classify the complexity of an implementation request against a "
    "code repository to choose the right model tier.\n\n"
    "Tiers:\n"
    "- easy: trivial mechanical change. New flag with no validation, "
    "rename a symbol, fix a typo, add a one-line guard. Single file. "
    "No new abstractions.\n"
    "- medium: a small feature or focused refactor. Touches 1-3 files, "
    "involves real logic but no deep architecture decisions. Adding a CLI "
    "command, adding a new endpoint, restructuring a function.\n"
    "- hard: cross-cutting change, new abstraction, multi-file refactor, "
    "or something requiring careful reasoning about correctness/edge cases. "
    "Adding a new agent, refactoring an algorithm, adding a feature with "
    "non-trivial state.\n\n"
    "Output:\n"
    "- tier: 'easy' | 'medium' | 'hard'\n"
    "- reasoning: one sentence explaining the classification."
)


complexity_router_agent = Agent(
    ROUTER_MODEL,
    output_type=TaskComplexity,
    instructions=_COMPLEXITY_INSTRUCTIONS,
)


async def classify_complexity(intent: Intent) -> TaskComplexity:
    """Return the complexity tier for an implementation intent."""
    prompt = (
        f"Canonical request: {intent.canonical_request}\n"
        f"Rationale: {intent.rationale}"
    )
    result = await complexity_router_agent.run(prompt)
    return result.output
