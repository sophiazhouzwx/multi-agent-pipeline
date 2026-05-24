"""Typer CLI entrypoint for the multi-agent pipeline.

Subcommands (today): ``ask`` — Q&A path against a repo.
Subcommands (planned): ``implement`` (Steps 7-10), ``report`` (Step 13).
"""

from __future__ import annotations

# Load .env BEFORE importing any module that constructs a PydanticAI Agent,
# because Agent(...) reads ANTHROPIC_API_KEY at construction time (i.e. on
# import). Without this, running the CLI from a shell that doesn't have the
# env vars exported errors out before main() ever runs.
from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
import difflib  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import typer  # noqa: E402
from pydantic_ai.exceptions import UnexpectedModelBehavior  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.prompt import Prompt  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402

from src.agents.answerer import answer_question  # noqa: E402
from src.agents.complexity_router import classify_complexity  # noqa: E402
from src.agents.generator import generate_changes  # noqa: E402
from src.agents.locator import locate  # noqa: E402
from src.agents.planner import plan_change  # noqa: E402
from src.agents.router import classify_intent  # noqa: E402
from src.config import ESCALATION_CHAIN, GENERATOR_MODEL, ROUTER_TIER_TO_MODEL  # noqa: E402
from src.apply.applier import apply_changes  # noqa: E402
from src.catalog.indexer import index_repo, index_stats, load_catalog  # noqa: E402
from src.catalog.updater import refresh_catalog_after_apply  # noqa: E402
from src.hitl.gate import AUTO_CONFIRM_ENV, show_and_confirm  # noqa: E402
from src.metrics.report import (  # noqa: E402
    _short as _short_model,
    compute_report,
    known_kinds,
    known_statuses,
)
from src.pipeline.verifier_panel import verify_proposal  # noqa: E402
from src.schemas import (  # noqa: E402
    Answer,
    ApplyResult,
    Catalog,
    ChangePlan,
    ChangeProposal,
    GateDecision,
    Intent,
    PanelVerdict,
)
from src.storage.persist import save_run  # noqa: E402

app = typer.Typer(
    help="Multi-agent repo-aware coding assistant",
    no_args_is_help=True,
)
console = Console()


class _Flag:
    """Tiny container so command-level options can reach the async helpers
    without threading them through every signature."""

    def __init__(self, default: bool = False) -> None:
        self._value = default

    def set(self, v: bool) -> None:
        self._value = v

    def get(self, default: bool = False) -> bool:
        return self._value if self._value is not None else default


_show_edits_flag = _Flag(False)
_skip_verify_flag = _Flag(False)
_no_route_flag = _Flag(False)


_VERDICT_STYLES = {
    "approve": ("green", "✓"),
    "reject": ("red", "✗"),
    "suggest": ("yellow", "?"),
}


@app.callback()
def _root() -> None:
    """Multi-agent repo-aware coding assistant."""
    # Empty callback forces typer to treat this as a multi-command app so
    # `ask` / future `implement` / `report` are real subcommands.


def _format_intent(intent: Intent) -> str:
    return (
        f"[bold]Kind:[/bold] {intent.kind}\n"
        f"[bold]Canonical request:[/bold] {intent.canonical_request}\n"
        f"[bold]Rationale:[/bold] {intent.rationale}"
    )


def _format_unified_diff(path: str, old: str, new: str, is_new: bool) -> str:
    """Render a colorized unified diff for one file edit."""
    diff_lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}" if not is_new else "/dev/null",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    colored: list[str] = []
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            colored.append(f"[bold]{line}[/bold]")
        elif line.startswith("@@"):
            colored.append(f"[cyan]{line}[/cyan]")
        elif line.startswith("+"):
            colored.append(f"[green]{line}[/green]")
        elif line.startswith("-"):
            colored.append(f"[red]{line}[/red]")
        else:
            colored.append(line)
    return "\n".join(colored) if colored else "[dim](no diff — content identical)[/dim]"


def _format_gate3_payload(
    proposal: ChangeProposal, existing_contents: dict[str, str]
) -> str:
    """Build the Gate #3 payload: per-file unified diffs + summary."""
    blocks: list[str] = []
    total_added = total_removed = 0
    for edit in proposal.edits:
        old = existing_contents.get(edit.path, "")
        is_new = edit.path not in existing_contents
        added, removed = _diff_stats(old, edit.new_content)
        total_added += added
        total_removed += removed
        header = (
            f"[bold]{'NEW' if is_new else 'MODIFY'}[/bold] [cyan]{edit.path}[/cyan]  "
            f"[green]+{added}[/green]/[red]-{removed}[/red]  — {edit.rationale}"
        )
        diff = _format_unified_diff(edit.path, old, edit.new_content, is_new)
        blocks.append(f"{header}\n{diff}")
    summary = (
        f"[bold]{len(proposal.edits)} file(s)[/bold], "
        f"[green]+{total_added}[/green] / [red]-{total_removed}[/red] lines.\n"
        "The Applier will: create a new branch [bold]agent/<slug>[/bold], "
        "write these files, commit, and run [bold]pytest[/bold]. "
        "Tests must pass or the branch is rolled back entirely."
    )
    return summary + "\n\n" + "\n\n".join(blocks)


