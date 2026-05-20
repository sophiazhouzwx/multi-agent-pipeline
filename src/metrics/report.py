"""Aggregate metrics over ``runs.db``.

Pure-Python over SQLModel; no LLM calls. Each top-level function returns a
typed dict so the CLI can render multiple tables from a single DB read.

Cost tracking (token usage * per-model prices) is a planned follow-up.
Today the report focuses on the structural metrics that don't need
per-call usage capture.
"""

from __future__ import annotations

from typing import Iterable

from sqlmodel import Session, select

from src.storage.db import get_session
from src.storage.models import GateRow, ReviewRow, RunRow


def _percentile(values: list[int], p: float) -> int:
    """Compute the p-th percentile (0-1) of ``values``. Empty -> 0."""
    if not values:
        return 0
    s = sorted(values)
    idx = min(int(p * len(s)), len(s) - 1)
    return s[idx]


def total_runs(session: Session) -> int:
    return len(session.exec(select(RunRow)).all())


def runs_by_kind_status(session: Session) -> dict[tuple[str, str], int]:
    """Counts keyed by (kind, status) — e.g. ('implement', 'success') -> 7."""
    rows = session.exec(select(RunRow.kind, RunRow.status)).all()
    out: dict[tuple[str, str], int] = {}
    for kind, status in rows:
        out[(kind, status)] = out.get((kind, status), 0) + 1
    return out


def latency_stats(session: Session, status_filter: str | None = "success") -> dict[str, int]:
    """Latency percentiles in ms, optionally filtered by status."""
    stmt = select(RunRow.total_runtime_ms)
    if status_filter:
        stmt = stmt.where(RunRow.status == status_filter)
    values = list(session.exec(stmt))
    return {
        "count": len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
    }


def gate_action_counts(session: Session) -> dict[tuple[str, str], int]:
    """Counts keyed by (gate, action). e.g. ('intent', 'confirm') -> 11."""
    rows = session.exec(select(GateRow.gate, GateRow.action)).all()
    out: dict[tuple[str, str], int] = {}
    for gate, action in rows:
        out[(gate, action)] = out.get((gate, action), 0) + 1
    return out


def reviewer_verdict_counts(session: Session) -> dict[tuple[str, str], int]:
    """Counts keyed by (model_id, verdict)."""
    rows = session.exec(select(ReviewRow.model_id, ReviewRow.verdict)).all()
    out: dict[tuple[str, str], int] = {}
    for model_id, verdict in rows:
        out[(model_id, verdict)] = out.get((model_id, verdict), 0) + 1
    return out


def panel_agreement_stats(session: Session) -> dict[str, float]:
    """Mean agreement_score across all runs that completed verification."""
    scores = list(
        session.exec(
            select(RunRow.agreement_score).where(RunRow.agreement_score.is_not(None))
        )
    )
    if not scores:
        return {"mean": 0.0, "n": 0}
    return {"mean": sum(scores) / len(scores), "n": float(len(scores))}


def apply_outcome_stats(session: Session) -> dict[str, int]:
    """Apply attempts: total, applied, rolled_back, with pass rate as percent."""
    all_implement = list(
        session.exec(
            select(RunRow.status, RunRow.applied_commit, RunRow.test_passed).where(
                RunRow.kind == "implement"
            )
        )
    )
    attempted = sum(
        1 for status, commit, _ in all_implement if commit is not None or status == "rolled_back"
    )
    applied = sum(1 for _, commit, passed in all_implement if commit is not None and passed)
    rolled_back = sum(1 for status, _, _ in all_implement if status == "rolled_back")
    pct = int(round(100 * applied / attempted)) if attempted else 0
    return {
        "attempted": attempted,
        "applied": applied,
        "rolled_back": rolled_back,
        "pass_rate_pct": pct,
    }


def compute_report() -> dict[str, object]:
    """One DB read; returns every metric in a single dict for the CLI."""
    with get_session() as session:
        return {
            "total_runs": total_runs(session),
            "by_kind_status": runs_by_kind_status(session),
            "latency": latency_stats(session),
            "gate_actions": gate_action_counts(session),
            "reviewer_verdicts": reviewer_verdict_counts(session),
            "panel_agreement": panel_agreement_stats(session),
            "apply_outcomes": apply_outcome_stats(session),
        }


def _short(model_id: str) -> str:
    """Strip the provider prefix for display."""
    return model_id.split(":", 1)[-1]


def known_kinds(by_kind_status: Iterable[tuple[str, str]]) -> list[str]:
    """Return the distinct request kinds present in the data."""
    return sorted({k for k, _ in by_kind_status})


def known_statuses(by_kind_status: Iterable[tuple[str, str]]) -> list[str]:
    """Return the distinct statuses present in the data."""
    return sorted({s for _, s in by_kind_status})
