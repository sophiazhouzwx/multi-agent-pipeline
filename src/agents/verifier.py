"""Verifier agent factory.

Each verifier independently reviews a ChangeProposal and returns a typed
``ProposalReview`` with verdict + confidence + reasoning. The panel in
``src/pipeline/verifier_panel.py`` fans out across multiple verifier
models and aggregates their reviews into a ``PanelVerdict``.

Verifiers are stateless and constructed per-model from ``VERIFIER_MODELS``.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.schemas import ProposalReview


_VERIFIER_INSTRUCTIONS = (
    "You review a proposed code change against the original user request, "
    "deciding whether to approve, reject, or suggest improvements.\n\n"
    "Input you receive:\n"
    "- The canonical user request.\n"
    "- The approved ChangePlan (summary + steps + affected files).\n"
    "- The proposed FileEdits: for each file, the original content (if any) "
    "and the proposed new content.\n\n"
    "Output (ProposalReview):\n"
    "- verdict: 'approve' (faithful to the request, no obvious bugs, no scope "
    "creep), 'reject' (has bugs, breaks something, doesn't implement the "
    "request, or introduces serious problems), or 'suggest' (works but has "
    "minor issues — style, missing edge case, a better approach).\n"
    "- confidence: 0.0-1.0, how sure you are of your verdict.\n"
    "- reasoning: a clear paragraph explaining your verdict. Cite specific "
    "files and line numbers (e.g. `src/foo.py:42`) when relevant.\n"
    "- suggestions: concrete improvements as a list of short strings (only "
    "for 'suggest' or 'reject' verdicts; leave empty for 'approve').\n\n"
    "Rules:\n"
    "- Focus on correctness, scope match, and safety. Don't reject for purely "
    "stylistic reasons — use 'suggest' for those.\n"
    "- Don't invent issues. If the proposal is straightforward and matches "
    "the request, approve it with high confidence.\n"
    "- Leave model_id empty — the panel fills it in.\n"
    "- Be independent. You are one of multiple reviewers; don't try to guess "
    "what others will say."
)


def make_verifier(model_id: str) -> Agent:
    """Construct a fresh verifier Agent for the given model string."""
    return Agent(
        model_id,
        output_type=ProposalReview,
        instructions=_VERIFIER_INSTRUCTIONS,
    )