def _diff_stats(old: str, new: str) -> tuple[int, int]:
    """Return (lines_added, lines_removed) between old and new content."""
    matcher = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            removed += i2 - i1
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "insert":
            added += j2 - j1
    return added, removed


def _format_panel_verdict(verdict: PanelVerdict) -> Table:
    color, glyph = _VERDICT_STYLES.get(verdict.consensus_verdict, ("white", "·"))
    table = Table(
        show_header=True,
        header_style="bold",
        title=(
            f"Verifier panel: [{color}]{glyph} {verdict.consensus_verdict.upper()}[/{color}] "
            f"(confidence {verdict.consensus_confidence:.2f}, "
            f"agreement {verdict.agreement_score:.2f})"
        ),
    )
    table.add_column("model", style="cyan")
    table.add_column("verdict")
    table.add_column("conf", justify="right")
    table.add_column("reasoning")
    for review in verdict.reviews:
        rcolor, rglyph = _VERDICT_STYLES.get(review.verdict, ("white", "·"))
        # Strip the "anthropic:" prefix for compact display.
        short = review.model_id.split(":", 1)[-1]
        table.add_row(
            short,
            f"[{rcolor}]{rglyph} {review.verdict}[/{rcolor}]",
            f"{review.confidence:.2f}",
            review.reasoning[:120] + ("..." if len(review.reasoning) > 120 else ""),
        )
    return table


def _format_proposal_table(
    proposal: ChangeProposal, existing_contents: dict[str, str]
) -> Table:
    table = Table(show_header=True, header_style="bold", title="Proposed edits")
    table.add_column("path", style="cyan")
    table.add_column("status")
    table.add_column("+", justify="right", style="green")
    table.add_column("-", justify="right", style="red")
    table.add_column("rationale")
    for edit in proposal.edits:
        old = existing_contents.get(edit.path, "")
        added, removed = _diff_stats(old, edit.new_content)
        status = "new" if edit.path not in existing_contents else "modify"
        table.add_row(
            edit.path,
            status,
            str(added),
            str(removed),
            edit.rationale[:80] + ("..." if len(edit.rationale) > 80 else ""),
        )
    return table


def _format_plan(plan: ChangePlan) -> str:
    lines = [f"[bold]Summary:[/bold] {plan.summary}", ""]
    if plan.affected_files:
        lines.append("[bold]Affected files:[/bold]")
        for path in plan.affected_files:
            lines.append(f"  - {path}")
        lines.append("")
    else:
        lines.append("[yellow]No affected files (planner returned empty plan).[/yellow]")
        lines.append("")
    if plan.steps:
        lines.append("[bold]Steps:[/bold]")
        for i, step in enumerate(plan.steps, 1):
            lines.append(f"  {i}. {step}")
    return "\n".join(lines)


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _can_prompt_follow_up() -> bool:
    """True iff we're in an interactive TTY and not in auto-confirm mode."""
    if os.environ.get(AUTO_CONFIRM_ENV) == "1":
        return False
    return sys.stdin.isatty()


