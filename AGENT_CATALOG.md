# AGENT_CATALOG.md

> generated 2026-05-24T19:38:32+00:00 by multi-agent-pipeline
> repo: `/Users/c270744/multi-agent-pipeline` @ `350931e6`
> Agents read this instead of crawling the repo. One anchor per file; only re-summarized when content changes.

_60 files indexed._

## Tree

```
README.md
dashboard/
  app.py
docs/
  CHEATSHEET.md
  PLAN-v1-coding-benchmark.md
  PLAN.md
pyproject.toml
src/
  __init__.py
  _retry.py
  agents/
    __init__.py
    answerer.py
    complexity_router.py
    generator.py
    judge.py
    locator.py
    planner.py
    router.py
    verifier.py
  apply/
    __init__.py
    applier.py
  benchmarks/
    __init__.py
  catalog/
    __init__.py
    catalog_md.py
    indexer.py
    summarizer.py
    symbols.py
    updater.py
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
    report.py
  pipeline/
    __init__.py
    verifier_panel.py
  schemas.py
  storage/
    __init__.py
    db.py
    models.py
    persist.py
tests/
  __init__.py
  test_agents_router_locator.py
  test_answerer.py
  test_applier.py
  test_catalog_unit.py
  test_complexity_router.py
  test_generator.py
  test_hitl_gate.py
  test_indexer.py
  test_metrics.py
  test_planner.py
  test_retry.py
  test_sandbox.py
  test_schemas.py
  test_schemas_v2.py
  test_storage.py
  test_updater.py
  test_verifier_panel.py
```

## Files

### `README.md`

**Purpose:** Comprehensive documentation for a multi-agent coding assistant that routes repository requests through intent-based pipelines with human confirmation gates and tier-escalating LLM generation.

### `dashboard/app.py`

**Purpose:** Provides a Streamlit web dashboard for visualizing pipeline run metrics, detailed run logs, and model verifier performance from the SQLite database.

**Public symbols:**
- `def load_runs() -> pd.DataFrame`
- `def load_gates() -> pd.DataFrame`
- `def load_reviews() -> pd.DataFrame`

### `docs/CHEATSHEET.md`

**Purpose:** Quick-reference guide for command-line usage, setup, and workflow of the multi-agent pipeline system.

### `docs/PLAN-v1-coding-benchmark.md`

**Purpose:** Outlines the complete implementation plan for a multi-agent coding benchmark pipeline using PydanticAI to orchestrate three Claude tiers with evaluator loops, sandboxed execution, adaptive routing, an

### `docs/PLAN.md`

**Purpose:** Strategic project plan documenting the multi-agent repo-aware coding assistant pipeline architecture, design decisions, and implementation roadmap with HITL gates and component responsibilities.

### `pyproject.toml`

**Purpose:** Defines project metadata, dependencies, and development requirements for the multi-agent pipeline application.

### `src/__init__.py`

**Purpose:** Marks the src directory as a Python package and serves as the entry point for package initialization.

### `src/_retry.py`

**Purpose:** Provides exponential backoff retry logic for transient LLM API failures (rate limits and 5xx errors) with user-visible wait notifications.

**Public symbols:**
- `async def run_with_retry(fn: Callable[[], Awaitable[T]], *, label: str='', max_attempts: int=DEFAULT_MAX_ATTEMPTS, base_delay_s: float=DEFAULT_BASE_DELAY_S) -> T` — Call ``fn`` with exponential backoff on retryable HTTP errors.

### `src/agents/__init__.py`

**Purpose:** Exports public agent classes and utilities for easy import access across the agents module.

### `src/agents/answerer.py`

**Purpose:** Generates natural-language answers to code repository questions using an LLM agent, citing specific file locations and paths referenced in the response.

**Public symbols:**
- `async def answer_question(intent: Intent, catalog: Catalog, located: LocatedFiles, file_contents: dict[str, str], *, prior_turns: list[tuple[str, str]] | None=None) -> Answer` — Produce a typed Answer for the user's question.

### `src/agents/complexity_router.py`

**Purpose:** Classifies implementation task complexity (easy/medium/hard) to select the appropriate cost-efficient LLM tier for code generation.

