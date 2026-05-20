"""Persist a finished run to the SQLite store.

Called once per CLI invocation (from the ``finally`` block in the
orchestrator) so EVERY run is recorded — success, abort, error, rollback.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.schemas import (
    ApplyResult,
    GateDecision,
    Intent,
    PanelVerdict,
)
from src.storage.db import get_session
from src.storage.models import GateRow, ReviewRow, RunRow


def save_run(
    *,
    repo_path: Path,
    kind: str,
    request: str,
    status: str,
    started_at: datetime,
    ended_at: datetime | None = None,
    intent: Intent | None = None,
    verification: PanelVerdict | None = None,
    apply_result: ApplyResult | None = None,
    gates: list[GateDecision] | None = None,
) -> int:
    """Persist a finished run + its child rows. Returns the new run id."""
    if ended_at is None:
        ended_at = datetime.now(timezone.utc)
    runtime_ms = int((ended_at - started_at).total_seconds() * 1000)

    run = RunRow(
        repo_path=str(repo_path),
        kind=kind,
        request=request,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        total_runtime_ms=runtime_ms,
        intent_kind=intent.kind if intent else None,
        intent_canonical=intent.canonical_request if intent else None,
        consensus_verdict=verification.consensus_verdict if verification else None,
        consensus_confidence=verification.consensus_confidence if verification else None,
        agreement_score=verification.agreement_score if verification else None,
        applied_commit=apply_result.applied_commit if apply_result else None,
        branch_name=apply_result.branch_name if apply_result else None,
        test_passed=(
            apply_result.test_result.success
            if apply_result and apply_result.test_result
            else None
        ),
    )

    with get_session() as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
        assert run_id is not None

        if gates:
            for i, g in enumerate(gates, 1):
                session.add(
                    GateRow(
                        run_id=run_id,
                        ordinal=i,
                        gate=g.gate,
                        action=g.action,
                        edited_payload=g.edited_payload,
                    )
                )

        if verification:
            for r in verification.reviews:
                session.add(
                    ReviewRow(
                        run_id=run_id,
                        model_id=r.model_id,
                        verdict=r.verdict,
                        confidence=r.confidence,
                        reasoning=r.reasoning,
                    )
                )

        session.commit()

    return run_id
