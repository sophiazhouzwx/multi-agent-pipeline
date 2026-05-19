"""Intent Router agent (Haiku).

Classifies a user message against a repo as either a question (read-only,
wants information) or an implementation request (wants code changes), and
rewrites it in canonical form for downstream agents.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.config import ROUTER_MODEL
from src.schemas import Intent

_ROUTER_INSTRUCTIONS = (
    "You classify user requests against a code repository and rewrite them in "
    "canonical form.\n\n"
    "Output fields:\n"
    "- kind: 'question' if the user wants information (explanations, locations, "
    "summaries, how-it-works). 'implement' if the user wants code changes "
    "(new features, bug fixes, refactors, additions, deletions).\n"
    "- canonical_request: a clear, self-contained restatement of what the user wants. "
    "Resolve pronouns and ambiguity. Be specific about scope when the user was vague.\n"
    "- rationale: ONE short sentence explaining your classification.\n"
)


router_agent = Agent(
    ROUTER_MODEL,
    output_type=Intent,
    instructions=_ROUTER_INSTRUCTIONS,
)


async def classify_intent(user_message: str) -> Intent:
    """Return the model's typed Intent for a free-form user message."""
    result = await router_agent.run(user_message)
    return result.output
