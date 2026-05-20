"""Hermetic tests for the verifier panel.

Stubs every verifier model + the judge agent via TestModel so the panel
can be exercised end-to-end without API calls.
"""

from __future__ import annotations

from contextlib import ExitStack

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.judge import judge_agent
from src.config import VERIFIER_MODELS
from src.pipeline.verifier_panel import (
    _VERIFIERS,
    agreement_score,
    verify_proposal,
)
from src.schemas import (
    ChangePlan,
    ChangeProposal,
    FileEdit,
    Intent,
    ProposalReview,
)


def _intent() -> Intent:
    return Intent(
        kind="implement",
        canonical_request="Add a --json flag to the ask command.",
        rationale="User wants machine-readable output.",
    )


def _proposal() -> ChangeProposal:
    return ChangeProposal(
        plan=ChangePlan(
            summary="Add --json flag to ask",
            affected_files=["src/cli.py"],
            steps=["wire the flag", "emit json"],
        ),
        edits=[
            FileEdit(
                path="src/cli.py",
                new_content="# updated\n",
                rationale="added flag",
            )
        ],
    )


def _review_payload(verdict: str, confidence: float, reasoning: str = "OK") -> dict:
    return {
        "model_id": "",
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "suggestions": [],
    }


def _judge_payload(verdict: str, confidence: float, reasoning: str = "panel agrees") -> dict:
    return {
        "consensus_verdict": verdict,
        "consensus_confidence": confidence,
        "reasoning": reasoning,
    }


# ---------------------------------------------------------------------------
# Agreement-score helper
# ---------------------------------------------------------------------------
def test_agreement_score_all_agree():
    reviews = [
        ProposalReview(model_id="a", verdict="approve", confidence=0.9, reasoning="r"),
        ProposalReview(model_id="b", verdict="approve", confidence=0.8, reasoning="r"),
        ProposalReview(model_id="c", verdict="approve", confidence=0.7, reasoning="r"),
    ]
    assert agreement_score(reviews) == 1.0


def test_agreement_score_all_disagree():
    reviews = [
        ProposalReview(model_id="a", verdict="approve", confidence=0.9, reasoning="r"),
        ProposalReview(model_id="b", verdict="reject", confidence=0.9, reasoning="r"),
        ProposalReview(model_id="c", verdict="suggest", confidence=0.9, reasoning="r"),
    ]
    assert agreement_score(reviews) == 0.0


def test_agreement_score_partial():
    reviews = [
        ProposalReview(model_id="a", verdict="approve", confidence=0.9, reasoning="r"),
        ProposalReview(model_id="b", verdict="approve", confidence=0.9, reasoning="r"),
        ProposalReview(model_id="c", verdict="reject", confidence=0.9, reasoning="r"),
    ]
    # 1 pair matches (a,b) out of 3 total -> 1/3
    assert abs(agreement_score(reviews) - (1 / 3)) < 1e-9


# ---------------------------------------------------------------------------
# End-to-end panel
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_panel_unanimous_approve():
    review = _review_payload("approve", 0.9, "looks correct")
    judgment = _judge_payload("approve", 0.9, "all three approved")

    with ExitStack() as stack:
        for agent in _VERIFIERS.values():
            stack.enter_context(agent.override(model=TestModel(custom_output_args=review)))
        stack.enter_context(judge_agent.override(model=TestModel(custom_output_args=judgment)))

        verdict = await verify_proposal(_intent(), _proposal(), {"src/cli.py": "# old\n"})

    assert verdict.consensus_verdict == "approve"
    assert verdict.consensus_confidence == 0.9
    assert verdict.agreement_score == 1.0
    assert len(verdict.reviews) == len(VERIFIER_MODELS)
    # Every review got its model_id stamped by the panel.
    assert sorted(r.model_id for r in verdict.reviews) == sorted(VERIFIER_MODELS)


@pytest.mark.asyncio
async def test_panel_stamps_model_ids():
    """Each verifier sees the same prompt but the panel must attribute the
    reviews to the right model."""
    review = _review_payload("suggest", 0.5)
    judgment = _judge_payload("suggest", 0.5, "all suggested")

    with ExitStack() as stack:
        for agent in _VERIFIERS.values():
            stack.enter_context(agent.override(model=TestModel(custom_output_args=review)))
        stack.enter_context(judge_agent.override(model=TestModel(custom_output_args=judgment)))

        verdict = await verify_proposal(_intent(), _proposal(), {"src/cli.py": "# old\n"})

    received = {r.model_id for r in verdict.reviews}
    assert received == set(VERIFIER_MODELS)


@pytest.mark.asyncio
async def test_panel_records_judge_reasoning():
    review = _review_payload("approve", 0.9)
    judgment = _judge_payload(
        "approve", 0.85, "two confident approves, one suggest with minor concerns"
    )

    with ExitStack() as stack:
        for agent in _VERIFIERS.values():
            stack.enter_context(agent.override(model=TestModel(custom_output_args=review)))
        stack.enter_context(judge_agent.override(model=TestModel(custom_output_args=judgment)))

        verdict = await verify_proposal(_intent(), _proposal(), {"src/cli.py": "# old\n"})

    assert "two confident approves" in verdict.judge_reasoning
    assert verdict.consensus_confidence == 0.85