async def _follow_up_loop(
    repo: Path,
    catalog: Catalog,
    original_intent: Intent,
    first_answer: Answer,
) -> None:
    """After the initial answer, let the user keep asking follow-ups in the
    same conversation. Each turn:
      1. Runs the Intent Router on the raw follow-up text.
      2. If kind='implement', delegates to ``_run_implement_pipeline`` —
         after a successful apply the loop ends (catalog has changed; the
         user can start a fresh `mapipe ask` to continue).
      3. If kind='question', re-locates (in case the topic shifted) and
         passes prior Q/A history to the Answerer for coherence.
    Each turn is persisted as its own RunRow."""
    prior_turns: list[tuple[str, str]] = [
        (original_intent.canonical_request, first_answer.body)
    ]

    while True:
        console.print()
        try:
            follow_up = Prompt.ask(
                "[bold cyan]Follow-up[/bold cyan] — question or change request (empty to finish)",
                default="",
                show_default=False,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Conversation ended (interrupted).[/dim]")
            return

        if not follow_up:
            console.print("[dim]Conversation ended.[/dim]")
            return

        turn_n = len(prior_turns)
        turn_started = datetime.now(timezone.utc)

        # Per-turn intent routing — the heart of unified ask/implement.
        console.rule(f"[bold cyan]Follow-up {turn_n}: Intent[/bold cyan]")
        try:
            turn_intent = await classify_intent(follow_up)
        except UnexpectedModelBehavior as exc:
            console.print(f"[yellow]Intent classifier failed: {exc}[/yellow]")
            continue
        console.print(_format_intent(turn_intent))

        # --- Implement branch: hand off to the full pipeline ---------------
        if turn_intent.kind == "implement":
            console.print(
                "[yellow]Detected an implement request — switching to the "
                "implement pipeline for this turn.[/yellow]"
            )
            exit_code = await _run_implement_pipeline(
                repo, catalog, turn_intent, follow_up, turn_started
            )
            if exit_code == 0:
                console.print(
                    "[dim]Implement complete and applied. Conversation ended — "
                    "the catalog has changed, so start a fresh `mapipe ask` "
                    "to continue.[/dim]"
                )
                return
            console.print(
                "[dim]Implement did not complete — staying in the conversation. "
                "Ask another question or re-request the change.[/dim]"
            )
            continue

        # --- Question branch: existing answer flow -------------------------
        turn_status = "errored"
        gates: list[GateDecision] = []

        try:
            # Re-locate using a combined-context intent so the Locator can
            # pick new files if the topic shifted, or stick with the old set.
            combined = turn_intent.model_copy(
                update={
                    "canonical_request": (
                        f"Previous topic: {original_intent.canonical_request}\n"
                        f"Follow-up question: {follow_up}"
                    )
                }
            )
            console.rule(f"[bold cyan]Follow-up {turn_n}: Locate[/bold cyan]")
            located = await locate(catalog, combined)
            if not located.paths:
                console.print("[yellow]No files matched the follow-up.[/yellow]")
                turn_status = "errored"
                continue
            console.print(f"[bold]Located:[/bold] {', '.join(located.paths)}")
            console.print(f"[dim]Reasoning:[/dim] {located.reasoning}")

            console.rule(f"[bold cyan]Follow-up {turn_n}: Answer[/bold cyan]")
            file_contents = {p: _read_file(repo / p) for p in located.paths}
            try:
                answer = await answer_question(
                    turn_intent, catalog, located, file_contents,
                    prior_turns=prior_turns,
                )
            except UnexpectedModelBehavior as exc:
                console.print(
                    Panel(
                        f"[bold]Model produced an invalid response on this turn.[/bold]\n\n"
                        f"Reason: {exc}\n\n"
                        f"The conversation is still alive — try a shorter / simpler "
                        f"follow-up, or hit Enter to exit. If you're asking for code "
                        f"changes, rephrase as an action ('add X', 'change Y') and "
                        f"the next turn will route to implement automatically.",
                        title="[bold yellow]Follow-up answer failed[/bold yellow]",
                        border_style="yellow",
                    )
                )
                turn_status = "errored"
                continue
            console.print(
                Panel(answer.body, title="[bold green]Answer[/bold green]", border_style="green")
            )
            if answer.cited_files:
                console.print(f"[dim]Cited:[/dim] {', '.join(answer.cited_files)}")

            prior_turns.append((follow_up, answer.body))
            turn_status = "success"
        finally:
            save_run(
                repo_path=repo,
                kind="ask",
                request=follow_up,
                status=turn_status,
                started_at=turn_started,
                intent=turn_intent,
                gates=gates,
            )


async def _ask_async(repo: Path, question: str, rebuild: bool) -> int:
    """Unified per-turn-routed entrypoint.

    Stage 1 (catalog) + Stage 2 (intent + Gate #1) run for every invocation.
    After the gate the router's ``intent.kind`` decides the branch:
      - ``question``: Stages 3-4 (locate + answer), then optional follow-up
        loop. Each follow-up is itself classified and may switch into the
        implement pipeline mid-conversation.
      - ``implement``: hand off to ``_run_implement_pipeline`` (Stages 3-8).
    Only the question branch persists a kind='ask' run row here; the
    implement helper saves its own kind='implement' row.
    """
    repo = repo.resolve()
    started_at = datetime.now(timezone.utc)
    gates: list[GateDecision] = []
    intent: Intent | None = None
    status = "errored"
    delegated_to_implement = False

    try:
        # ---- Stage 1: catalog ---------------------------------------------
        console.rule("[bold cyan]Stage 1: Catalog[/bold cyan]")
        prior = load_catalog(repo)
        try:
            catalog = await index_repo(repo, force_rebuild=rebuild)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            status = "errored"
            return 1

        stats = index_stats(prior, catalog)
        table = Table(show_header=True, header_style="bold")
        table.add_column("total")
        table.add_column("added")
        table.add_column("modified")
        table.add_column("unchanged")
        table.add_row(
            str(stats["total"]),
            str(stats["added"]),
            str(stats["modified"]),
            str(stats["unchanged"]),
        )
        console.print(table)

        # ---- Stage 2: intent + Gate #1 ------------------------------------
        console.rule("[bold cyan]Stage 2: Intent[/bold cyan]")
        intent = await classify_intent(question)
        decision = show_and_confirm("intent", _format_intent(intent))
        gates.append(decision)
        if decision.action == "abort":
            console.print("[red]Aborted at intent gate.[/red]")
            status = "aborted_intent"
            return 2
        if decision.action == "edit":
            revised_message = f"{question}\n\nUser correction: {decision.edited_payload}"
            intent = await classify_intent(revised_message)
            console.print("[green]Re-classified after edit:[/green]")
            console.print(_format_intent(intent))

        # ---- Per-turn routing: hand off to implement pipeline if asked ----
        if intent.kind == "implement":
            console.print(
                "[yellow]Router detected an implement request — switching to "
                "the implement pipeline.[/yellow]"
            )
            delegated_to_implement = True
            return await _run_implement_pipeline(
                repo, catalog, intent, question, started_at, preceding_gates=gates
            )

        # ---- Stage 3: locate ----------------------------------------------
        console.rule("[bold cyan]Stage 3: Locate[/bold cyan]")
        located = await locate(catalog, intent)
        if not located.paths:
            console.print("[yellow]No files matched the request.[/yellow]")
            status = "errored"
            return 3
        console.print(f"[bold]Located:[/bold] {', '.join(located.paths)}")
        console.print(f"[dim]Reasoning:[/dim] {located.reasoning}")

        # ---- Stage 4: answer ----------------------------------------------
        console.rule("[bold cyan]Stage 4: Answer[/bold cyan]")
        file_contents = {p: _read_file(repo / p) for p in located.paths}
        try:
            answer = await answer_question(intent, catalog, located, file_contents)
        except UnexpectedModelBehavior as exc:
            console.print(
                Panel(
                    f"[bold]Model produced an invalid response.[/bold]\n\n"
                    f"Reason: {exc}\n\n"
                    f"Try rephrasing the question. If you want code changes, "
                    f"just say so — `mapipe ask` will auto-route into the "
                    f"implement pipeline.",
                    title="[bold yellow]Answer failed[/bold yellow]",
                    border_style="yellow",
                )
            )
            status = "errored"
            return 4
        console.print(
            Panel(answer.body, title="[bold green]Answer[/bold green]", border_style="green")
        )
        if answer.cited_files:
            console.print(f"[dim]Cited:[/dim] {', '.join(answer.cited_files)}")
        status = "success"

        # ---- Optional: multi-turn follow-up loop --------------------------
        if _can_prompt_follow_up():
            await _follow_up_loop(repo, catalog, intent, answer)

        return 0
    finally:
        # The implement helper saves its own kind='implement' row — don't
        # double-record this turn as kind='ask' when we delegated.
        if not delegated_to_implement:
            save_run(
                repo_path=repo,
                kind="ask",
                request=question,
                status=status,
                started_at=started_at,
                intent=intent,
                gates=gates,
            )


@app.command()
def ask(
    repo: Path = typer.Argument(..., exists=True, file_okay=False, help="Target git repo"),
    question: str = typer.Argument(..., help="A question OR a change request — the router decides per turn"),
    rebuild_index: bool = typer.Option(
        False, "--rebuild-index", help="Discard cached catalog and re-summarize every file."
    ),
    auto_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run)."
    ),
    show_edits: bool = typer.Option(
        False, "--show-edits",
        help="On implement turns: print full proposed file contents (verbose).",
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify",
        help="On implement turns: skip the cross-tier verifier panel (saves 4 LLM calls).",
    ),
    no_route: bool = typer.Option(
        False, "--no-route",
        help="On implement turns: force Opus 4.6 for the generator (skip the complexity router).",
    ),
) -> None:
    """Unified Q&A + implement entrypoint.

    Each turn (the initial input and any follow-up in the multi-turn loop)
    is classified by the Intent Router:

      - 'question' -> Locate + Answer with file citations.
      - 'implement' -> full pipeline (Plan + Gate #2, Generate, Verify,
        Apply + Gate #3 with git branch / tests / commit-or-rollback).

    You can switch from asking to implementing in the same session without
    re-running anything — just describe the change you want. After a
    successful implement the catalog has changed, so the conversation ends
    and you can start a fresh `mapipe ask` to keep going.

    The --show-edits / --no-verify / --no-route flags are no-ops on
    question turns and take effect whenever a turn routes to implement.
    """
    if auto_confirm:
        os.environ[AUTO_CONFIRM_ENV] = "1"
    _show_edits_flag.set(show_edits)
    _skip_verify_flag.set(no_verify)
    _no_route_flag.set(no_route)
    exit_code = asyncio.run(_ask_async(repo, question, rebuild_index))
    raise typer.Exit(exit_code)


