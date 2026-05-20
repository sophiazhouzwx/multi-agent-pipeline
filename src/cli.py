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
from pathlib import Path  # noqa: E402

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402

from src.agents.answerer import answer_question  # noqa: E402
from src.agents.generator import generate_changes  # noqa: E402
from src.agents.locator import locate  # noqa: E402
from src.agents.planner import plan_change  # noqa: E402
from src.agents.router import classify_intent  # noqa: E402
from src.apply.applier import apply_changes  # noqa: E402
from src.catalog.indexer import index_repo, index_stats, load_catalog  # noqa: E402
from src.hitl.gate import AUTO_CONFIRM_ENV, show_and_confirm  # noqa: E402
from src.pipeline.verifier_panel import verify_proposal  # noqa: E402
from src.schemas import ChangePlan, ChangeProposal, Intent, PanelVerdict  # noqa: E402

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


async def _ask_async(repo: Path, question: str, rebuild: bool) -> int:
    repo = repo.resolve()

    # ---- Stage 1: catalog --------------------------------------------------
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

    # ---- Stage 2: intent + Gate #1 ----------------------------------------
    console.rule("[bold cyan]Stage 2: Intent[/bold cyan]")
    intent = await classify_intent(question)
    decision = show_and_confirm("intent", _format_intent(intent))
    if decision.action == "abort":
        console.print("[red]Aborted at intent gate.[/red]")
        return 2
    if decision.action == "edit":
        revised_message = f"{question}\n\nUser correction: {decision.edited_payload}"
        intent = await classify_intent(revised_message)
        console.print("[green]Re-classified after edit:[/green]")
        console.print(_format_intent(intent))

    # ---- Stage 3: locate --------------------------------------------------
    console.rule("[bold cyan]Stage 3: Locate[/bold cyan]")
    located = await locate(catalog, intent)
    if not located.paths:
        console.print("[yellow]No files matched the request.[/yellow]")
        return 3
    console.print(f"[bold]Located:[/bold] {', '.join(located.paths)}")
    console.print(f"[dim]Reasoning:[/dim] {located.reasoning}")

    # ---- Stage 4: answer --------------------------------------------------
    console.rule("[bold cyan]Stage 4: Answer[/bold cyan]")
    file_contents = {p: _read_file(repo / p) for p in located.paths}
    answer = await answer_question(intent, catalog, located, file_contents)
    console.print(
        Panel(answer.body, title="[bold green]Answer[/bold green]", border_style="green")
    )
    if answer.cited_files:
        console.print(f"[dim]Cited:[/dim] {', '.join(answer.cited_files)}")
    return 0


@app.command()
def ask(
    repo: Path = typer.Argument(..., exists=True, file_okay=False, help="Target git repo"),
    question: str = typer.Argument(..., help="Your question about the repo"),
    rebuild_index: bool = typer.Option(
        False, "--rebuild-index", help="Discard cached catalog and re-summarize every file."
    ),
    auto_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run)."
    ),
) -> None:
    """Ask a question about a repo and get an answer with file citations."""
    if auto_confirm:
        os.environ[AUTO_CONFIRM_ENV] = "1"
    exit_code = asyncio.run(_ask_async(repo, question, rebuild_index))
    raise typer.Exit(exit_code)


