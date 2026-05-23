"""Judge agent (Haiku).

Reads N independent ProposalReview objects and decides the consensus call
for the panel. Kept as a separate agent (rather than a hardcoded voting
rule) so the consensus can be reasoned about — e.g. weighting a high-
confidence reject more heavily than a low-confidence approve.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src._retry import run_with_retry
from src.config import JUDGE_MODEL
from src.schemas import JudgeDecision, ProposalReview


_JUDGE_INSTRUCTIONS = (
    "You consume independent reviews of a proposed code change and decide "
    "the consensus call.\n\n"
    "Output (JudgeDecision):\n"
    "- consensus_verdict: 'approve', 'reject', or 'suggest'\n"
    "- consensus_confidence: 0.0-1.0, your confidence in the consensus call\n"
    "- reasoning: one short paragraph explaining your call\n\n"
    "Consensus rules:\n"
    "- If ALL reviewers approve -> approve (confidence = avg of theirs).\n"
    "- If ANY reviewer rejects with confidence >= 0.7 AND their reasoning "
    "names a concrete issue -> consensus is reject (defer to the strongest "
    "concern).\n"
    "- If reviewers are split (e.g. approve + reject + suggest) -> consensus "
    "is suggest (the disagreement itself warrants user attention).\n"
    "- If majority approve and the rejecter has low confidence -> approve, "
    "but flag the dissent in your reasoning.\n"
    "- All-suggest -> suggest.\n\n"
    "Be brief and decisive. Your reasoning should reference specific reviewer "
    "concerns by their (1-indexed) reviewer number."
)


judge_agent: Agent = Agent(
    JUDGE_MODEL,
    output_type=JudgeDecision,
    instructions=_JUDGE_INSTRUCTIONS,
    retries=3,
)


def _format_reviews(reviews: list[ProposalReview]) -> str:
    blocks: list[str] = []
    for i, r in enumerate(reviews, 1):
        suggestion_block = ""
        if r.suggestions:
            suggestion_block = "\nSuggestions:\n" + "\n".join(
                f"  - {s}" for s in r.suggestions
            )
        blocks.append(
            f"### Reviewer {i} ({r.model_id})\n"
            f"Verdict: {r.verdict}\n"
            f"Confidence: {r.confidence}\n"
            f"Reasoning: {r.reasoning}"
            f"{suggestion_block}"
        )
    return "\n\n".join(blocks)


async def judge(reviews: list[ProposalReview], request: str) -> JudgeDecision:
    """Decide the consensus across N independent reviews."""
    prompt = (
        f"Original request: {request}\n\n"
        f"Independent reviews ({len(reviews)}):\n\n{_format_reviews(reviews)}"
    )
    result = await run_with_retry(
        lambda: judge_agent.run(prompt), label="judge"
    )
    return result.output