async def _run_implement_pipeline(
    repo: Path,
    catalog: Catalog,
    intent: Intent,
    request: str,
    started_at: datetime,
    *,
    preceding_gates: list[GateDecision] | None = None,
) -> int:
    """Stages 3-8 of the implement pipeline (locate -> apply -> catalog refresh).

    Reusable from both ``_ask_async`` (when the per-turn router detects an
    implement intent) and ``_implement_async`` (the deprecated direct
    entrypoint). Saves its own run row with kind='implement'.

    ``preceding_gates`` carries any HITL decisions made before this helper
    was invoked (e.g. Gate #1 in ``_ask_async``) so they appear in the
    persisted run.
    """
    gates: list[GateDecision] = list(preceding_gates) if preceding_gates else []
    verification: PanelVerdict | None = None
    apply_result: ApplyResult | None = None
    status = "errored"

    try:
        # ---- Stage 3: locate ----------------------------------------------
        console.rule("[bold cyan]Stage 3: Locate[/bold cyan]")
        located = await locate(catalog, intent)
        if not located.paths:
            console.print("[yellow]No files matched the request.[/yellow]")
            status = "errored"
            return 3
        console.print(f"[bold]Located:[/bold] {', '.join(located.paths)}")
        console.print(f"[dim]Reasoning:[/dim] {located.reasoning}")

        # ---- Stage 4: plan + Gate #2 --------------------------------------
        console.rule("[bold cyan]Stage 4: Plan[/bold cyan]")
        file_contents = {p: _read_file(repo / p) for p in located.paths}
        plan = await plan_change(intent, located, file_contents)
        decision = show_and_confirm("plan", _format_plan(plan))
        gates.append(decision)
        if decision.action == "abort":
            console.print("[red]Aborted at plan gate.[/red]")
            status = "aborted_plan"
            return 4
        if decision.action == "edit":
            revised_intent = intent.model_copy(
                update={
                    "canonical_request": (
                        f"{intent.canonical_request}\n\n"
                        f"User correction: {decision.edited_payload}"
                    )
                }
            )
            plan = await plan_change(revised_intent, located, file_contents)
            console.print("[green]Re-planned after edit:[/green]")
            console.print(_format_plan(plan))

        # ---- Stage 5a: route (adaptive tier) -----------------------------
        if _no_route_flag.get(False):
            chosen_model = GENERATOR_MODEL
            console.rule(f"[dim]Stage 5a: Route — forced {_short_model(chosen_model)} (--no-route)[/dim]")
        else:
            console.rule("[bold cyan]Stage 5a: Route[/bold cyan]")
            complexity = await classify_complexity(intent)
            chosen_model = ROUTER_TIER_TO_MODEL.get(complexity.tier, GENERATOR_MODEL)
            console.print(
                f"[dim]Complexity:[/dim] [bold]{complexity.tier}[/bold] "
                f"-> [cyan]{_short_model(chosen_model)}[/cyan]\n"
                f"[dim]Reasoning:[/dim] {complexity.reasoning}"
            )

        # ---- Stage 5: generate --------------------------------------------
        console.rule("[bold cyan]Stage 5: Generate[/bold cyan]")
        if not plan.affected_files:
            console.print("[yellow]Plan has no affected files — nothing to generate.[/yellow]")
            status = "errored"
            return 5
        existing_contents: dict[str, str] = {}
        for path in plan.affected_files:
            abs_path = repo / path
            if abs_path.exists():
                existing_contents[path] = _read_file(abs_path)

        # Tier-escalation fallback: if the routed tier emits invalid
        # structured output (Haiku sometimes returns `{}` and exhausts the
        # agent's internal retries, raising UnexpectedModelBehavior), climb
        # ESCALATION_CHAIN until a tier succeeds. Forced-Opus runs
        # (--no-route) just retry once at the top tier.
        try:
            start_idx = ESCALATION_CHAIN.index(chosen_model)
        except ValueError:
            start_idx = len(ESCALATION_CHAIN) - 1
        tier_chain = ESCALATION_CHAIN[start_idx:] or (chosen_model,)

        proposal: ChangeProposal | None = None
        last_error: Exception | None = None
        for attempt_model in tier_chain:
            try:
                proposal = await generate_changes(
                    intent, plan, existing_contents, model_id=attempt_model
                )
                if attempt_model != chosen_model:
                    console.print(
                        f"[yellow]Generator escalated to "
                        f"[cyan]{_short_model(attempt_model)}[/cyan] after "
                        f"lower tier failed.[/yellow]"
                    )
                break
            except UnexpectedModelBehavior as exc:
                last_error = exc
                console.print(
                    f"[yellow]Generator ([cyan]{_short_model(attempt_model)}[/cyan]) "
                    f"produced invalid output: {exc}[/yellow]"
                )

        if proposal is None:
            console.print(
                Panel(
                    f"All generator tiers exhausted ({', '.join(_short_model(m) for m in tier_chain)}).\n\n"
                    f"Last error: {last_error}\n\n"
                    f"Common cause: the plan asks for a binary file "
                    f"(.png/.jpg/.pdf) — the Generator can only emit text. "
                    f"Re-run and at Gate #2 edit the plan to list only the "
                    f"source script that produces the binary.",
                    title="[bold red]Generator failed[/bold red]",
                    border_style="red",
                )
            )
            status = "errored"
            return 5
        if not proposal.edits:
            console.print("[red]Generator produced no edits.[/red]")
            status = "errored"
            return 5

        console.print(_format_proposal_table(proposal, existing_contents))

        if _show_edits_flag.get(False):
            console.rule("[dim]Full edit contents (--show-edits)[/dim]")
            for edit in proposal.edits:
                lang = "python" if edit.path.endswith(".py") else "text"
                console.print(
                    Panel(
                        Syntax(edit.new_content, lang, theme="ansi_dark", line_numbers=True),
                        title=f"[bold]{edit.path}[/bold] — {edit.rationale}",
                        border_style="dim",
                    )
                )

        # ---- Stage 6: verify (cross-tier panel) ---------------------------
        if _skip_verify_flag.get(False):
            console.rule("[dim]Stage 6: Verify — skipped (--no-verify)[/dim]")
        else:
            console.rule("[bold cyan]Stage 6: Verify[/bold cyan]")
            verification = await verify_proposal(intent, proposal, existing_contents)
            console.print(_format_panel_verdict(verification))
            console.print(f"[dim]Judge:[/dim] {verification.judge_reasoning}")
            if verification.consensus_verdict == "reject":
                console.print(
                    "[red]Verifier panel rejected the proposal. Aborting before "
                    "apply.[/red]"
                )
                status = "rejected"
                return 6

        # ---- Stage 7: Gate #3 + Apply -------------------------------------
        console.rule("[bold cyan]Stage 7: Apply[/bold cyan]")
        gate_payload = _format_gate3_payload(proposal, existing_contents)
        decision = show_and_confirm("apply", gate_payload)
        gates.append(decision)
        if decision.action == "abort":
            console.print("[red]Aborted at apply gate. Repo untouched.[/red]")
            status = "aborted_apply"
            return 7
        if decision.action == "edit":
            console.print(
                "[yellow]Edits aren't applied at Gate #3 — re-run with a refined "
                "request to regenerate the proposal.[/yellow]"
            )
            console.print(f"[dim]Your note:[/dim] {decision.edited_payload}")
            status = "aborted_apply"
            return 7

        try:
            apply_result = await apply_changes(
                repo, proposal, intent.canonical_request
            )
        except ValueError as exc:
            console.print(f"[red]Applier refused: {exc}[/red]")
            status = "errored"
            return 7

        if apply_result.rolled_back:
            console.rule("[bold red]Rolled back[/bold red]")
            console.print(
                Panel(
                    f"[bold]Reason:[/bold] {apply_result.rollback_reason}\n\n"
                    f"Branch [cyan]{apply_result.branch_name}[/cyan] was created, "
                    "the files were written, tests were run — they failed, so "
                    "the branch + commit have been destroyed. Your repo is "
                    "identical to before this run.",
                    title="[bold red]Apply failed — repo state restored[/bold red]",
                    border_style="red",
                )
            )
            if apply_result.test_result:
                console.print("[dim]Test output (last 500 chars):[/dim]")
                tail = (apply_result.test_result.stdout or apply_result.test_result.stderr)[-500:]
                console.print(Panel(tail or "(empty)", border_style="dim"))
            status = "rolled_back"
            return 8

        console.rule("[bold green]Applied[/bold green]")
        console.print(
            Panel(
                f"[bold]Branch:[/bold] [cyan]{apply_result.branch_name}[/cyan]\n"
                f"[bold]Commit:[/bold] [cyan]{apply_result.applied_commit[:12]}[/cyan]\n"
                f"[bold]Tests:[/bold] passed "
                f"(exit={apply_result.test_result.exit_code}, "
                f"runtime={apply_result.test_result.runtime_ms} ms)\n\n"
                f"You're on the new branch. To merge:\n"
                f"  [dim]git checkout main && git merge {apply_result.branch_name}[/dim]\n"
                f"To discard:\n"
                f"  [dim]git checkout main && git branch -D {apply_result.branch_name}[/dim]",
                title="[bold green]Apply succeeded[/bold green]",
                border_style="green",
            )
        )

        # ---- Stage 8: catalog refresh (incremental) -----------------------
        console.rule("[bold cyan]Stage 8: Catalog refresh[/bold cyan]")
        refresh = await refresh_catalog_after_apply(repo)
        console.print(
            f"[dim]Catalog updated: "
            f"{refresh.files_resummarized} re-summarized, "
            f"{refresh.files_added} added, "
            f"{refresh.files_unchanged} unchanged (of {refresh.files_total}).[/dim]"
        )
        status = "success"
        return 0
    finally:
        save_run(
            repo_path=repo,
            kind="implement",
            request=request,
            status=status,
            started_at=started_at,
            intent=intent,
            verification=verification,
            apply_result=apply_result,
            gates=gates,
        )


