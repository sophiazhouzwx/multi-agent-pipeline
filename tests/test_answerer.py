"""Hermetic test for the Answerer agent."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.answerer import answer_question, answerer_agent
from src.schemas import Catalog, CatalogFile, Intent, LocatedFiles

pytestmark = pytest.mark.asyncio


async def test_answerer_returns_typed_answer():
    intent = Intent(
        kind="question",
        canonical_request="Where does the sandbox set its memory limit?",
        rationale="User asking about a specific implementation detail.",
    )
    catalog = Catalog(
        repo_path=Path("/tmp/example"),
        git_commit="abcd1234",
        files=[
            CatalogFile(
                path="src/sandbox.py",
                purpose="sandboxed execution with resource limits",
                public_symbols=[],
                content_hash="h1",
            )
        ],
    )
    located = LocatedFiles(
        paths=["src/sandbox.py"],
        reasoning="The sandbox module owns rlimits.",
    )
    fake_output = {
        "body": "Memory limit is set via RLIMIT_AS in `src/sandbox.py:42`.",
        "cited_files": ["src/sandbox.py"],
    }
    with answerer_agent.override(model=TestModel(custom_output_args=fake_output)):
        answer = await answer_question(
            intent, catalog, located, {"src/sandbox.py": "import resource\n# ...\n"}
        )
    assert "RLIMIT_AS" in answer.body
    assert answer.cited_files == ["src/sandbox.py"]
