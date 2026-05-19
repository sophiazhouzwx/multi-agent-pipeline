"""Round-trip checks for the v2 repo-aware schemas."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas import (
    Catalog,
    CatalogFile,
    CatalogSymbol,
    ChangePlan,
    ChangeProposal,
    FileEdit,
    GateDecision,
    Intent,
    Repo,
    RepoRun,
    Request,
)


def _repo() -> Repo:
    return Repo(path=Path("/tmp/example"), git_commit="abcd123", branch="main")


def _intent() -> Intent:
    return Intent(
        kind="question",
        canonical_request="Where does the parser tokenize input?",
        rationale="User asked about parser internals",
    )


def test_request_roundtrip():
    req = Request(repo=_repo(), user_message="find the tokenizer", kind="question")
    assert Request.model_validate_json(req.model_dump_json()) == req


def test_catalog_roundtrip():
    cat = Catalog(
        repo_path=Path("/tmp/example"),
        git_commit="abcd123",
        files=[
            CatalogFile(
                path="src/lexer.py",
                purpose="tokenises source",
                public_symbols=[
                    CatalogSymbol(name="tokenize", signature="(src: str) -> list[Token]"),
                ],
                content_hash="aaaa",
            ),
        ],
    )
    assert Catalog.model_validate_json(cat.model_dump_json()) == cat


def test_change_proposal_roundtrip():
    plan = ChangePlan(
        summary="add a --json flag",
        affected_files=["src/cli.py"],
        steps=["import json", "wire option", "format output"],
    )
    edit = FileEdit(
        path="src/cli.py",
        new_content="# new content\n",
        rationale="adds --json flag",
    )
    prop = ChangeProposal(plan=plan, edits=[edit])
    assert ChangeProposal.model_validate_json(prop.model_dump_json()) == prop


def test_gate_decision_action_constrained():
    with pytest.raises(ValidationError):
        GateDecision(gate="intent", action="maybe")  # type: ignore[arg-type]


def test_gate_decision_with_edit():
    g = GateDecision(gate="plan", action="edit", edited_payload="new plan text")
    assert g.action == "edit"
    assert g.edited_payload == "new plan text"


def test_repo_run_minimum_fields():
    req = Request(repo=_repo(), user_message="find the tokenizer", kind="question")
    run = RepoRun(request=req, intent=_intent())
    assert run.plan is None
    assert run.gates == []
    assert run.total_cost_usd == 0.0
    # Round-trip survives.
    assert RepoRun.model_validate_json(run.model_dump_json()) == run
