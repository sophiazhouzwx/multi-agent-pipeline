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
import os  # noqa: E402
from pathlib import Path  # noqa: E402

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from src.agents.answerer import answer_question  # noqa: E402
from src.agents.locator import locate  # noqa: E402
from src.agents.router import classify_intent  # noqa: E402
from src.catalog.indexer import index_repo, index_stats, load_catalog  # noqa: E402
from src.hitl.gate import AUTO_CONFIRM_ENV, show_and_confirm  # noqa: E402
from src.schemas import Intent  # noqa: E402

app = typer.Typer(
    help="Multi-agent repo-aware coding assistant",
    no_args_is_help=True,
)
console = Console()


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


if __name__ == "__main__":
    app()
