"""Hermetic tests for the complexity router + tier-aware generator dispatch."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from src.agents.complexity_router import (
    classify_complexity,
    complexity_router_agent,
)
from src.agents.generator import _GENERATOR_AGENTS, generate_changes
from src.config import ROUTER_TIER_TO_MODEL
from src.schemas import ChangePlan, Intent

pytestmark = pytest.mark.asyncio


async def test_complexity_router_returns_typed_tier():
    fake = {"tier": "easy", "reasoning": "single-file flag rename"}
    with complexity_router_agent.override(model=TestModel(custom_output_args=fake)):
        complexity = await classify_complexity(
            Intent(
                kind="implement",
                canonical_request="rename --foo to --bar",
                rationale="cosmetic CLI cleanup",
            )
        )
    assert complexity.tier == "easy"
    assert "single-file" in complexity.reasoning


async def test_generator_uses_tier_specific_agent():
    """Passing model_id=<tier model> should route the call to that tier's
    cached agent, not the default one."""
    haiku_model = ROUTER_TIER_TO_MODEL["easy"]
    haiku_agent = _GENERATOR_AGENTS[haiku_model]

    fake_haiku = [
        {"path": "f.py", "new_content": "# from haiku\n", "rationale": "haiku-tier edit"},
    ]
    fake_default = [
        {"path": "f.py", "new_content": "# from default\n", "rationale": "default-tier edit"},
    ]
    plan = ChangePlan(summary="x", affected_files=["f.py"], steps=["s"])
    intent = Intent(kind="implement", canonical_request="x", rationale="y")

    with haiku_agent.override(model=TestModel(custom_output_args=fake_haiku)):
        # Override the default too so we can prove it WASN'T called.
        from src.agents.generator import generator_agent

        with generator_agent.override(model=TestModel(custom_output_args=fake_default)):
            proposal = await generate_changes(
                intent, plan, {"f.py": "# old\n"}, model_id=haiku_model
            )

    assert "haiku" in proposal.edits[0].new_content


async def test_generator_falls_back_to_default_on_unknown_model():
    """If the caller passes a model_id we don't have a cached agent for,
    the call uses the default agent (back-compat)."""
    from src.agents.generator import generator_agent

    fake = [
        {"path": "f.py", "new_content": "# from default\n", "rationale": "default"},
    ]
    plan = ChangePlan(summary="x", affected_files=["f.py"], steps=["s"])
    intent = Intent(kind="implement", canonical_request="x", rationale="y")

    with generator_agent.override(model=TestModel(custom_output_args=fake)):
        proposal = await generate_changes(
            intent, plan, {"f.py": "# old\n"}, model_id="anthropic:nonexistent-model"
        )

    assert "default" in proposal.edits[0].new_content
