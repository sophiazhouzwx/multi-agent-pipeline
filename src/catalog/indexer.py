"""Top-level indexer: build or incrementally refresh a repo's catalog.

Flow:
  1. Validate the target is a git repo (refuse otherwise).
  2. Load any prior catalog from ``.agent_catalog/catalog.json``.
  3. Walk the repo. For each file:
     - If a prior entry exists AND its content_hash matches now -> reuse the
       prior purpose verbatim. NO LLM call.
     - Else -> queue for fresh Haiku summarization.
  4. Fan out summaries with bounded concurrency.
  5. Write updated catalog.json + AGENT_CATALOG.md.

The catalog.json is the source of truth (typed, includes hashes). The .md is
a rendered, human-readable export.
"""

from __future__ import annotations

from pathlib import Path

from git import InvalidGitRepositoryError
from git import Repo as GitRepo

from src.catalog.catalog_md import render_catalog_md
from src.catalog.summarizer import summarize_batch
from src.catalog.symbols import extract_symbols
from src.catalog.walker import iter_files, sha256_of
from src.schemas import Catalog, CatalogFile

SIDECAR_DIR = ".agent_catalog"
SIDECAR_JSON = "catalog.json"
CATALOG_MD = "AGENT_CATALOG.md"


def sidecar_path(repo_path: Path) -> Path:
    return repo_path / SIDECAR_DIR / SIDECAR_JSON


def md_path(repo_path: Path) -> Path:
    return repo_path / CATALOG_MD


def ensure_git_repo(repo_path: Path) -> str:
    """Return the current HEAD sha, or raise ValueError if not a git repo."""
    try:
        repo = GitRepo(repo_path)
    except InvalidGitRepositoryError as exc:
        raise ValueError(f"{repo_path} is not a git repository") from exc
    try:
        return repo.head.commit.hexsha
    except Exception:
        # Brand-new repo with no commits yet — index anyway with placeholder.
        return "0" * 40


def load_catalog(repo_path: Path) -> Catalog | None:
    p = sidecar_path(repo_path)
    if not p.exists():
        return None
    try:
        return Catalog.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_catalog(catalog: Catalog) -> None:
    repo_path = Path(catalog.repo_path)
    (repo_path / SIDECAR_DIR).mkdir(exist_ok=True)
    sidecar_path(repo_path).write_text(
        catalog.model_dump_json(indent=2), encoding="utf-8"
    )
    md_path(repo_path).write_text(render_catalog_md(catalog), encoding="utf-8")


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


async def index_repo(
    repo_path: Path,
    max_files: int | None = None,
    force_rebuild: bool = False,
) -> Catalog:
    """Build or incrementally update the catalog for ``repo_path``.

    Returns the up-to-date Catalog and writes both sidecar + markdown.
    """
    repo_path = repo_path.resolve()
    commit = ensure_git_repo(repo_path)

    existing = None if force_rebuild else load_catalog(repo_path)
    existing_by_path: dict[str, CatalogFile] = (
        {f.path: f for f in existing.files} if existing else {}
    )

    new_files: list[CatalogFile] = []
    to_summarize: list[tuple[str, str]] = []
    summarize_slots: list[int] = []  # indexes in new_files awaiting purpose

    for abs_path in iter_files(repo_path, max_files=max_files):
        rel = str(abs_path.relative_to(repo_path))
        content_hash = sha256_of(abs_path)
        source = _read_text(abs_path)
        prior = existing_by_path.get(rel)

        if prior and prior.content_hash == content_hash:
            # Unchanged file: reuse the existing purpose (no LLM call).
            # Symbols are re-extracted; it's cheap and keeps the catalog
            # consistent if the symbol extractor improves over time.
            new_files.append(
                CatalogFile(
                    path=rel,
                    purpose=prior.purpose,
                    public_symbols=extract_symbols(abs_path, source),
                    content_hash=content_hash,
                )
            )
            continue

        # New or modified file — placeholder purpose, filled in below.
        new_files.append(
            CatalogFile(
                path=rel,
                purpose="",
                public_symbols=extract_symbols(abs_path, source),
                content_hash=content_hash,
            )
        )
        summarize_slots.append(len(new_files) - 1)
        to_summarize.append((rel, source))

    if to_summarize:
        purposes = await summarize_batch(to_summarize)
        for slot, purpose in zip(summarize_slots, purposes):
            new_files[slot] = new_files[slot].model_copy(update={"purpose": purpose})

    catalog = Catalog(repo_path=repo_path, git_commit=commit, files=new_files)
    save_catalog(catalog)
    return catalog


def index_stats(prior: Catalog | None, current: Catalog) -> dict[str, int]:
    """Diff stats useful for the CLI to print after an index run."""
    if prior is None:
        return {"total": len(current.files), "added": len(current.files), "modified": 0, "unchanged": 0}
    prior_by_path = {f.path: f for f in prior.files}
    added = modified = unchanged = 0
    for f in current.files:
        p = prior_by_path.get(f.path)
        if p is None:
            added += 1
        elif p.content_hash != f.content_hash:
            modified += 1
        else:
            unchanged += 1
    return {
        "total": len(current.files),
        "added": added,
        "modified": modified,
        "unchanged": unchanged,
    }
