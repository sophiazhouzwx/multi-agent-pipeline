"""Answerer agent (Opus).

Given a typed Intent, a Catalog, the Locator's pick, and the actual contents
of the located files, produces a typed Answer that cites which files it
referenced. Used only by the Q&A path of the pipeline.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src._retry import run_with_retry
from src.config import GENERATOR_MODEL
from src.schemas import Answer, Catalog, Intent, LocatedFiles


_ANSWERER_INSTRUCTIONS = (
    "You answer questions about a code repository using only the provided "
    "file excerpts and catalog summaries. Rules:\n"
    "- Be specific. Cite file paths (and line numbers when relevant) inline in "
    "the answer, e.g. `src/foo.py:42`.\n"
    "- If the excerpts don't contain enough information to answer confidently, "
    "say so explicitly rather than guessing.\n"
    "- Keep the answer focused: address exactly the question asked, no more.\n"
    "- If a 'Previous conversation' section is provided, treat the current "
    "question as a follow-up. Stay consistent with prior turns but pivot to "
    "new files / new code when the follow-up changes topic.\n\n"
    "Output fields:\n"
    "- body: the answer in clear prose with inline path citations.\n"
    "- cited_files: the list of file paths your answer actually referenced."
)


answerer_agent = Agent(
    GENERATOR_MODEL,
    output_type=Answer,
    instructions=_ANSWERER_INSTRUCTIONS,
    # The Answerer sometimes gets long conversation histories + many file
    # excerpts and emits an empty output. Give the model a few more chances
    # to produce a valid Answer before raising UnexpectedModelBehavior.
    retries=3,
)


def _format_excerpts(file_contents: dict[str, str]) -> str:
    sections: list[str] = []
    for path, content in file_contents.items():
        sections.append(f"### `{path}`\n```\n{content}\n```")
    return "\n\n".join(sections)


async def answer_question(
    intent: Intent,
    catalog: Catalog,
    located: LocatedFiles,
    file_contents: dict[str, str],
    *,
    prior_turns: list[tuple[str, str]] | None = None,
) -> Answer:
    """Produce a typed Answer for the user's question.

    ``prior_turns`` carries earlier (question, answer) pairs from the same
    conversation. When provided, the Answerer is told to treat the current
    question as a follow-up and stay consistent with the discussion so far.
    """
    parts: list[str] = [
        f"Repo: {catalog.repo_path} @ {catalog.git_commit[:8]}",
    ]
    if prior_turns:
        parts.append("")
        parts.append("Previous conversation:")
        for i, (q, a) in enumerate(prior_turns, 1):
            parts.append(f"\nTurn {i} — Q: {q}")
            parts.append(f"Turn {i} — A: {a}")
        parts.append("")
        parts.append(f"Current (follow-up) question: {intent.canonical_request}")
    else:
        parts.append(f"Question: {intent.canonical_request}")
    parts.append("")
    parts.append(f"Locator reasoning: {located.reasoning}")
    parts.append("")
    parts.append(f"File excerpts:\n\n{_format_excerpts(file_contents)}")

    prompt = "\n".join(parts)
    result = await run_with_retry(
        lambda: answerer_agent.run(prompt), label="answerer"
    )
    return result.output
