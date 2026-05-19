# AGENT_CATALOG.md

> generated 2026-05-19T20:05:58+00:00 by multi-agent-pipeline
> repo: `/Users/c270744/multi-agent-pipeline` @ `6483326c`
> Agents read this instead of crawling the repo. One anchor per file; only re-summarized when content changes.

_35 files indexed._

## Tree

```
README.md
docs/
  PLAN-v1-coding-benchmark.md
  PLAN.md
pyproject.toml
src/
  __init__.py
  agents/
    __init__.py
    answerer.py
    locator.py
    router.py
  benchmarks/
    __init__.py
  catalog/
    __init__.py
    catalog_md.py
    indexer.py
    summarizer.py
    symbols.py
    walker.py
  cli.py
  config.py
  execution/
    __init__.py
    sandbox.py
  hitl/
    __init__.py
    gate.py
  metrics/
    __init__.py
  pipeline/
    __init__.py
  schemas.py
  storage/
    __init__.py
tests/
  __init__.py
  test_agents_router_locator.py
  test_answerer.py
  test_catalog_unit.py
  test_hitl_gate.py
  test_indexer.py
  test_sandbox.py
  test_schemas.py
  test_schemas_v2.py
```

## Files

### `README.md`

**Purpose:** Provides documentation and setup instructions for a multi-agent coding assistant pipeline that routes repository questions and implementation requests through typed Claude agents with human-in-the-loo

### `docs/PLAN-v1-coding-benchmark.md`

**Purpose:** Outlines the complete implementation plan for a multi-agent coding benchmark pipeline using PydanticAI to orchestrate three Claude tiers with evaluator loops, sandboxed execution, adaptive routing, an

### `docs/PLAN.md`

**Purpose:** Establishes the architectural design and workflow for a multi-agent, repo-aware coding assistant that uses persistent catalog indexing and human-in-the-loop gates to safely implement changes.

### `pyproject.toml`

**Purpose:** Defines project metadata, dependencies, and development requirements for the multi-agent pipeline application.

### `src/__init__.py`

**Purpose:** Marks the src directory as a Python package and serves as the entry point for package initialization.

### `src/agents/__init__.py`

**Purpose:** Exports public agent classes and utilities for easy import access across the agents module.

### `src/agents/answerer.py`

**Purpose:** Generates structured answers to user questions about code repositories by processing file excerpts and catalog information using an LLM agent.

**Public symbols:**
- `async def answer_question(intent: Intent, catalog: Catalog, located: LocatedFiles, file_contents: dict[str, str]) -> Answer` — Produce a typed Answer for the user's question.

### `src/agents/locator.py`

**Purpose:** Identifies the 1-5 most relevant files in a codebase catalog for a given user intent using Claude Sonnet, with hallucination filtering to ensure only valid paths are returned.

**Public symbols:**
- `async def locate(catalog: Catalog, intent: Intent) -> LocatedFiles` — Return the 1-5 files most relevant to ``intent``.

### `src/agents/router.py`

**Purpose:** Classifies user messages into question or implementation request intents and rewrites them in canonical form for downstream processing.

**Public symbols:**
- `async def classify_intent(user_message: str) -> Intent` — Return the model's typed Intent for a free-form user message.

### `src/benchmarks/__init__.py`

**Purpose:** Marks the benchmarks directory as a Python package for organizing and importing benchmark tests.

### `src/catalog/__init__.py`

**Purpose:** Designates the catalog directory as a Python package and exposes its public API.

### `src/catalog/catalog_md.py`

**Purpose:** Converts a typed Catalog object into human-readable AGENT_CATALOG.md markdown documentation with file tree, purposes, and public symbols.

**Public symbols:**
- `def render_catalog_md(catalog: Catalog) -> str` — Render a Catalog as AGENT_CATALOG.md text.

### `src/catalog/indexer.py`

**Purpose:** Orchestrates building or incrementally updating a repository's file catalog by validating git status, reusing unchanged file summaries, queuing new/modified files for LLM-based purpose generation, and

**Public symbols:**
- `def sidecar_path(repo_path: Path) -> Path`
- `def md_path(repo_path: Path) -> Path`
- `def ensure_git_repo(repo_path: Path) -> str` — Return the current HEAD sha, or raise ValueError if not a git repo.
- `def load_catalog(repo_path: Path) -> Catalog | None`
- `def save_catalog(catalog: Catalog) -> None`
- `async def index_repo(repo_path: Path, max_files: int | None=None, force_rebuild: bool=False) -> Catalog` — Build or incrementally update the catalog for ``repo_path``.
- `def index_stats(prior: Catalog | None, current: Catalog) -> dict[str, int]` — Diff stats useful for the CLI to print after an index run.

### `src/catalog/summarizer.py`