**Public symbols:**
- `async def classify_complexity(intent: Intent) -> TaskComplexity` — Return the complexity tier for an implementation intent.

### `src/agents/generator.py`

**Purpose:** Generates complete file contents for each file in an approved change plan by invoking an LLM agent with the plan details and existing file contents.

**Public symbols:**
- `async def generate_changes(intent: Intent, plan: ChangePlan, file_contents: dict[str, str], *, model_id: str | None=None) -> ChangeProposal` — Produce a typed ChangeProposal from an approved plan.

### `src/agents/judge.py`

**Purpose:** Synthesizes multiple independent code review verdicts into a single consensus decision by reasoning about reviewer confidence levels and conflict resolution.

**Public symbols:**
- `async def judge(reviews: list[ProposalReview], request: str) -> JudgeDecision` — Decide the consensus across N independent reviews.

### `src/agents/locator.py`

**Purpose:** Identifies 1-5 most relevant files from a code catalog based on a user's intent using Claude Sonnet with hallucination filtering.

**Public symbols:**
- `async def locate(catalog: Catalog, intent: Intent) -> LocatedFiles` — Return the 1-5 files most relevant to ``intent``.

### `src/agents/planner.py`

**Purpose:** Produces a high-level, ordered ChangePlan describing what files will be modified before code generation, serving as the human review checkpoint.

**Public symbols:**
- `async def plan_change(intent: Intent, located: LocatedFiles, file_contents: dict[str, str]) -> ChangePlan` — Produce a typed ChangePlan from the user's request + located files.

### `src/agents/router.py`

**Purpose:** Classifies user messages as questions or implementation requests and rewrites them in canonical form for downstream processing.

**Public symbols:**
- `async def classify_intent(user_message: str) -> Intent` — Return the model's typed Intent for a free-form user message.

### `src/agents/verifier.py`

**Purpose:** Constructs independent verifier agents that review proposed code changes and return typed verdicts with confidence scores and reasoning.

**Public symbols:**
- `def make_verifier(model_id: str) -> Agent` — Construct a fresh verifier Agent for the given model string.

### `src/apply/__init__.py`

**Purpose:** Provides the public API for the apply module by exposing its main functions and classes.

### `src/apply/applier.py`

**Purpose:** Applies file changes to a git repository on a temporary branch, runs tests in a sandbox, and automatically rolls back if tests fail or commits if they pass.

**Public symbols:**
- `def make_branch_slug(request: str, max_len: int=40) -> str` — Generate a branch name like ``agent/add-json-flag-20260519-160355``.
- `async def apply_changes(repo_path: Path, proposal: ChangeProposal, request_summary: str, test_fn: TestFn=run_pytest) -> ApplyResult` — Apply ``proposal`` on a new branch, run tests, commit or rollback.

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

**Purpose:** Generates single-sentence purpose summaries for source files using Claude AI with bounded concurrency for efficient batch processing.

**Public symbols:**
- `def make_summarizer_agent() -> Agent` — Construct a fresh summarizer agent. Tests can use ``agent.override``.
- `async def summarize_file(path_rel: str, source: str) -> str` — Return a 1-line purpose for a single file.
- `async def summarize_batch(items: list[tuple[str, str]], concurrency: int=5) -> list[str]` — Summarize many files with bounded concurrency. Preserves input order.

### `src/catalog/symbols.py`

**Purpose:** Extracts public symbols (functions, classes, constants) from source files with deterministic signatures and docstrings for catalog indexing.

**Public symbols:**
- `def extract_python_symbols(source: str) -> list[CatalogSymbol]` — Return public top-level functions/classes/constants from a Python source.
- `def extract_symbols(path: Path, source: str) -> list[CatalogSymbol]` — Dispatch by extension. Returns [] for unsupported languages.

### `src/catalog/updater.py`

**Purpose:** Re-indexes a repository after file modifications to refresh the catalog with only changed files, returning typed statistics for persistence.

**Public symbols:**
- `class CatalogRefreshResult(BaseModel)`
- `async def refresh_catalog_after_apply(repo_path: Path) -> CatalogRefreshResult` — Refresh the catalog after files have been written.

### `src/catalog/walker.py`

**Purpose:** Walks a repository to discover indexable files while respecting `.gitignore` and exclusion rules, and provides hashing utilities for content deduplication.

