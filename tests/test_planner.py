"""Hermetic test for the Planner agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.planner import plan_change, planner_agent
from src.schemas import Intent, LocatedFiles

pytestmark = pytest.mark.asyncio


async def test_planner_returns_typed_change_plan():
    intent = Intent(
        kind="implement",
        canonical_request="Add a --json flag to the ask command that prints the answer as JSON.",
        rationale="User wants machine-readable output.",
    )
    located = LocatedFiles(
        paths=["src/cli.py"],
        reasoning="The CLI defines the ask command.",
    )
    file_contents = {"src/cli.py": "# pretend cli.py contents\n"}

    fake_output = {
        "summary": "Add a --json flag to the ask command that emits the Answer as JSON.",
        "affected_files": ["src/cli.py"],
        "steps": [
            "Add a json_output: bool = typer.Option(False, '--json') parameter to ask().",
            "When True, after Stage 4 print answer.model_dump_json(indent=2) instead of the rich Panel.",
        ],
    }
    with planner_agent.override(model=TestModel(custom_output_args=fake_output)):
        plan = await plan_change(intent, located, file_contents)

    assert plan.summary.startswith("Add a --json flag")
    assert plan.affected_files == ["src/cli.py"]
    assert len(plan.steps) == 2
    assert "json_output" in plan.steps[0]


async def test_planner_can_signal_impossible_request():
    """If the model can't make sense of the request, summary explains it and
    affected_files/steps stay empty."""
    intent = Intent(
        kind="implement",
        canonical_request="Make the code faster by 1000x.",
        rationale="Vague performance request.",
    )
    located = LocatedFiles(paths=["src/cli.py"], reasoning="Picked CLI.")
    file_contents = {"src/cli.py": "x = 1\n"}

    fake_output = {
        "summary": "Request is too vague to plan a concrete change.",
        "affected_files": [],
        "steps": [],
    }
    with planner_agent.override(model=TestModel(custom_output_args=fake_output)):
        plan = await plan_change(intent, located, file_contents)

    assert plan.affected_files == []
    assert plan.steps == []
    assert "vague" in plan.summary.lower()