**Purpose:** Generates concise one-line purpose summaries for source files using Claude, with bounded concurrency for batch processing and content-hash-based caching integration.

**Public symbols:**
- `def make_summarizer_agent() -> Agent` — Construct a fresh summarizer agent. Tests can use ``agent.override``.
- `async def summarize_file(path_rel: str, source: str) -> str` — Return a 1-line purpose for a single file.
- `async def summarize_batch(items: list[tuple[str, str]], concurrency: int=5) -> list[str]` — Summarize many files with bounded concurrency. Preserves input order.

### `src/catalog/symbols.py`

**Purpose:** Extracts public symbols (functions, classes, constants) from source files with deterministic signatures and docstrings for catalog indexing.

**Public symbols:**
- `def extract_python_symbols(source: str) -> list[CatalogSymbol]` — Return public top-level functions/classes/constants from a Python source.
- `def extract_symbols(path: Path, source: str) -> list[CatalogSymbol]` — Dispatch by extension. Returns [] for unsupported languages.

### `src/catalog/walker.py`

**Purpose:** Walks a repository to discover indexable files while respecting `.gitignore` and exclusion rules, and provides hashing utilities for content deduplication.

**Public symbols:**
- `def iter_files(repo_path: Path, max_files: int | None=None) -> Iterator[Path]` — Yield absolute paths of indexable files under ``repo_path``.
- `def sha256_of(path: Path) -> str` — SHA-256 hex digest of a file's bytes.
- `def sha256_of_text(text: str) -> str`

### `src/cli.py`

**Purpose:** Defines the Typer CLI entry point with an `ask` subcommand that orchestrates a four-stage multi-agent pipeline (catalog, intent classification, file location, answer generation) for repo-aware Q&A.

**Public symbols:**
- `def ask(repo: Path=typer.Argument(..., exists=True, file_okay=False, help='Target git repo'), question: str=typer.Argument(..., help='Your question about the repo'), rebuild_index: bool=typer.Option(False, '--rebuild-index', help='Discard cached catalog and re-summarize every file.'), auto_confirm: bool=typer.Option(False, '--yes', '-y', help='Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run).')) -> None` — Ask a question about a repo and get an answer with file citations.

### `src/config.py`

**Purpose:** Centralizes all configurable parameters including model assignments, optimization thresholds, sandbox limits, database paths, and token pricing across the project.

**Public symbols:**
- `def price_for(model_id: str, kind: str) -> float` — USD per 1M tokens for ``model_id`` / ``kind`` (input | output | cached).

### `src/execution/__init__.py`

**Purpose:** Provides the public API for execution-related functionality in the package.

### `src/execution/sandbox.py`

**Purpose:** Executes untrusted Python code and pytest test suites in resource-limited subprocesses with CPU, memory, process count, and wall-clock timeout protections.

**Public symbols:**
- `async def run_python(code: str, test_code: str='', timeout_s: int=SANDBOX_TIMEOUT_S, mem_mb: int=SANDBOX_MEM_MB) -> ExecutionResult` — Run ``code`` (and any ``test_code``) inside a sandboxed subprocess.
- `async def run_pytest(repo_path: Path, test_target: str | None=None, timeout_s: int=SANDBOX_TIMEOUT_S * 6) -> ExecutionResult` — Run ``pytest`` inside ``repo_path``.

### `src/hitl/__init__.py`

**Purpose:** Provides the public API entry point for the HITL (Human-In-The-Loop) module by exposing key classes and functions.

### `src/hitl/gate.py`

**Purpose:** Provides interactive human confirmation gates in the pipeline where users can approve, edit, or abort agent outputs before proceeding.

**Public symbols:**
- `def show_and_confirm(gate: GateName, payload_display: str, *, console: Console | None=None, ask_fn: AskFn=_default_ask, edit_fn: EditFn=_default_edit) -> GateDecision` — Display ``payload_display`` and prompt the user for c/e/a.

### `src/metrics/__init__.py`

**Purpose:** Exports metrics module components and utilities for monitoring and measuring application performance.

### `src/pipeline/__init__.py`

**Purpose:** Initializes the pipeline package and exports its public API for data processing workflows.

### `src/schemas.py`

**Purpose:** Defines all Pydantic message schemas for inter-agent communication, providing typed contracts for code generation pipelines and repository-aware coding workflows.

**Public symbols:**
- `class Task(BaseModel)`
- `class CodeSolution(BaseModel)`
- `class ExecutionResult(BaseModel)`
- `class Evaluation(BaseModel)`
- `class VerificationVote(BaseModel)`
- `class VerificationPanel(BaseModel)`
- `class TaskComplexity(BaseModel)`
- `class TokenUsage(BaseModel)`
- `class PipelineRun(BaseModel)`
- `class Repo(BaseModel)`
- `class Request(BaseModel)`
- `class Intent(BaseModel)`
- `class CatalogSymbol(BaseModel)`
- `class CatalogFile(BaseModel)`
- `class Catalog(BaseModel)`
- `class LocatedFiles(BaseModel)`
- `class Answer(BaseModel)`
- `class FileEdit(BaseModel)`
- `class ChangePlan(BaseModel)`
- `class ChangeProposal(BaseModel)`
- `class GateDecision(BaseModel)`
- `class RepoRun(BaseModel)`