async def _implement_async(repo: Path, request: str, rebuild: bool) -> int:
    repo = repo.resolve()

    # ---- Stage 1: catalog --------------------------------------------------
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

    # ---- Stage 2: intent + Gate #1 ----------------------------------------
    console.rule("[bold cyan]Stage 2: Intent[/bold cyan]")
    intent = await classify_intent(request)
    # User invoked `implement` — pin the kind even if Router thought it was a question.
    if intent.kind != "implement":
        console.print(
            f"[yellow]Router classified as '{intent.kind}'. Forcing kind=implement "
            "because the user invoked `implement`.[/yellow]"
        )
        intent = intent.model_copy(update={"kind": "implement"})
    decision = show_and_confirm("intent", _format_intent(intent))
    if decision.action == "abort":
        console.print("[red]Aborted at intent gate.[/red]")
        return 2
    if decision.action == "edit":
        revised = f"{request}\n\nUser correction: {decision.edited_payload}"
        intent = await classify_intent(revised)
        intent = intent.model_copy(update={"kind": "implement"})
        console.print("[green]Re-classified after edit:[/green]")
        console.print(_format_intent(intent))

    # ---- Stage 3: locate --------------------------------------------------
    console.rule("[bold cyan]Stage 3: Locate[/bold cyan]")
    located = await locate(catalog, intent)
    if not located.paths:
        console.print("[yellow]No files matched the request.[/yellow]")
        return 3
    console.print(f"[bold]Located:[/bold] {', '.join(located.paths)}")
    console.print(f"[dim]Reasoning:[/dim] {located.reasoning}")

    # ---- Stage 4: plan + Gate #2 ------------------------------------------
    console.rule("[bold cyan]Stage 4: Plan[/bold cyan]")
    file_contents = {p: _read_file(repo / p) for p in located.paths}
    plan = await plan_change(intent, located, file_contents)
    decision = show_and_confirm("plan", _format_plan(plan))
    if decision.action == "abort":
        console.print("[red]Aborted at plan gate.[/red]")
        return 4
    if decision.action == "edit":
        # Re-run planner with the user's correction appended to the intent.
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

    # ---- Stage 5: generate -----------------------------------------------
    console.rule("[bold cyan]Stage 5: Generate[/bold cyan]")
    if not plan.affected_files:
        console.print("[yellow]Plan has no affected files — nothing to generate.[/yellow]")
        return 5
    # Read whatever EXISTING files the plan touches (NEW files won't exist yet).
    existing_contents: dict[str, str] = {}
    for path in plan.affected_files:
        abs_path = repo / path
        if abs_path.exists():
            existing_contents[path] = _read_file(abs_path)

    proposal = await generate_changes(intent, plan, existing_contents)
    if not proposal.edits:
        console.print("[red]Generator produced no edits.[/red]")
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

    # ---- Stage 6: verify (cross-tier panel) ------------------------------
    if _skip_verify_flag.get(False):
        console.rule("[dim]Stage 6: Verify — skipped (--no-verify)[/dim]")
    else:
        console.rule("[bold cyan]Stage 6: Verify[/bold cyan]")
        panel_verdict = await verify_proposal(intent, proposal, existing_contents)
        console.print(_format_panel_verdict(panel_verdict))
        console.print(f"[dim]Judge:[/dim] {panel_verdict.judge_reasoning}")
        if panel_verdict.consensus_verdict == "reject":
            console.print(
                "[red]Verifier panel rejected the proposal. Aborting before "
                "apply.[/red]"
            )
            return 6

    # ---- Stage 7: Gate #3 + Apply -----------------------------------------
    console.rule("[bold cyan]Stage 7: Apply[/bold cyan]")
    gate_payload = _format_gate3_payload(proposal, existing_contents)
    decision = show_and_confirm("apply", gate_payload)
    if decision.action == "abort":
        console.print("[red]Aborted at apply gate. Repo untouched.[/red]")
        return 7
    if decision.action == "edit":
        console.print(
            "[yellow]Edits aren't applied at Gate #3 — re-run with a refined "
            "request to regenerate the proposal.[/yellow]"
        )
        console.print(f"[dim]Your note:[/dim] {decision.edited_payload}")
        return 7

    try:
        apply_result = await apply_changes(
            repo, proposal, intent.canonical_request
        )
    except ValueError as exc:
        console.print(f"[red]Applier refused: {exc}[/red]")
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
    return 0


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
) -> None:
    """Plan, generate, verify, and apply a change to a repo.

    Full pipeline (Stages 1-7): Catalog -> Intent (Gate #1) -> Locate ->
    Plan (Gate #2) -> Generate -> Verify -> Apply (Gate #3 + git branch +
    tests + commit OR rollback).

    On apply: a new branch `agent/<slug>-<timestamp>` is created, files are
    written, the repo's pytest suite runs inside the sandbox. If tests pass
    the branch keeps the commit (you stay on it). If tests fail the branch
    + commit are destroyed and the repo is restored bit-for-bit.

    Refuses on a dirty working tree. Refuses on a non-git directory.
    """
    if auto_confirm:
        os.environ[AUTO_CONFIRM_ENV] = "1"
    _show_edits_flag.set(show_edits)
    _skip_verify_flag.set(no_verify)
    exit_code = asyncio.run(_implement_async(repo, request, rebuild_index))
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
