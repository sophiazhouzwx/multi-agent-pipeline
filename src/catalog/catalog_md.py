"""Render a typed ``Catalog`` to AGENT_CATALOG.md (human-readable)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from src.schemas import Catalog


def render_catalog_md(catalog: Catalog) -> str:
    """Render a Catalog as AGENT_CATALOG.md text."""
    lines: list[str] = []
    lines.append("# AGENT_CATALOG.md")
    lines.append("")
    lines.append(
        f"> generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        "by multi-agent-pipeline"
    )
    lines.append(f"> repo: `{catalog.repo_path}` @ `{catalog.git_commit[:8]}`")
    lines.append(
        "> Agents read this instead of crawling the repo. "
        "One anchor per file; only re-summarized when content changes."
    )
    lines.append("")
    lines.append(f"_{len(catalog.files)} files indexed._")
    lines.append("")
    lines.append("## Tree")
    lines.append("")
    lines.append("```")
    for line in _render_tree([f.path for f in catalog.files]):
        lines.append(line)
    lines.append("```")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for f in catalog.files:
        lines.append(f"### `{f.path}`")
        lines.append("")
        lines.append(f"**Purpose:** {f.purpose or '_(no summary)_'}")
        if f.public_symbols:
            lines.append("")
            lines.append("**Public symbols:**")
            for s in f.public_symbols:
                summary = f" — {s.summary}" if s.summary else ""
                lines.append(f"- `{s.signature}`{summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_tree(paths: list[str]) -> list[str]:
    """Plain indented tree listing — readable, no fancy unicode."""
    out: list[str] = []
    seen_dirs: set[str] = set()
    for p in sorted(paths):
        parts = PurePosixPath(p).parts
        for i in range(len(parts) - 1):
            d = "/".join(parts[: i + 1])
            if d in seen_dirs:
                continue
            seen_dirs.add(d)
            out.append("  " * i + f"{parts[i]}/")
        out.append("  " * (len(parts) - 1) + parts[-1])
    return out
