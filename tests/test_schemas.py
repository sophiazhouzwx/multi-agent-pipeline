"""Round-trip serialisation + validation checks for inter-agent schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import (
    CodeSolution,
    Evaluation,
    ExecutionResult,
    PipelineRun,
    Task,
    TaskComplexity,
    TokenUsage,
    VerificationPanel,
    VerificationVote,
)


def _solution() -> CodeSolution:
    return CodeSolution(
        code="def f(x):\n    return x + 1\n",
        entry_point="f",
        explanation="adds one",
    )


def _evaluation(passes: bool = True) -> Evaluation:
    return Evaluation(
        correctness=9,
        efficiency=8,
        safety=10,
        overall=9 if passes else 4,
        critique="LGTM" if passes else "wrong answer",
        passes_threshold=passes,
    )


def _execution() -> ExecutionResult:
    return ExecutionResult(
        success=True,
        stdout="",
        stderr="",
        exit_code=0,
        runtime_ms=12,
        timed_out=False,
        error_category="none",
    )


def test_task_roundtrip():
    t = Task(task_id="t1", prompt="add one", test_code="assert f(1) == 2", difficulty="easy")
    assert Task.model_validate_json(t.model_dump_json()) == t


def test_evaluation_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Evaluation(
            correctness=11,
            efficiency=5,
            safety=5,
            overall=5,
            critique="",
            passes_threshold=False,
        )


def test_verification_panel_roundtrip():
    vote = VerificationVote(
        model_id="anthropic:claude-haiku-4-5",
        answer=_solution(),
        confidence=0.8,
        reasoning="matches spec",
    )
    panel = VerificationPanel(votes=[vote], consensus=_solution(), agreement_score=1.0)
    assert VerificationPanel.model_validate_json(panel.model_dump_json()) == panel


def test_task_complexity_tier_constrained():
    with pytest.raises(ValidationError):
        TaskComplexity(tier="trivial", reasoning="")  # type: ignore[arg-type]


def test_pipeline_run_full_roundtrip():
    run = PipelineRun(
        task_id="t1",
        final_solution=_solution(),
        iterations=2,
        final_evaluation=_evaluation(),
        final_execution=_execution(),
        verification=None,
        total_cost_usd=0.0123,
        total_latency_ms=4567,
        per_model_tokens={
            "anthropic:claude-opus-4-6": TokenUsage(
                input_tokens=120, output_tokens=80, cached_tokens=10
            ),
        },
    )
    assert PipelineRun.model_validate_json(run.model_dump_json()) == run


def test_confidence_range():
    with pytest.raises(ValidationError):
        VerificationVote(
            model_id="m",
            answer=_solution(),
            confidence=1.5,
            reasoning="",
        )