**Public symbols:**
- `def iter_files(repo_path: Path, max_files: int | None=None) -> Iterator[Path]` — Yield absolute paths of indexable files under ``repo_path``.
- `def sha256_of(path: Path) -> str` — SHA-256 hex digest of a file's bytes.
- `def sha256_of_text(text: str) -> str`

### `src/cli.py`

**Purpose:** Provides the Typer CLI entrypoint and interactive command handlers for the multi-agent pipeline, including the `ask` subcommand for Q&A against repositories with human-in-the-loop gates and rich termi

**Public symbols:**
- `def ask(repo: Path=typer.Argument(..., exists=True, file_okay=False, help='Target git repo'), question: str=typer.Argument(..., help='A question OR a change request — the router decides per turn'), rebuild_index: bool=typer.Option(False, '--rebuild-index', help='Discard cached catalog and re-summarize every file.'), auto_confirm: bool=typer.Option(False, '--yes', '-y', help='Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run).'), show_edits: bool=typer.Option(False, '--show-edits', help='On implement turns: print full proposed file contents (verbose).'), no_verify: bool=typer.Option(False, '--no-verify', help='On implement turns: skip the cross-tier verifier panel (saves 4 LLM calls).'), no_route: bool=typer.Option(False, '--no-route', help='On implement turns: force Opus 4.6 for the generator (skip the complexity router).')) -> None` — Unified Q&A + implement entrypoint.
- `def implement(repo: Path=typer.Argument(..., exists=True, file_okay=False, help='Target git repo'), request: str=typer.Argument(..., help='The change you want made'), rebuild_index: bool=typer.Option(False, '--rebuild-index', help='Discard cached catalog and re-summarize every file.'), auto_confirm: bool=typer.Option(False, '--yes', '-y', help='Skip HITL gates (sets GATE_AUTO_CONFIRM=1 for this run).'), show_edits: bool=typer.Option(False, '--show-edits', help='Print full proposed file contents (verbose).'), no_verify: bool=typer.Option(False, '--no-verify', help='Skip the cross-tier verifier panel (saves 4 LLM calls).'), no_route: bool=typer.Option(False, '--no-route', help='Force Opus 4.6 for the generator (skip the complexity router).')) -> None` — [DEPRECATED] Plan, generate, verify, and apply a change to a repo.
- `def report() -> None` — Print a summary of past runs from runs.db.

### `src/config.py`

**Purpose:** Defines all configurable parameters including model assignments, optimization thresholds, sandbox settings, and token pricing for the application.

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

### `src/metrics/report.py`

**Purpose:** Provides aggregated metrics and statistics from the runs database for CLI reporting, including run counts, latency percentiles, gate actions, reviewer verdicts, and apply outcomes.

**Public symbols:**
- `def total_runs(session: Session) -> int`
- `def runs_by_kind_status(session: Session) -> dict[tuple[str, str], int]` — Counts keyed by (kind, status) — e.g. ('implement', 'success') -> 7.
- `def latency_stats(session: Session, status_filter: str | None='success') -> dict[str, int]` — Latency percentiles in ms, optionally filtered by status.
- `def gate_action_counts(session: Session) -> dict[tuple[str, str], int]` — Counts keyed by (gate, action). e.g. ('intent', 'confirm') -> 11.
- `def reviewer_verdict_counts(session: Session) -> dict[tuple[str, str], int]` — Counts keyed by (model_id, verdict).
- `def panel_agreement_stats(session: Session) -> dict[str, float]` — Mean agreement_score across all runs that completed verification.
- `def apply_outcome_stats(session: Session) -> dict[str, int]` — Apply attempts: total, applied, rolled_back, with pass rate as percent.
- `def compute_report() -> dict[str, object]` — One DB read; returns every metric in a single dict for the CLI.
- `def known_kinds(by_kind_status: Iterable[tuple[str, str]]) -> list[str]` — Return the distinct request kinds present in the data.
- `def known_statuses(by_kind_status: Iterable[tuple[str, str]]) -> list[str]` — Return the distinct statuses present in the data.

### `src/pipeline/__init__.py`

**Purpose:** Initializes the pipeline package and exports its public API for data processing workflows.

### `src/pipeline/verifier_panel.py`

