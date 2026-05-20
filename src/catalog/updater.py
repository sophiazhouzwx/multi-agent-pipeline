"""Post-apply catalog refresh.

After the Applier commits new file contents, this updater walks the repo
again and re-summarizes ONLY the files whose content hash changed —
typically just the files the Applier wrote. Untouched files keep their
existing purpose line verbatim (no LLM call).

Implementation note: the hash-check / cache-hit logic already lives in
``src.catalog.indexer.index_repo`` — this module is a focused entry point
that returns typed stats the orchestrator can persist alongside the
RepoRun in the storage layer.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from src.catalog.indexer import index_repo, index_stats, load_catalog
from src.schemas import Catalog


class CatalogRefreshResult(BaseModel):
    catalog: Catalog
    files_resummarized: int
    files_added: int
    files_unchanged: int
    files_total: int


async def refresh_catalog_after_apply(repo_path: Path) -> CatalogRefreshResult:
    """Refresh the catalog after files have been written.

    Walks the repo, hash-checks each file, re-summarizes only what changed,
    rewrites the AGENT_CATALOG.md + catalog.json. Returns typed stats.
    """
    prior = load_catalog(repo_path)
    updated = await index_repo(repo_path)
    stats = index_stats(prior, updated)
    return CatalogRefreshResult(
        catalog=updated,
        files_resummarized=stats["modified"],
        files_added=stats["added"],
        files_unchanged=stats["unchanged"],
        files_total=stats["total"],
    )
