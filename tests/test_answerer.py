"""Hermetic test for the Answerer agent."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.answerer import answer_question, answerer_agent
from src.schemas import Catalog, CatalogFile, Intent, LocatedFiles

pytestmark = pytest.mark.asyncio


async def test_answerer_passes_prior_turns_into_prompt():
    """When prior_turns is supplied, the prompt must include the previous
    Q/A so the model can answer the follow-up coherently."""
    intent = Intent(
        kind="question",
        canonical_request="Where exactly is RLIMIT_AS configured?",
        rationale="Follow-up after initial overview.",
    )
    catalog = Catalog(
        repo_path=Path("/tmp/example"),
        git_commit="abcd1234",
        files=[
            CatalogFile(
                path="src/sandbox.py", purpose="sandbox", public_symbols=[],
                content_hash="h1",
            )
        ],
    )
    located = LocatedFiles(paths=["src/sandbox.py"], reasoning="sandbox file")
    prior = [
        ("How does the sandbox enforce memory?", "Via setrlimit() in the preamble."),
    ]

    captured_prompts: list[str] = []

    class _CapturingTestModel(TestModel):
        async def request(self, messages, *args, **kwargs):  # type: ignore[override]
            # Capture the user message text from the request before responding.
            for m in messages:
                for part in getattr(m, "parts", []):
                    content = getattr(part, "content", None)
                    if isinstance(content, str):
                        captured_prompts.append(content)
            return await super().request(messages, *args, **kwargs)

    fake = {"body": "RLIMIT_AS is set at src/sandbox.py:43.", "cited_files": ["src/sandbox.py"]}
    with answerer_agent.override(
        model=_CapturingTestModel(custom_output_args=fake)
    ):
        answer = await answer_question(
            intent, catalog, located,
            {"src/sandbox.py": "import resource\n"},
            prior_turns=prior,
        )

    assert "RLIMIT_AS" in answer.body
    # The prompt must have carried the previous turn so the model has context.
    full = "\n".join(captured_prompts)
    assert "Previous conversation" in full
    assert "How does the sandbox enforce memory?" in full
    assert "Via setrlimit() in the preamble." in full
    assert "follow-up" in full.lower()


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
