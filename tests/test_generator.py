"""Hermetic test for the Generator agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.generator import generate_changes, generator_agent
from src.schemas import ChangePlan, Intent

pytestmark = pytest.mark.asyncio


def _plan() -> ChangePlan:
    return ChangePlan(
        summary="Add a --json flag to ask.",
        affected_files=["src/cli.py"],
        steps=[
            "Add `json_output: bool = typer.Option(False, '--json')` to ask().",
            "When True, print answer.model_dump_json() instead of the rich Panel.",
        ],
    )


def _intent() -> Intent:
    return Intent(
        kind="implement",
        canonical_request="Add a --json flag to the ask command that emits the Answer as JSON.",
        rationale="User wants machine-readable output.",
    )


async def test_generator_returns_typed_proposal():
    fake_edits = [
        {
            "path": "src/cli.py",
            "new_content": "# updated cli.py with --json flag\n",
            "rationale": "Wired the new flag into the ask command.",
        }
    ]
    with generator_agent.override(model=TestModel(custom_output_args=fake_edits)):
        proposal = await generate_changes(
            _intent(), _plan(), {"src/cli.py": "# original cli.py\n"}
        )

    assert proposal.plan == _plan()  # plan echoed verbatim
    assert len(proposal.edits) == 1
    assert proposal.edits[0].path == "src/cli.py"
    assert "--json flag" in proposal.edits[0].new_content
    assert "ask command" in proposal.edits[0].rationale


async def test_generator_filters_out_of_plan_edits():
    """Edits for paths not in plan.affected_files must be dropped."""
    fake_edits = [
        {"path": "src/cli.py", "new_content": "# good\n", "rationale": "in plan"},
        {"path": "src/secret.py", "new_content": "# rogue\n", "rationale": "out of plan"},
        {"path": "src/other.py", "new_content": "# rogue2\n", "rationale": "out of plan"},
    ]
    with generator_agent.override(model=TestModel(custom_output_args=fake_edits)):
        proposal = await generate_changes(
            _intent(), _plan(), {"src/cli.py": "# original\n"}
        )

    paths = [e.path for e in proposal.edits]
    assert paths == ["src/cli.py"]


async def test_generator_handles_new_file_paths():
    """A path in the plan that's NOT in file_contents is a new file the
    generator should still emit content for."""
    plan = ChangePlan(
        summary="Add a new helper module.",
        affected_files=["src/cli.py", "src/helpers.py"],
        steps=["Create src/helpers.py", "Import the helper in src/cli.py"],
    )
    fake_edits = [
        {
            "path": "src/cli.py",
            "new_content": "from src.helpers import h\n",
            "rationale": "Wired the new helper.",
        },
        {
            "path": "src/helpers.py",
            "new_content": "def h() -> int:\n    return 1\n",
            "rationale": "Created the new helper module.",
        },
    ]
    with generator_agent.override(model=TestModel(custom_output_args=fake_edits)):
        # Only src/cli.py exists; src/helpers.py is new.
        proposal = await generate_changes(
            _intent(), plan, {"src/cli.py": "x = 1\n"}
        )

    paths = sorted(e.path for e in proposal.edits)
    assert paths == ["src/cli.py", "src/helpers.py"]
    helpers_edit = next(e for e in proposal.edits if e.path == "src/helpers.py")
    assert "def h" in helpers_edit.new_content