async def _implement_async(repo: Path, request: str, rebuild: bool) -> int:
    """Deprecated direct entrypoint for the implement pipeline.

    Kept so the `mapipe implement` Typer command still works. Pins
    intent.kind='implement' even when the Router disagrees (the old contract
    callers expect), then delegates Stages 3-8 to ``_run_implement_pipeline``.

    Mirrors ``_ask_async`` 's try/finally + delegated flag so a kind=
    'implement' RunRow is persisted on Stage 1/2 failure, while successful
    runs let the helper save its own row (no double-record).
    """
    repo = repo.resolve()
    started_at = datetime.now(timezone.utc)
    gates: list[GateDecision] = []
    intent: Intent | None = None
    status = "errored"
    delegated = False

    try:
        # ---- Stage 1: catalog ---------------------------------------------
        console.rule("[bold cyan]Stage 1: Catalog[/bold cyan]")
        prior = load_catalog(repo)
        try:
            catalog = await index_repo(repo, force_rebuild=rebuild)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1

        stats = index_stats(prior, catalog)
        table = Table(show_header=True, header_style="bold")
        table.add_column("total")
        table.add_column("added")
        table.add_column("modified")
        table.add_column("unchanged")
        table.add_row(
            str(stats["total"]),
            str(stats["added"]),
            str(stats["modified"]),
            str(stats["unchanged"]),
        )
        console.print(table)

        # ---- Stage 2: intent + Gate #1 (kind pinned to implement) ---------
        console.rule("[bold cyan]Stage 2: Intent[/bold cyan]")
        intent = await classify_intent(request)
        if intent.kind != "implement":
            console.print(
                f"[yellow]Router classified as '{intent.kind}'. Forcing kind=implement "
                "because the user invoked `implement`.[/yellow]"
            )
            intent = intent.model_copy(update={"kind": "implement"})
        decision = show_and_confirm("intent", _format_intent(intent))
        gates.append(decision)
        if decision.action == "abort":
            console.print("[red]Aborted at intent gate.[/red]")
            status = "aborted_intent"
            return 2
        if decision.action == "edit":
            revised = f"{request}\n\nUser correction: {decision.edited_payload}"
            intent = await classify_intent(revised)
            intent = intent.model_copy(update={"kind": "implement"})
            console.print("[green]Re-classified after edit:[/green]")
            console.print(_format_intent(intent))

        delegated = True
        return await _run_implement_pipeline(
            repo, catalog, intent, request, started_at, preceding_gates=gates
        )
    finally:
        if not delegated:
            save_run(
                repo_path=repo,
                kind="implement",
                request=request,
                status=status,
                started_at=started_at,
                intent=intent,
                gates=gates,
            )