**Purpose:** Orchestrates parallel verification of code change proposals by running multiple verifier agents, collecting their reviews, and obtaining a judge's consensus verdict.

**Public symbols:**
- `def agreement_score(reviews: list[ProposalReview]) -> float` — Pairwise verdict agreement: 1.0 = all match, 0.0 = all disagree.
- `async def verify_proposal(intent: Intent, proposal: ChangeProposal, original_contents: dict[str, str]) -> PanelVerdict` — Run the panel: parallel reviewers + judge -> typed PanelVerdict.

### `src/schemas.py`

**Purpose:** Defines all Pydantic message schemas used for inter-agent communication in the pipeline, covering both coding-task and repository-aware workflows.

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
- `class ProposalReview(BaseModel)` — One verifier's independent review of a ChangeProposal.
- `class JudgeDecision(BaseModel)` — Judge agent's consensus call across multiple ProposalReview objects.
- `class PanelVerdict(BaseModel)` — Full output of the verifier panel: reviews + judged consensus.
- `class GateDecision(BaseModel)`
- `class ApplyResult(BaseModel)` — Outcome of the Applier: branch created, tests run, commit OR rollback.
- `class RepoRun(BaseModel)`

### `src/storage/__init__.py`

**Purpose:** Exposes the storage module's public API and classes for data persistence and retrieval.

### `src/storage/db.py`

**Purpose:** Provides lazy initialization and management of a SQLite database engine and session factory with test utilities for swapping to isolated databases.

**Public symbols:**
- `def get_engine() -> Engine` — Return the cached engine, building it from ``config.DB_URL`` if needed.
- `def init_db() -> None` — Create tables if they don't exist (idempotent).
- `def use_engine_for_url(url: str) -> None` — Replace the cached engine with a fresh one for ``url``. For tests.
- `def reset_engine() -> None` — Dispose and clear the cached engine. For test teardown.
- `def get_session() -> Iterator[Session]` — Yield a session, auto-initialising tables on first use.

### `src/storage/models.py`

**Purpose:** Defines SQLModel database tables for persisting pipeline runs, HITL gate decisions, and verifier panel reviews to a SQLite database.

**Public symbols:**
- `class RunRow(SQLModel, table=True)` — One row per CLI invocation (ask or implement).
- `class GateRow(SQLModel, table=True)` — One row per HITL gate decision.
- `class ReviewRow(SQLModel, table=True)` — One row per verifier panel review.

### `src/storage/persist.py`

**Purpose:** Persists completed CLI runs and their associated gates/reviews to the SQLite database, ensuring every execution (success, error, or abort) is permanently recorded.

**Public symbols:**
- `def save_run(*, repo_path: Path, kind: str, request: str, status: str, started_at: datetime, ended_at: datetime | None=None, intent: Intent | None=None, verification: PanelVerdict | None=None, apply_result: ApplyResult | None=None, gates: list[GateDecision] | None=None) -> int` — Persist a finished run + its child rows. Returns the new run id.

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

**Purpose:** Tests that the Answerer agent correctly formats prompts with conversation history and returns structured answers with cited sources.

**Public symbols:**
- `async def test_answerer_passes_prior_turns_into_prompt()` — When prior_turns is supplied, the prompt must include the previous
- `async def test_answerer_returns_typed_answer()`

### `tests/test_applier.py`

**Purpose:** Validates the git-aware applier module through hermetic tests using real git repositories and injected fake test runners to verify change application, rollback, and branch management behavior.

**Public symbols:**
- `def test_slug_alphanumeric_only(monkeypatch)`
- `def test_slug_empty_request()`
- `def test_slug_max_len_respected()`
- `def test_write_edits_creates_parent_dirs(tmp_path: Path)`
- `async def test_apply_happy_path(tmp_path: Path)`
- `async def test_apply_treats_no_tests_as_pass(tmp_path: Path)` — pytest exit code 5 means no tests collected — treat as pass.
- `async def test_apply_rolls_back_on_test_failure(tmp_path: Path)`
- `async def test_apply_refuses_dirty_repo(tmp_path: Path)`
- `async def test_apply_refuses_non_git_dir(tmp_path: Path)`
- `def test_test_pass_codes()`

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

### `tests/test_complexity_router.py`