### `src/storage/__init__.py`

**Purpose:** Exposes the storage module's public API and classes for data persistence and retrieval.

### `tests/__init__.py`

**Purpose:** Marks the tests directory as a Python package to enable test discovery and imports.

### `tests/test_agents_router_locator.py`

**Purpose:** Provides hermetic unit tests for the Intent Router and Locator agents using PydanticAI's TestModel to verify intent classification and source file location without live API calls.

**Public symbols:**
- `async def test_router_returns_typed_intent()`
- `async def test_router_implement_kind()`
- `async def test_locator_returns_paths_from_catalog()`
- `async def test_locator_filters_hallucinated_paths()` — If the model returns a path that isn't in the catalog, it must be dropped.

### `tests/test_answerer.py`

**Purpose:** Verifies that the Answerer agent correctly generates typed answers to questions about codebase implementation details using test fixtures and mocked model outputs.

**Public symbols:**
- `async def test_answerer_returns_typed_answer()`

### `tests/test_catalog_unit.py`

**Purpose:** Provides hermetic unit tests for the catalog's deterministic components—file walking, symbol extraction, and markdown rendering—without requiring LLM integration.

**Public symbols:**
- `def test_iter_files_respects_gitignore_and_defaults(tmp_path: Path)`
- `def test_iter_files_max_files(tmp_path: Path)`
- `def test_hashing_is_stable(tmp_path: Path)`
- `def test_python_symbols_basic()`
- `def test_python_symbols_skips_invalid_source()`
- `def test_extract_symbols_unsupported_extension(tmp_path: Path)`
- `def test_render_catalog_md_smoke()`

### `tests/test_hitl_gate.py`

**Purpose:** Tests the HITL gate's prompt interaction logic by injecting mock input/output functions to verify confirm, abort, and edit decision flows.

**Public symbols:**
- `def test_gate_confirm()`
- `def test_gate_abort()`
- `def test_gate_edit_returns_payload()`
- `def test_gate_empty_edit_reprompts_then_confirms()` — Empty edits don't crash — the loop reprompts until a real choice.
- `def test_gate_unrecognised_choice_reprompts()`

### `tests/test_indexer.py`

**Purpose:** Verifies the indexer's incremental update mechanism by testing catalog generation, unchanged-file caching, selective re-summarization, and AST-based symbol extraction across git repository state chang

**Public symbols:**
- `async def test_first_index_builds_catalog_and_sidecar(tmp_path: Path)`
- `async def test_unchanged_repo_uses_zero_llm_calls(tmp_path: Path)` — The whole point: re-running the indexer on an unchanged repo must
- `async def test_modified_file_triggers_resummary(tmp_path: Path)`
- `async def test_refuses_non_git_directory(tmp_path: Path)`
- `async def test_new_file_added_picked_up(tmp_path: Path)`

### `tests/test_sandbox.py`

**Purpose:** Verifies the sandboxed Python executor's ability to run and classify code execution results, errors, and timeouts without external dependencies.

**Public symbols:**
- `async def test_happy_path()`
- `async def test_assertion_failure_classified()`
- `async def test_syntax_error_classified()`
- `async def test_runtime_error_classified()`
- `async def test_wall_clock_timeout()`
- `async def test_stdout_captured()`
- `async def test_run_pytest_against_self(tmp_path: Path)` — Smoke test for run_pytest: create a tiny inline test and run it.
- `async def test_run_pytest_failure_propagates(tmp_path: Path)`

### `tests/test_schemas.py`

**Purpose:** Validates serialization, deserialization, and constraint enforcement for inter-agent communication schemas used throughout the pipeline.

**Public symbols:**
- `def test_task_roundtrip()`
- `def test_evaluation_rejects_out_of_range()`
- `def test_verification_panel_roundtrip()`
- `def test_task_complexity_tier_constrained()`
- `def test_pipeline_run_full_roundtrip()`
- `def test_confidence_range()`

### `tests/test_schemas_v2.py`

**Purpose:** Validates serialization/deserialization and constraint enforcement for the v2 schema models used in repository-aware operations.

**Public symbols:**
- `def test_request_roundtrip()`
- `def test_catalog_roundtrip()`
- `def test_change_proposal_roundtrip()`
- `def test_gate_decision_action_constrained()`
- `def test_gate_decision_with_edit()`
- `def test_repo_run_minimum_fields()`
