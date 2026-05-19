"""Human-in-the-loop confirmation gate.

Renders an agent's output to the terminal and asks the user one of:
- (c)onfirm   — proceed with the payload as-is
- (e)dit      — supply a correction/instruction; the next agent will get
                the edit appended to its input prompt
- (a)bort     — stop the pipeline now

Returns a typed ``GateDecision`` that the orchestrator persists in the
RepoRun's gate transcript.

The gate is the ONLY interactive component of the pipeline — every agent
call is non-interactive. Tests substitute the input function via the
``ask_fn`` parameter to keep them hermetic.
"""

from __future__ import annotations

import os
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.schemas import GateDecision, GateName


AUTO_CONFIRM_ENV = "GATE_AUTO_CONFIRM"


GATE_TITLES: dict[GateName, str] = {
    "intent": "Intent — confirm what the agent thinks you're asking",
    "plan": "Plan — confirm the change plan before code is generated",
    "apply": "Apply — confirm files will be written and tested",
}


AskFn = Callable[[str, list[str], str], str]
EditFn = Callable[[], str]


def _default_ask(question: str, choices: list[str], default: str) -> str:
    return Prompt.ask(question, choices=choices, default=default)


def _default_edit() -> str:
    return Prompt.ask("Your correction or extra instruction")


def show_and_confirm(
    gate: GateName,
    payload_display: str,
    *,
    console: Console | None = None,
    ask_fn: AskFn = _default_ask,
    edit_fn: EditFn = _default_edit,
) -> GateDecision:
    """Display ``payload_display`` and prompt the user for c/e/a.

    Returns the typed ``GateDecision``. For ``action == "edit"`` the
    ``edited_payload`` field carries the user's correction text — the
    orchestrator decides how to merge that into the next agent's prompt.
    """
    cons = console or Console()
    cons.print(
        Panel(
            payload_display,
            title=f"[bold cyan]GATE: {GATE_TITLES.get(gate, gate)}[/bold cyan]",
            border_style="cyan",
        )
    )

    # Non-interactive escape hatch for CI / scripted runs / tests.
    if os.environ.get(AUTO_CONFIRM_ENV) == "1":
        cons.print("[dim](auto-confirmed via GATE_AUTO_CONFIRM=1)[/dim]")
        return GateDecision(gate=gate, action="confirm")

    while True:
        choice = ask_fn("[c]onfirm / [e]dit / [a]bort", ["c", "e", "a"], "c").strip().lower()
        if choice == "c":
            return GateDecision(gate=gate, action="confirm")
        if choice == "a":
            return GateDecision(gate=gate, action="abort")
        if choice == "e":
            edit = edit_fn().strip()
            if not edit:
                cons.print("[yellow]Empty correction — choose again.[/yellow]")
                continue
            return GateDecision(gate=gate, action="edit", edited_payload=edit)
        cons.print(f"[yellow]Unrecognised choice {choice!r} — try c, e, or a.[/yellow]")