@app.command()
def implement(
    repo: Path = typer.Argument(..., exists=True, file_okay=False, help="Target git repo"),
    request: str = typer.Argument(..., help="The change you want made"),
    rebuild_index: bool = typer.Option(
        False, "--rebuild-index", help="Discard cached catalog and re-summarize every file."
    ),
    auto_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run)."
    ),
    show_edits: bool = typer.Option(
        False, "--show-edits", help="Print full proposed file contents (verbose)."
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip the cross-tier verifier panel (saves 4 LLM calls)."
    ),
    no_route: bool = typer.Option(
        False, "--no-route", help="Force Opus 4.6 for the generator (skip the complexity router)."
    ),
) -> None:
    """[DEPRECATED] Plan, generate, verify, and apply a change to a repo.

    Prefer `mapipe ask` — it auto-routes per turn, so the same command
    handles both questions and change requests, and you can switch between
    them in one conversation.

    This command still works (it pins kind='implement' even if the Router
    classifies the input as a question), but will be removed in a future
    release.
    """
    console.print(
        Panel(
            "[bold]`mapipe implement` is deprecated.[/bold]\n\n"
            "Use [cyan]mapipe ask[/cyan] instead — it auto-routes each turn "
            "between Q&A and the full implement pipeline (Plan -> Gate #2 -> "
            "Generate -> Verify -> Apply -> Gate #3), and you can switch "
            "between them in the same conversation.\n\n"
            "Continuing with the legacy `implement` flow for now (kind pinned).",
            title="[bold yellow]Deprecation notice[/bold yellow]",
            border_style="yellow",
        )
    )
    if auto_confirm:
        os.environ[AUTO_CONFIRM_ENV] = "1"
    _show_edits_flag.set(show_edits)
    _skip_verify_flag.set(no_verify)
    _no_route_flag.set(no_route)
    exit_code = asyncio.run(_implement_async(repo, request, rebuild_index))
    raise typer.Exit(exit_code)


