"""Planner agent (Opus).

Given a typed Intent (kind='implement') plus the contents of the files the
Locator picked, produces a typed ChangePlan: a high-level, ordered narrative
of what will be changed. The Planner does NOT write code — the Generator
(Step 8) consumes this plan and produces the actual FileEdits.

The plan is what the user reviews at HITL Gate #2: agreeing the scope and
file list BEFORE we burn Opus tokens generating code.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.config import GENERATOR_MODEL
from src.schemas import ChangePlan, Intent, LocatedFiles


_PLANNER_INSTRUCTIONS = (
    "You produce a typed CHANGE PLAN for a code-modification request. "
    "You do NOT write code — the Generator agent will do that from your plan.\n\n"
    "Input:\n"
    "- The user's canonical request (already paraphrased by the Intent Router).\n"
    "- The relevant files with their FULL CONTENTS (picked by the Locator).\n\n"
    "Output fields:\n"
    "- summary: 1-2 sentences describing the overall change.\n"
    "- affected_files: file paths that will be created or modified. Use the "
    "EXACT paths shown in the provided files for edits; new files use their "
    "proposed repo-relative path.\n"
    "- steps: ordered list of short, specific sentences describing WHAT changes, "
    "not HOW. Each step touches one concept or one file. Aim for 2-6 steps.\n\n"
    "Rules:\n"
    "- Be SPECIFIC. 'Add a --json flag to parse_cmd in src/cli.py' beats "
    "'improve the CLI'.\n"
    "- Be MINIMAL. Don't add unrelated refactors or polish. Match the user's "
    "scope exactly.\n"
    "- Skip test edits unless the user asked. Existing tests are run by the "
    "Applier; new tests are a separate request.\n"
    "- If the request is impossible or unclear from the provided files, set "
    "summary to explain the problem and leave affected_files / steps empty."
)


planner_agent = Agent(
    GENERATOR_MODEL,
    output_type=ChangePlan,
    instructions=_PLANNER_INSTRUCTIONS,
)


def _format_files_for_prompt(file_contents: dict[str, str]) -> str:
    """Render the located files compactly for the planner prompt."""
    sections: list[str] = []
    for path, content in file_contents.items():
        sections.append(f"### `{path}`\n```\n{content}\n```")
    return "\n\n".join(sections)


async def plan_change(
    intent: Intent,
    located: LocatedFiles,
    file_contents: dict[str, str],
) -> ChangePlan:
    """Produce a typed ChangePlan from the user's request + located files."""
    prompt = (
        f"Canonical request: {intent.canonical_request}\n"
        f"Locator reasoning: {located.reasoning}\n\n"
        f"Files to consider:\n\n{_format_files_for_prompt(file_contents)}"
    )
    result = await planner_agent.run(prompt)
    return result.output
