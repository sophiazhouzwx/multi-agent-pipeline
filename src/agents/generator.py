"""Generator agent (Opus).

Takes an approved ChangePlan plus the current contents of any existing files
it will touch, and produces one FileEdit per path in plan.affected_files.
Each FileEdit contains the FULL new file contents (not a diff) plus a
one-sentence rationale.

The generator emits whole files (not patches) for two reasons:
1. The Applier (Step 10) just writes the bytes — no patch-application logic.
2. The Verifier panel (Step 9) can review each file independently without
   needing to reconstruct intermediate state from diffs.

Diffs are computed at display time (Gate #3 preview) via stdlib ``difflib``.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.config import GENERATOR_MODEL
from src.schemas import ChangePlan, ChangeProposal, FileEdit, Intent


_GENERATOR_INSTRUCTIONS = (
    "You implement an approved change plan against a repository, producing "
    "one FileEdit per affected file.\n\n"
    "Input you receive:\n"
    "- The user's canonical request.\n"
    "- The approved ChangePlan (summary, ordered steps, affected_files).\n"
    "- For each EXISTING file you'll modify: its FULL current contents.\n"
    "- Any path in the plan's affected_files that doesn't appear in the "
    "existing contents is a NEW file you'll create from scratch.\n\n"
    "Output: a list of FileEdit objects, one per path in plan.affected_files.\n"
    "Each FileEdit has:\n"
    "- path: the EXACT path string from the plan.\n"
    "- new_content: the COMPLETE new file contents after your edit. Include "
    "every unchanged section — your output REPLACES the file entirely. "
    "Never include placeholders like '...' or 'TODO'.\n"
    "- rationale: ONE sentence describing what changed in this file.\n\n"
    "Rules:\n"
    "- Implement EXACTLY the approved plan. No unrelated refactors, tests, "
    "or polish.\n"
    "- Preserve existing formatting (indentation, spacing, comments, import "
    "ordering).\n"
    "- For Python files, keep type hints and docstring style consistent with "
    "the rest of the file.\n"
    "- If a planned change is impossible given the file contents, output the "
    "file with its current content UNCHANGED and explain the obstacle in the "
    "rationale. Do NOT invent a workaround."
)


generator_agent = Agent(
    GENERATOR_MODEL,
    output_type=list[FileEdit],
    instructions=_GENERATOR_INSTRUCTIONS,
)


def _format_inputs(plan: ChangePlan, file_contents: dict[str, str]) -> str:
    sections: list[str] = [
        "### Approved plan",
        f"Summary: {plan.summary}",
        "Steps:",
    ]
    for i, step in enumerate(plan.steps, 1):
        sections.append(f"  {i}. {step}")
    sections.append("Affected files:")
    for path in plan.affected_files:
        marker = "" if path in file_contents else "  (NEW)"
        sections.append(f"  - {path}{marker}")

    existing = {p: file_contents[p] for p in plan.affected_files if p in file_contents}
    if existing:
        sections.append("")
        sections.append("### Existing file contents")
        for path, content in existing.items():
            sections.append(f"#### `{path}`")
            sections.append("```")
            sections.append(content)
            sections.append("```")
    return "\n".join(sections)


async def generate_changes(
    intent: Intent,
    plan: ChangePlan,
    file_contents: dict[str, str],
) -> ChangeProposal:
    """Produce a typed ChangeProposal from an approved plan."""
    prompt = (
        f"Canonical request: {intent.canonical_request}\n\n"
        f"{_format_inputs(plan, file_contents)}"
    )
    result = await generator_agent.run(prompt)

    # Defensive filter: only accept edits whose path is in the approved plan.
    allowed = set(plan.affected_files)
    edits = [e for e in result.output if e.path in allowed]
    return ChangeProposal(plan=plan, edits=edits)
