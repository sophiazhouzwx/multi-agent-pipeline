"""Cross-tier verifier panel.

Fans out a ChangeProposal to every model in ``config.VERIFIER_MODELS`` in
parallel, collects their typed ProposalReviews, then asks the judge agent
for a consensus call. Returns a typed ``PanelVerdict``.

The panel is *per-proposal*: one vote per verifier covering ALL edits in
the proposal as a unit. Per-file voting was considered and rejected for
cost reasons (3 × N calls instead of 3).

Verifier agents are constructed once per process at import time and cached
in ``_VERIFIERS``. Tests stub them via ``agent.override(model=TestModel(...))``.
"""

from __future__ import annotations

import asyncio

from pydantic_ai import Agent

from src.agents.judge import judge
from src.agents.verifier import make_verifier
from src.config import VERIFIER_MODELS
from src.schemas import (
    ChangeProposal,
    Intent,
    PanelVerdict,
    ProposalReview,
)


# Module-level cache so tests can override each verifier's model.
_VERIFIERS: dict[str, Agent] = {m: make_verifier(m) for m in VERIFIER_MODELS}


def _format_payload(
    intent: Intent,
    proposal: ChangeProposal,
    original_contents: dict[str, str],
) -> str:
    """Render the proposal compactly for the reviewer prompt."""
    sections: list[str] = [
        f"Canonical request: {intent.canonical_request}",
        "",
        "Approved plan:",
        f"  Summary: {proposal.plan.summary}",
        "  Steps:",
    ]
    for i, step in enumerate(proposal.plan.steps, 1):
        sections.append(f"    {i}. {step}")
    sections.append("")
    sections.append("Proposed edits:")
    for edit in proposal.edits:
        original = original_contents.get(edit.path, "")
        status = "NEW FILE" if not original else "MODIFY"
        sections.append("")
        sections.append(f"=== {status}: `{edit.path}` ===")
        sections.append(f"Rationale: {edit.rationale}")
        if original:
            sections.append("--- ORIGINAL ---")
            sections.append("```")
            sections.append(original)
            sections.append("```")
        sections.append("--- PROPOSED NEW CONTENT ---")
        sections.append("```")
        sections.append(edit.new_content)
        sections.append("```")
    return "\n".join(sections)


def agreement_score(reviews: list[ProposalReview]) -> float:
    """Pairwise verdict agreement: 1.0 = all match, 0.0 = all disagree.

    With 3 reviewers there are 3 pairs; with N reviewers there are
    C(N,2) = N*(N-1)/2 pairs.
    """
    if len(reviews) < 2:
        return 1.0
    verdicts = [r.verdict for r in reviews]
    pairs = 0
    agreements = 0
    for i in range(len(verdicts)):
        for j in range(i + 1, len(verdicts)):
            pairs += 1
            if verdicts[i] == verdicts[j]:
                agreements += 1
    return agreements / pairs if pairs else 1.0


async def verify_proposal(
    intent: Intent,
    proposal: ChangeProposal,
    original_contents: dict[str, str],
) -> PanelVerdict:
    """Run the panel: parallel reviewers + judge -> typed PanelVerdict."""
    payload = _format_payload(intent, proposal, original_contents)

    async def _review(model_id: str, agent: Agent) -> ProposalReview:
        result = await agent.run(payload)
        # Stamp the model_id (reviewer doesn't know its own identity).
        return result.output.model_copy(update={"model_id": model_id})

    reviews = await asyncio.gather(
        *(_review(m, a) for m, a in _VERIFIERS.items())
    )

    judgment = await judge(list(reviews), intent.canonical_request)

    return PanelVerdict(
        reviews=list(reviews),
        consensus_verdict=judgment.consensus_verdict,
        consensus_confidence=judgment.consensus_confidence,
        agreement_score=agreement_score(list(reviews)),
        judge_reasoning=judgment.reasoning,
    )
