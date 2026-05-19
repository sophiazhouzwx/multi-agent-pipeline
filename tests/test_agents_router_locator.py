"""Hermetic tests for the Intent Router and Locator agents.

Uses PydanticAI's TestModel to stub the LLM call. No live API.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.locator import locate, locator_agent
from src.agents.router import classify_intent, router_agent
from src.schemas import Catalog, CatalogFile, Intent

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Intent Router
# ---------------------------------------------------------------------------
async def test_router_returns_typed_intent():
    fake_intent = {
        "kind": "question",
        "canonical_request": "Where does the sandbox enforce its memory limit?",
        "rationale": "User is asking about a location in the codebase.",
    }
    with router_agent.override(model=TestModel(custom_output_args=fake_intent)):
        intent = await classify_intent("where's the mem limit set?")
    assert intent.kind == "question"
    assert "memory" in intent.canonical_request.lower()
    assert intent.rationale


async def test_router_implement_kind():
    fake_intent = {
        "kind": "implement",
        "canonical_request": "Add a --json flag to the parse command that emits JSON.",
        "rationale": "User wants a new CLI flag.",
    }
    with router_agent.override(model=TestModel(custom_output_args=fake_intent)):
        intent = await classify_intent("can you add a json flag to parse?")
    assert intent.kind == "implement"


# ---------------------------------------------------------------------------
# Locator
# ---------------------------------------------------------------------------
def _make_catalog() -> Catalog:
    return Catalog(
        repo_path=Path("/tmp/example"),
        git_commit="abcd1234",
        files=[
            CatalogFile(
                path="src/execution/sandbox.py",
                purpose="sandboxed Python and pytest execution with rlimits",
                public_symbols=[],
                content_hash="h1",
            ),
            CatalogFile(
                path="src/cli.py",
                purpose="typer CLI entrypoint",
                public_symbols=[],
                content_hash="h2",
            ),
            CatalogFile(
                path="src/catalog/indexer.py",
                purpose="walks the repo and writes AGENT_CATALOG.md",
                public_symbols=[],
                content_hash="h3",
            ),
        ],
    )


async def test_locator_returns_paths_from_catalog():
    intent = Intent(
        kind="question",
        canonical_request="Where does the sandbox set memory limits?",
        rationale="Asking about sandbox internals.",
    )
    fake_output = {
        "paths": ["src/execution/sandbox.py"],
        "reasoning": "The sandbox module enforces resource limits.",
    }
    with locator_agent.override(model=TestModel(custom_output_args=fake_output)):
        located = await locate(_make_catalog(), intent)
    assert located.paths == ["src/execution/sandbox.py"]
    assert "limits" in located.reasoning


async def test_locator_filters_hallucinated_paths():
    """If the model returns a path that isn't in the catalog, it must be dropped."""
    intent = Intent(
        kind="question",
        canonical_request="Where is X?",
        rationale="...",
    )
    fake_output = {
        "paths": ["src/execution/sandbox.py", "src/does_not_exist.py", "src/cli.py"],
        "reasoning": "Picked these.",
    }
    with locator_agent.override(model=TestModel(custom_output_args=fake_output)):
        located = await locate(_make_catalog(), intent)
    assert located.paths == ["src/execution/sandbox.py", "src/cli.py"]
    assert "src/does_not_exist.py" not in located.paths
