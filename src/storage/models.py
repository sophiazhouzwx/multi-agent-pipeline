"""SQLModel tables for the storage layer.

Three tables, all in the single ``runs.db`` at the project root:

- ``runs``      — one row per pipeline invocation (ask or implement)
- ``gates``     — child rows: every HITL gate decision in a run
- ``reviews``   — child rows: every verifier panel review in a run

Top-level run fields are indexed for efficient ``report`` queries (Step 13);
freeform fields (reasoning, request text) are stored as TEXT and aren't
indexed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunRow(SQLModel, table=True):
    """One row per CLI invocation (ask or implement)."""

    __tablename__ = "runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_path: str = Field(index=True)
    kind: str = Field(index=True)  # 'ask' | 'implement'
    request: str
    status: str = Field(index=True)
    # status values:
    #   'success'           — completed all stages successfully
    #   'rolled_back'       — apply failed tests; branch destroyed
    #   'rejected'          — verifier panel consensus was 'reject'
    #   'aborted_intent'    — user aborted at Gate #1
    #   'aborted_plan'      — user aborted at Gate #2
    #   'aborted_apply'     — user aborted at Gate #3
    #   'errored'           — exception thrown before completion

    started_at: datetime = Field(default_factory=_now)
    ended_at: Optional[datetime] = None
    total_runtime_ms: int = 0

    # Denormalised top-level fields for fast metrics queries.
    intent_kind: Optional[str] = Field(default=None, index=True)
    intent_canonical: Optional[str] = None
    consensus_verdict: Optional[str] = Field(default=None, index=True)
    consensus_confidence: Optional[float] = None
    agreement_score: Optional[float] = None
    applied_commit: Optional[str] = None
    branch_name: Optional[str] = None
    test_passed: Optional[bool] = None


class GateRow(SQLModel, table=True):
    """One row per HITL gate decision."""

    __tablename__ = "gates"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    ordinal: int  # 1, 2, 3... order within the run
    gate: str = Field(index=True)   # 'intent' | 'plan' | 'apply'
    action: str = Field(index=True)  # 'confirm' | 'edit' | 'abort'
    edited_payload: Optional[str] = None


class ReviewRow(SQLModel, table=True):
    """One row per verifier panel review."""

    __tablename__ = "reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    model_id: str = Field(index=True)
    verdict: str = Field(index=True)
    confidence: float
    reasoning: str
