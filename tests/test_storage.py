"""Hermetic tests for the SQLite storage layer.

Each test gets an isolated temp DB via the ``tmp_db`` fixture — no contact
with the real ``runs.db`` at the project root.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import select

from src.schemas import (
    ApplyResult,
    ExecutionResult,
    GateDecision,
    Intent,
    PanelVerdict,
    ProposalReview,
)
from src.storage import db, persist
from src.storage.models import GateRow, ReviewRow, RunRow


@pytest.fixture
def tmp_db(tmp_path: Path):
    db.use_engine_for_url(f"sqlite:///{tmp_path / 'test.db'}")
    db.init_db()
    yield
    db.reset_engine()


def _started_at() -> datetime:
    return datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Smoke: save the minimum-viable run
# ---------------------------------------------------------------------------
def test_save_minimal_ask_run(tmp_db):
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="ask",
        request="hello?",
        status="success",
        started_at=_started_at(),
        ended_at=_started_at(),
    )
    assert run_id is not None

    with db.get_session() as s:
        rows = s.exec(select(RunRow)).all()
    assert len(rows) == 1
    assert rows[0].kind == "ask"
    assert rows[0].request == "hello?"
    assert rows[0].status == "success"
    assert rows[0].applied_commit is None


# ---------------------------------------------------------------------------
# Gate child rows
# ---------------------------------------------------------------------------
def test_save_run_with_gate_decisions(tmp_db):
    gates = [
        GateDecision(gate="intent", action="confirm"),
        GateDecision(gate="plan", action="edit", edited_payload="also handle empty input"),
        GateDecision(gate="apply", action="confirm"),
    ]
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="add a flag",
        status="success",
        started_at=_started_at(),
        gates=gates,
    )

    with db.get_session() as s:
        gate_rows = s.exec(
            select(GateRow).where(GateRow.run_id == run_id).order_by(GateRow.ordinal)
        ).all()

    assert [g.gate for g in gate_rows] == ["intent", "plan", "apply"]
    assert [g.action for g in gate_rows] == ["confirm", "edit", "confirm"]
    assert gate_rows[1].edited_payload == "also handle empty input"
    assert [g.ordinal for g in gate_rows] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Review child rows + denormalised consensus fields
# ---------------------------------------------------------------------------
def test_save_run_with_verification(tmp_db):
    verification = PanelVerdict(
        reviews=[
            ProposalReview(
                model_id="anthropic:claude-opus-4-6",
                verdict="approve",
                confidence=0.9,
                reasoning="Looks correct",
            ),
            ProposalReview(
                model_id="anthropic:claude-sonnet-4-6",
                verdict="suggest",
                confidence=0.7,
                reasoning="Could add a test",
            ),
            ProposalReview(
                model_id="anthropic:claude-haiku-4-5@20251001",
                verdict="approve",
                confidence=0.85,
                reasoning="Matches the request",
            ),
        ],
        consensus_verdict="approve",
        consensus_confidence=0.82,
        agreement_score=2 / 3,
        judge_reasoning="Two approves, one suggest",
    )
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="add x",
        status="success",
        started_at=_started_at(),
        verification=verification,
    )

    with db.get_session() as s:
        run = s.get(RunRow, run_id)
        review_rows = s.exec(select(ReviewRow).where(ReviewRow.run_id == run_id)).all()

    assert run.consensus_verdict == "approve"
    assert run.consensus_confidence == 0.82
    assert abs(run.agreement_score - 2 / 3) < 1e-9
    assert len(review_rows) == 3
    assert sorted(r.model_id for r in review_rows) == sorted(
        v.model_id for v in verification.reviews
    )


# ---------------------------------------------------------------------------
# Apply result fields
# ---------------------------------------------------------------------------
def test_save_run_records_apply_result(tmp_db):
    apply_result = ApplyResult(
        branch_name="agent/foo-20260519-120000",
        applied_commit="abc1234deadbeef",
        test_result=ExecutionResult(
            success=True,
            stdout="3 passed",
            stderr="",
            exit_code=0,
            runtime_ms=42,
            timed_out=False,
            error_category="none",
        ),
        rolled_back=False,
        rollback_reason="",
    )
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="x",
        status="success",
        started_at=_started_at(),
        apply_result=apply_result,
    )
    with db.get_session() as s:
        run = s.get(RunRow, run_id)
    assert run.branch_name == "agent/foo-20260519-120000"
    assert run.applied_commit == "abc1234deadbeef"
    assert run.test_passed is True


def test_save_run_records_rollback(tmp_db):
    apply_result = ApplyResult(
        branch_name="agent/doomed-20260519-120000",
        applied_commit=None,
        test_result=ExecutionResult(
            success=False,
            stdout="",
            stderr="AssertionError",
            exit_code=1,
            runtime_ms=10,
            timed_out=False,
            error_category="assertion",
        ),
        rolled_back=True,
        rollback_reason="tests failed",
    )
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="x",
        status="rolled_back",
        started_at=_started_at(),
        apply_result=apply_result,
    )
    with db.get_session() as s:
        run = s.get(RunRow, run_id)
    assert run.applied_commit is None
    assert run.branch_name == "agent/doomed-20260519-120000"
    assert run.test_passed is False
    assert run.status == "rolled_back"


# ---------------------------------------------------------------------------
# Intent fields denormalised
# ---------------------------------------------------------------------------
def test_save_run_records_intent(tmp_db):
    intent = Intent(
        kind="implement",
        canonical_request="Add a --version flag.",
        rationale="User wants version info.",
    )
    run_id = persist.save_run(
        repo_path=Path("/tmp/r"),
        kind="implement",
        request="add version flag",
        status="success",
        started_at=_started_at(),
        intent=intent,
    )
    with db.get_session() as s:
        run = s.get(RunRow, run_id)
    assert run.intent_kind == "implement"
    assert "version flag" in run.intent_canonical