**Purpose:** Validates that the complexity router correctly classifies request tiers and that code generation properly dispatches to tier-specific or fallback agents.

**Public symbols:**
- `async def test_complexity_router_returns_typed_tier()`
- `async def test_generator_uses_tier_specific_agent()` — Passing model_id=<tier model> should route the call to that tier's
- `async def test_generator_falls_back_to_default_on_unknown_model()` — If the caller passes a model_id we don't have a cached agent for,

### `tests/test_generator.py`

**Purpose:** Tests the Generator agent's ability to produce typed code change proposals and filter edits to match the planned file scope.

**Public symbols:**
- `async def test_generator_returns_typed_proposal()`
- `async def test_generator_filters_out_of_plan_edits()` — Edits for paths not in plan.affected_files must be dropped.
- `async def test_generator_handles_new_file_paths()` — A path in the plan that's NOT in file_contents is a new file the

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

### `tests/test_metrics.py`

**Purpose:** Verifies the metrics report module's functions for computing aggregate statistics from stored runs, including percentile calculations, run counts by kind/status, gate actions, reviewer verdicts, apply

**Public symbols:**
- `def tmp_db(tmp_path: Path)`
- `def test_percentile_empty()`
- `def test_percentile_basic()`
- `def test_report_empty_db(tmp_db)`
- `def test_runs_by_kind_status(tmp_db)`
- `def test_gate_action_counts(tmp_db)`
- `def test_reviewer_verdict_counts(tmp_db)`
- `def test_apply_outcome_stats(tmp_db)`
- `def test_panel_agreement_only_counts_runs_with_verification(tmp_db)`
- `def test_latency_filters_to_success(tmp_db)`

### `tests/test_planner.py`

**Purpose:** Tests that the Planner agent correctly generates typed change plans from intents and file contexts, including handling of impossible requests.

**Public symbols:**
- `async def test_planner_returns_typed_change_plan()`
- `async def test_planner_can_signal_impossible_request()` — If the model can't make sense of the request, summary explains it and

### `tests/test_retry.py`

**Purpose:** Validates the retry-with-backoff mechanism, ensuring it succeeds on first attempt, retries transient errors (429, 5xx), fails fast on client errors (4xx except 429), and respects max attempt limits.

**Public symbols:**
- `async def test_succeeds_first_try()`
- `async def test_retries_429_then_succeeds()`
- `async def test_retries_then_gives_up_and_raises()`
- `async def test_does_not_retry_400_class_errors()` — 4xx errors other than 429 should fail fast — they're our bugs, not transient.
- `async def test_retries_5xx_errors()`
- `def test_retryable_statuses_membership()`

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

### `tests/test_storage.py`

**Purpose:** Provides hermetic unit tests for the SQLite storage layer, verifying persistence of runs, gates, reviews, apply results, and intents using isolated temporary databases.

**Public symbols:**
- `def tmp_db(tmp_path: Path)`
- `def test_save_minimal_ask_run(tmp_db)`
- `def test_save_run_with_gate_decisions(tmp_db)`
- `def test_save_run_with_verification(tmp_db)`
- `def test_save_run_records_apply_result(tmp_db)`
- `def test_save_run_records_rollback(tmp_db)`
- `def test_save_run_records_intent(tmp_db)`

### `tests/test_updater.py`

**Purpose:** Verifies that the catalog updater correctly re-summarizes only changed files and uses cached results for unchanged files.

**Public symbols:**
- `async def test_refresh_resummarizes_only_changed_files(tmp_path: Path)`
- `async def test_refresh_unchanged_repo_uses_no_llm(tmp_path: Path)` — A refresh on an unchanged repo must not call the summarizer.

### `tests/test_verifier_panel.py`

**Purpose:** Provides hermetic end-to-end tests for the verifier panel by stubbing all verifier and judge models to validate proposal review workflows without external API calls.

**Public symbols:**
- `def test_agreement_score_all_agree()`
- `def test_agreement_score_all_disagree()`
- `def test_agreement_score_partial()`
- `async def test_panel_unanimous_approve()`
- `async def test_panel_stamps_model_ids()` — Each verifier sees the same prompt but the panel must attribute the
- `async def test_panel_records_judge_reasoning()`
