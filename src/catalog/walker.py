"""Repo walking and content hashing.

Yields files worth indexing: respects ``.gitignore`` and a hardcoded set of
default exclusions (caches, virtualenvs, build outputs, the catalog itself).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

import pathspec


# Always-skip patterns, even when .gitignore is empty.
DEFAULT_EXCLUDES = pathspec.PathSpec.from_lines(
    "gitignore",
    [
        ".git/",
        ".venv/",
        "venv/",
        "env/",
        "node_modules/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "dist/",
        "build/",
        "*.egg-info/",
        ".DS_Store",
        ".agent_catalog/",
        "AGENT_CATALOG.md",
        "*.lock",
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "yarn.lock",
    ],
)

# File extensions we can extract meaning from.
SUPPORTED_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".sh",
        ".bash",
        ".zsh",
        ".md",
        ".rst",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".sql",
        ".html",
        ".css",
    }
)

# Extension-less files we still want (root config + scripts).
SUPPORTED_BASENAMES: frozenset[str] = frozenset({"Dockerfile", "Makefile", "Procfile"})

MAX_FILE_BYTES = 200_000  # files larger than this are skipped for summarization


def _load_gitignore(repo_path: Path) -> pathspec.PathSpec:
    gi = repo_path / ".gitignore"
    if not gi.exists():
        return pathspec.PathSpec.from_lines("gitignore", [])
    try:
        return pathspec.PathSpec.from_lines(
            "gitignore", gi.read_text(encoding="utf-8", errors="replace").splitlines()
        )
    except OSError:
        return pathspec.PathSpec.from_lines("gitignore", [])


def _is_supported(p: Path) -> bool:
    if p.suffix:
        return p.suffix in SUPPORTED_EXTS
    return p.name in SUPPORTED_BASENAMES


def iter_files(repo_path: Path, max_files: int | None = None) -> Iterator[Path]:
    """Yield absolute paths of indexable files under ``repo_path``.

    Sorted for deterministic output; respects .gitignore plus DEFAULT_EXCLUDES;
    enforces SUPPORTED_EXTS / SUPPORTED_BASENAMES; skips files larger than
    MAX_FILE_BYTES; stops after ``max_files`` if provided.
    """
    user_spec = _load_gitignore(repo_path)
    count = 0
    for p in sorted(repo_path.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_path)
        rel_str = str(rel)
        if DEFAULT_EXCLUDES.match_file(rel_str):
            continue
        if user_spec.match_file(rel_str):
            continue
        if not _is_supported(p):
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield p
        count += 1
        if max_files is not None and count >= max_files:
            return


def sha256_of(path: Path) -> str:
    """SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
