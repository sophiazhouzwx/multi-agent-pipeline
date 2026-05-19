"""Answerer agent (Opus).

Given a typed Intent, a Catalog, the Locator's pick, and the actual contents
of the located files, produces a typed Answer that cites which files it
referenced. Used only by the Q&A path of the pipeline.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.config import GENERATOR_MODEL
from src.schemas import Answer, Catalog, Intent, LocatedFiles


_ANSWERER_INSTRUCTIONS = (
    "You answer questions about a code repository using only the provided "
    "file excerpts and catalog summaries. Rules:\n"
    "- Be specific. Cite file paths (and line numbers when relevant) inline in "
    "the answer, e.g. `src/foo.py:42`.\n"
    "- If the excerpts don't contain enough information to answer confidently, "
    "say so explicitly rather than guessing.\n"
    "- Keep the answer focused: address exactly the question asked, no more.\n\n"
    "Output fields:\n"
    "- body: the answer in clear prose with inline path citations.\n"
    "- cited_files: the list of file paths your answer actually referenced."
)


answerer_agent = Agent(
    GENERATOR_MODEL,
    output_type=Answer,
    instructions=_ANSWERER_INSTRUCTIONS,
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
) -> Answer:
    """Produce a typed Answer for the user's question."""
    prompt = (
        f"Repo: {catalog.repo_path} @ {catalog.git_commit[:8]}\n"
        f"Question: {intent.canonical_request}\n\n"
        f"Locator reasoning: {located.reasoning}\n\n"
        f"File excerpts:\n\n{_format_excerpts(file_contents)}"
    )
    result = await answerer_agent.run(prompt)
    return result.output
