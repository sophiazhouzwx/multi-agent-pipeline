"""Hermetic tests for the HITL gate prompt.

Uses the gate's ``ask_fn`` / ``edit_fn`` injection points so no real terminal
input is needed.
"""

from __future__ import annotations

from rich.console import Console

from src.hitl.gate import show_and_confirm


def _make_console() -> Console:
    # Quiet console so test output stays clean.
    return Console(record=True, force_terminal=False)


def test_gate_confirm():
    decision = show_and_confirm(
        "intent",
        "previous agent output",
        console=_make_console(),
        ask_fn=lambda q, c, d: "c",
        edit_fn=lambda: "",
    )
    assert decision.gate == "intent"
    assert decision.action == "confirm"
    assert decision.edited_payload is None


def test_gate_abort():
    decision = show_and_confirm(
        "plan",
        "the plan goes here",
        console=_make_console(),
        ask_fn=lambda q, c, d: "a",
    )
    assert decision.action == "abort"


def test_gate_edit_returns_payload():
    decision = show_and_confirm(
        "apply",
        "files to write",
        console=_make_console(),
        ask_fn=lambda q, c, d: "e",
        edit_fn=lambda: "  add input validation too  ",
    )
    assert decision.action == "edit"
    assert decision.edited_payload == "add input validation too"


def test_gate_empty_edit_reprompts_then_confirms():
    """Empty edits don't crash — the loop reprompts until a real choice."""
    answers = iter(["e", "c"])
    edits = iter([""])

    decision = show_and_confirm(
        "intent",
        "payload",
        console=_make_console(),
        ask_fn=lambda q, c, d: next(answers),
        edit_fn=lambda: next(edits),
    )
    assert decision.action == "confirm"


def test_gate_unrecognised_choice_reprompts():
    answers = iter(["x", "a"])
    decision = show_and_confirm(
        "intent",
        "payload",
        console=_make_console(),
        ask_fn=lambda q, c, d: next(answers),
    )
    assert decision.action == "abort"
