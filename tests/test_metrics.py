"""Hermetic tests for the metrics module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.metrics.report import (
    _percentile,
    apply_outcome_stats,
    compute_report,
    gate_action_counts,
    latency_stats,
    panel_agreement_stats,
    reviewer_verdict_counts,
    runs_by_kind_status,
)
from src.schemas import (
    ApplyResult,
    ExecutionResult,
    GateDecision,
    Intent,
    PanelVerdict,
    ProposalReview,
)
from src.storage import db, persist


@pytest.fixture
def tmp_db(tmp_path: Path):
    db.use_engine_for_url(f"sqlite:///{tmp_path / 'test.db'}")
    db.init_db()
    yield
    db.reset_engine()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------
def test_percentile_empty():
    assert _percentile([], 0.5) == 0


def test_percentile_basic():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert _percentile(values, 0.5) == 60
    assert _percentile(values, 0.95) == 100


# ---------------------------------------------------------------------------
# End-to-end report
# ---------------------------------------------------------------------------
def _save_ask(status: str = "success", runtime_ms: int = 1000) -> None:
    started = _now()
    persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="ask",
        request="q",
        status=status,
        started_at=started,
        ended_at=started + timedelta(milliseconds=runtime_ms),
        intent=Intent(kind="question", canonical_request="q", rationale="r"),
        gates=[GateDecision(gate="intent", action="confirm")],
    )


def _save_implement_success() -> int:
    started = _now()
    return persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="add x",
        status="success",
        started_at=started,
        intent=Intent(kind="implement", canonical_request="add x", rationale="r"),
        verification=PanelVerdict(
            reviews=[
                ProposalReview(model_id="anthropic:opus", verdict="approve", confidence=0.9, reasoning=""),
                ProposalReview(model_id="anthropic:sonnet", verdict="approve", confidence=0.8, reasoning=""),
                ProposalReview(model_id="anthropic:haiku", verdict="suggest", confidence=0.7, reasoning=""),
            ],
            consensus_verdict="approve",
            consensus_confidence=0.85,
            agreement_score=1 / 3,
            judge_reasoning="ok",
        ),
        apply_result=ApplyResult(
            branch_name="agent/x",
            applied_commit="abc123",
            test_result=ExecutionResult(
                success=True, stdout="", stderr="", exit_code=0,
                runtime_ms=1, timed_out=False, error_category="none",
            ),
            rolled_back=False,
            rollback_reason="",
        ),
        gates=[
            GateDecision(gate="intent", action="confirm"),
            GateDecision(gate="plan", action="confirm"),
            GateDecision(gate="apply", action="confirm"),
        ],
    )


def _save_implement_rolled_back() -> int:
    started = _now()
    return persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="bad",
        status="rolled_back",
        started_at=started,
        intent=Intent(kind="implement", canonical_request="bad", rationale="r"),
        apply_result=ApplyResult(
            branch_name="agent/bad",
            applied_commit=None,
            test_result=ExecutionResult(
                success=False, stdout="", stderr="fail", exit_code=1,
                runtime_ms=1, timed_out=False, error_category="assertion",
            ),
            rolled_back=True,
            rollback_reason="tests failed",
        ),
        gates=[
            GateDecision(gate="intent", action="confirm"),
            GateDecision(gate="plan", action="edit", edited_payload="more"),
            GateDecision(gate="apply", action="confirm"),
        ],
    )


def test_report_empty_db(tmp_db):
    r = compute_report()
    assert r["total_runs"] == 0
    assert r["by_kind_status"] == {}
    assert r["latency"]["count"] == 0
    assert r["apply_outcomes"]["pass_rate_pct"] == 0


def test_runs_by_kind_status(tmp_db):
    _save_ask("success")
    _save_ask("aborted_intent")
    _save_implement_success()
    _save_implement_rolled_back()

    with db.get_session() as s:
        out = runs_by_kind_status(s)
    assert out[("ask", "success")] == 1
    assert out[("ask", "aborted_intent")] == 1
    assert out[("implement", "success")] == 1
    assert out[("implement", "rolled_back")] == 1


def test_gate_action_counts(tmp_db):
    _save_implement_success()
    _save_implement_rolled_back()
    with db.get_session() as s:
        out = gate_action_counts(s)
    # Two implements, each contributes intent+plan+apply
    assert out[("intent", "confirm")] == 2
    assert out[("plan", "confirm")] == 1
    assert out[("plan", "edit")] == 1
    assert out[("apply", "confirm")] == 2


def test_reviewer_verdict_counts(tmp_db):
    _save_implement_success()  # 2 approve + 1 suggest
    with db.get_session() as s:
        out = reviewer_verdict_counts(s)
    assert out[("anthropic:opus", "approve")] == 1
    assert out[("anthropic:sonnet", "approve")] == 1
    assert out[("anthropic:haiku", "suggest")] == 1


def test_apply_outcome_stats(tmp_db):
    _save_implement_success()
    _save_implement_rolled_back()
    with db.get_session() as s:
        out = apply_outcome_stats(s)
    assert out["attempted"] == 2
    assert out["applied"] == 1
    assert out["rolled_back"] == 1
    assert out["pass_rate_pct"] == 50


def test_panel_agreement_only_counts_runs_with_verification(tmp_db):
    _save_ask("success")  # no verification
    _save_implement_success()  # has verification, agreement = 1/3
    with db.get_session() as s:
        out = panel_agreement_stats(s)
    assert out["n"] == 1
    assert abs(out["mean"] - 1 / 3) < 1e-9


def test_latency_filters_to_success(tmp_db):
    _save_ask("success")
    _save_ask("aborted_intent")
    with db.get_session() as s:
        out = latency_stats(s, status_filter="success")
    assert out["count"] == 1