def _print_report(report: dict) -> None:
    if report["total_runs"] == 0:
        console.print("[yellow]No runs recorded yet — try `ask` or `implement` first.[/yellow]")
        return

    # ---- Headline -------------------------------------------------------
    console.print(f"[bold]Total runs:[/bold] {report['total_runs']}")
    console.print()

    # ---- Runs by kind × status ------------------------------------------
    by_ks = report["by_kind_status"]
    kinds = known_kinds(by_ks.keys())
    statuses = known_statuses(by_ks.keys())
    table = Table(title="Runs by kind × status", show_header=True, header_style="bold")
    table.add_column("status", style="cyan")
    for k in kinds:
        table.add_column(k, justify="right")
    for s in statuses:
        row = [s]
        for k in kinds:
            row.append(str(by_ks.get((k, s), 0)) or "-")
        table.add_row(*row)
    console.print(table)

    # ---- Latency --------------------------------------------------------
    lat = report["latency"]
    console.print(
        f"[bold]Latency (success runs):[/bold] "
        f"p50={lat['p50']} ms, p95={lat['p95']} ms (n={lat['count']})"
    )
    console.print()

    # ---- Gate actions ---------------------------------------------------
    ga = report["gate_actions"]
    if ga:
        gtable = Table(title="HITL gate actions", show_header=True, header_style="bold")
        gtable.add_column("gate", style="cyan")
        gtable.add_column("confirm", justify="right", style="green")
        gtable.add_column("edit", justify="right", style="yellow")
        gtable.add_column("abort", justify="right", style="red")
        for gate in ("intent", "plan", "apply"):
            row_total = sum(ga.get((gate, a), 0) for a in ("confirm", "edit", "abort"))
            if row_total == 0:
                continue
            gtable.add_row(
                gate,
                str(ga.get((gate, "confirm"), 0)),
                str(ga.get((gate, "edit"), 0)),
                str(ga.get((gate, "abort"), 0)),
            )
        console.print(gtable)

    # ---- Verifier panel -------------------------------------------------
    rv = report["reviewer_verdicts"]
    if rv:
        agree = report["panel_agreement"]
        console.print(
            f"[bold]Panel agreement:[/bold] mean={agree['mean']:.2f} (n={int(agree['n'])})"
        )
        models = sorted({m for m, _ in rv.keys()})
        rtable = Table(title="Verifier verdicts by model", show_header=True, header_style="bold")
        rtable.add_column("model", style="cyan")
        rtable.add_column("approve", justify="right", style="green")
        rtable.add_column("suggest", justify="right", style="yellow")
        rtable.add_column("reject", justify="right", style="red")
        for m in models:
            rtable.add_row(
                _short_model(m),
                str(rv.get((m, "approve"), 0)),
                str(rv.get((m, "suggest"), 0)),
                str(rv.get((m, "reject"), 0)),
            )
        console.print(rtable)

    # ---- Apply outcomes -------------------------------------------------
    ao = report["apply_outcomes"]
    if ao["attempted"] > 0:
        console.print(
            f"[bold]Apply outcomes:[/bold] "
            f"attempted={ao['attempted']}, "
            f"applied={ao['applied']}, "
            f"rolled_back={ao['rolled_back']}, "
            f"pass_rate={ao['pass_rate_pct']}%"
        )


@app.command()
def report() -> None:
    """Print a summary of past runs from runs.db."""
    _print_report(compute_report())


if __name__ == "__main__":
    app()
