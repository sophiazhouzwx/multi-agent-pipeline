# Multi-Agent Pipeline (Claude × GPT × Gemini) — Implementation Plan

> **Source**: Recovered from prior Claude Code session, saved 2026-05-19.
> **Project location**: `/Users/c270744/multi-agent-pipeline`
> **Status when saved**: Plan approved, Step 1 (scaffolding) about to begin.

---

## Context

Build a portfolio-grade multi-agent system at `/Users/c270744/multi-agent-pipeline` that demonstrates Machine Learning Engineering and AI Engineering skills. The system uses PydanticAI to orchestrate three Claude tiers (Opus 4.6 / Sonnet 4.6 / Haiku 4.5) via the existing CVS Health Anthropic proxy, with the architecture kept provider-agnostic so GPT-4o and Gemini can be dropped into any role later by changing one config line.

**Why all-Claude today**: Only `ANTHROPIC_API_KEY` (+ `ANTHROPIC_BASE_URL` proxy) is configured locally; no OpenAI or Gemini keys. Using three Claude tiers gives genuine capability differentiation (different sizes, different costs, different speeds) and still showcases every pattern in the plan. The cross-model panel becomes a cross-tier panel; we'll call this out honestly in the README and frame the multi-provider abstraction as the engineering win.

### Pipeline features

1. **Evaluator–optimizer loops** — Opus 4.6 generates, Sonnet 4.6 scores against a typed rubric, Opus regenerates with the critique injected; up to N iterations.
2. **Cross-tier verification** — Same problem fanned out to Opus / Sonnet / Haiku in parallel; a judge agent computes agreement and produces a consensus answer with confidence.
3. **Sandboxed code execution** — Generated Python is run in a subprocess with CPU/memory/wall-clock limits; results (stdout, stderr, exit, runtime) feed back into the optimizer loop for auto-fix.
4. **Adaptive model routing** — A lightweight classifier routes easy tasks to Haiku and hard tasks to Opus; cost vs. accuracy is measured against an always-Opus baseline.
5. **Benchmark harness + metrics** — Runs the pipeline against a curated coding benchmark, logs every step to SQLite, computes pass@k, cost-per-correct-answer, latency p50/p95, inter-tier agreement, and a failure taxonomy.
6. **Observability** — Pydantic Logfire traces the full agent graph; a Streamlit dashboard summarises benchmark runs.

The goal is not "another chatbot" — it is a pipeline with measurable outcomes that an interviewer can interrogate (architecture, async fan-out, typed I/O, eval rigor, cost trade-offs, sandbox safety).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Orchestrator  (pipeline/orchestrator.py)                            │
│  - Receives Task, calls Router → Generator → Sandbox → Evaluator     │
│  - Loops up to MAX_ITERATIONS until score ≥ threshold                │
│  - Fans out to Verifier panel; logs every step to SQLite             │
└─────┬────────────────┬──────────────────┬──────────────┬─────────────┘
      │                │                  │              │
┌─────▼─────┐  ┌───────▼────────┐  ┌──────▼───────┐  ┌──▼──────────────┐
│ Router    │  │ Generator      │  │ Evaluator    │  │ Verifier Panel  │
│ (Haiku)   │  │ (Opus 4.6)     │  │ (Sonnet 4.6) │  │ (Opus+Son+Haiku)│
│ → Tier    │  │ → CodeSolution │  │ → Evaluation │  │ → 3 Votes       │
└───────────┘  └────────┬───────┘  └──────────────┘  └─────────────────┘
                        │
                ┌───────▼────────────────┐
                │ Sandbox Executor       │
                │ subprocess + rlimits   │
                │ → ExecutionResult      │
                └────────────────────────┘
                        │
                ┌───────▼────────────────┐
                │ SQLite (sqlmodel)      │
                │ Run, Iteration, Vote   │
                └────────────────────────┘
```

All inter-agent messages are typed `pydantic.BaseModel` subclasses. The whole pipeline is async; `asyncio.gather` parallelises the three verifier calls.

---

## Tech Stack (locked)

| Layer | Choice | Rationale |
|---|---|---|
| Package manager | `uv` (already installed at `~/.local/bin/uv`) | Modern, fast, lockfile-first |
| Python | 3.11 (managed by `uv python install 3.11`) | System Python is 3.9, too old for PydanticAI |
| Agent framework | `pydantic-ai` (latest) | Typed I/O, multi-provider, async-native |
| Model clients | `anthropic`, `openai`, `google-genai` (pulled in transitively) | Official SDKs |
| Storage | `sqlmodel` + SQLite at `./runs.db` | Typed, no server needed |
| Sandboxing | `subprocess` + Python `resource` module (CPU/RSS/wall-clock limits) | No extra API key vs. E2B |
| Observability | `pydantic-logfire` (free tier, optional via env var) | Built into PydanticAI |
| CLI | `typer` + `rich` | Clean dev UX |
| Dashboard | `streamlit` reading `runs.db` | Cheap insight surface |
| Tests | `pytest` + `pytest-asyncio` | Standard |

### Model strings (PydanticAI `<provider>:<model>` format, sourced from `src/config.py`)

| Role | Today (single-provider) | Swap target later |
|---|---|---|
| Generator | `anthropic:claude-opus-4-6` | `openai:gpt-4o` or stay on Opus |
| Evaluator | `anthropic:claude-sonnet-4-6` | `openai:gpt-4o` (independent judge) |
| Verifier (panel) | Opus 4.6 + Sonnet 4.6 + Haiku 4.5 in parallel | swap any leg for GPT-4o / Gemini |
| Router/Judge | `anthropic:claude-haiku-4-5` | unchanged |

**Authentication**: all calls go through the existing `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` (CVS Health proxy). The PydanticAI `AnthropicModel` reads both env vars automatically — no extra wiring. Adaptive thinking is enabled on Opus 4.6 and Sonnet 4.6 via PydanticAI's `Thinking()` capability (auto-enables `thinking={"type": "adaptive"}` on the underlying SDK call); effort defaults to high on 4.6 and is left at the default.

`src/config.py` exposes every model ID as a constant so any role can be retargeted to a different provider with one line, plus a per-1M-token price table for cost reporting.

---

## Project Layout

```
/Users/c270744/multi-agent-pipeline/
├── pyproject.toml              # uv-managed, deps + tool config
├── .env.example                # ANTHROPIC_API_KEY (required), ANTHROPIC_BASE_URL (optional proxy), OPENAI_API_KEY / GEMINI_API_KEY (optional, for later swap)
├── .gitignore
├── README.md                   # How to run, what it shows
├── src/
│   ├── __init__.py
│   ├── config.py               # Model IDs, thresholds, paths
│   ├── schemas.py              # All Pydantic models (single source of truth)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── generator.py        # Opus 4.6 → CodeSolution
│   │   ├── evaluator.py        # Sonnet 4.6 → Evaluation
│   │   ├── verifier.py         # factory: model_id → Agent[VerificationVote]
│   │   └── router.py           # Haiku → TaskComplexity
│   ├── execution/
│   │   ├── __init__.py
│   │   └── sandbox.py          # run_python(code, timeout, mem_mb) → ExecutionResult
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Main async pipeline; ties everything together
│   │   ├── optimizer_loop.py   # generator ↔ evaluator with auto-fix
│   │   └── verifier_panel.py   # asyncio.gather over 3 models + judge
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLModel tables: Run, Iteration, Vote
│   │   └── db.py               # Engine + session helpers
│   ├── benchmarks/
│   │   ├── __init__.py
│   │   ├── problems.py         # 10 hand-picked HumanEval-style tasks (inline)
│   │   └── harness.py          # Runs all problems, writes metrics
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── report.py           # pass@k, cost/correct, latency p50/p95, agreement
│   └── cli.py                  # `typer` entrypoint: single, bench, report
├── tests/
│   ├── test_schemas.py
│   ├── test_sandbox.py         # Hermetic — no API calls
│   └── test_optimizer_loop.py  # Uses TestModel (PydanticAI fake)
└── dashboard/                  # Streamlit app reading runs.db
    └── app.py
```

---

## Pydantic Schemas (`src/schemas.py` — single source of truth)

```python
class Task(BaseModel):
    task_id: str
    prompt: str            # natural-language problem statement
    test_code: str         # pytest-style asserts that must pass
    difficulty: Literal["easy", "medium", "hard"] | None = None

class CodeSolution(BaseModel):
    code: str              # full Python module
    entry_point: str       # function name the test code calls
    explanation: str

class ExecutionResult(BaseModel):
    success: bool          # exit 0 AND all tests passed
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    timed_out: bool
    error_category: Literal["syntax", "runtime", "assertion", "timeout", "none"]

class Evaluation(BaseModel):
    correctness: int = Field(ge=0, le=10)
    efficiency: int = Field(ge=0, le=10)
    safety: int = Field(ge=0, le=10)
    overall: int = Field(ge=0, le=10)
    critique: str          # actionable feedback for the generator
    passes_threshold: bool

class VerificationVote(BaseModel):
    model_id: str
    answer: CodeSolution
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

class VerificationPanel(BaseModel):
    votes: list[VerificationVote]
    consensus: CodeSolution | None        # majority/judge pick
    agreement_score: float                # 0..1 (1 = all 3 agreed)

class TaskComplexity(BaseModel):
    tier: Literal["easy", "medium", "hard"]
    reasoning: str

class PipelineRun(BaseModel):         # top-level result returned by orchestrator
    task_id: str
    final_solution: CodeSolution
    iterations: int
    final_evaluation: Evaluation
    final_execution: ExecutionResult
    verification: VerificationPanel | None
    total_cost_usd: float
    total_latency_ms: int
    per_model_tokens: dict[str, dict[str, int]]   # {model: {input, output, cached}}
```

---

## Implementation Steps (in execution order)

Each step is small, testable, and produces a visible artifact. Steps 1–6 give a working single-task pipeline; 7–10 add cross-tier verification, storage, the benchmark, and metrics; 11 adds adaptive routing; 12 ships the dashboard.

### Step 1 — Project scaffolding
- `uv python install 3.11` (if not present), `uv init`, `uv add` all deps
- Create directory tree above, empty `__init__.py` files, `.gitignore`, `.env.example`, stub `README.md`
- Verify with `uv run python -c "import pydantic_ai; print(pydantic_ai.__version__)"`

### Step 2 — Schemas + config
- Write `src/schemas.py` with all models above
- Write `src/config.py` (model IDs, `MAX_ITERATIONS=3`, `SCORE_THRESHOLD=8`, `SANDBOX_TIMEOUT_S=10`, `SANDBOX_MEM_MB=256`)
- `pytest tests/test_schemas.py` — round-trip serialisation checks

### Step 3 — Sandboxed executor
- `src/execution/sandbox.py`: `async def run_python(code: str, test_code: str) -> ExecutionResult`
- Implementation: `tempfile` for the module, `asyncio.create_subprocess_exec` with `preexec_fn` setting `RLIMIT_CPU` + `RLIMIT_AS`, `asyncio.wait_for` for wall-clock timeout
- Classifies failures: `SyntaxError` text → `"syntax"`, non-zero exit → `"runtime"`, `AssertionError` → `"assertion"`, `TimeoutError` → `"timeout"`
- `tests/test_sandbox.py` covers: happy path, infinite loop (timeout), `import os; os.fork()`-style mischief (rejected via `RLIMIT_NPROC`), assertion failure

### Step 4 — Generator agent (Claude)
- `src/agents/generator.py`: PydanticAI `Agent(config.GENERATOR_MODEL, output_type=CodeSolution, instructions=...)`
- Instructions: "You are a Python coding agent. Given a task and optionally a previous attempt with critique, produce a complete, runnable solution that passes the provided tests."
- Exposes `async def generate(task: Task, prior: CodeSolution | None = None, critique: str | None = None) -> CodeSolution`

### Step 5 — Evaluator agent (Sonnet 4.6)
- `src/agents/evaluator.py`: `Agent(config.EVALUATOR_MODEL, output_type=Evaluation, instructions=...)`
- Instructions: "Score the candidate solution on correctness, efficiency, safety (0–10 each). Set `passes_threshold=true` only if `overall >= 8`. Provide one actionable critique paragraph."
- Exposes `async def evaluate(task: Task, solution: CodeSolution, execution: ExecutionResult) -> Evaluation`
- Sonnet 4.6 is a smaller, faster model than Opus 4.6, giving us independent judgment + cost savings on the evaluator path

### Step 6 — Optimizer loop + single-task CLI
- `src/pipeline/optimizer_loop.py`: `async def optimize(task: Task) -> tuple[CodeSolution, Evaluation, ExecutionResult, int]`
- Loop: generate → sandbox → evaluate → break if `passes_threshold`, else feed `Evaluation.critique` back to generator (up to `MAX_ITERATIONS`)
- `src/cli.py`: `typer` command `single` that takes a task description from stdin/flag and prints a rich-formatted result
- At this point we have a working evaluator-optimizer pipeline end-to-end

### Step 7 — Verifier panel (cross-tier)
- `src/agents/verifier.py`: factory `make_verifier(model_id: str)` so the panel can spin up one verifier per configured model
- `src/pipeline/verifier_panel.py`: `async def verify(task: Task) -> VerificationPanel` — runs Opus + Sonnet + Haiku verifiers in parallel via `asyncio.gather`
- Agreement: pairwise edit-distance on normalised AST dumps (`ast.dump` after `ast.parse`) → averaged into `agreement_score ∈ [0,1]`; falls back to text similarity if a vote isn't valid Python
- Haiku judge picks consensus from the three votes; result feeds into `PipelineRun`
- Architecture stays provider-agnostic: replacing one entry in `config.VERIFIER_MODELS` with `"openai:gpt-4o"` adds GPT to the panel with no other code change

### Step 8 — Storage
- `src/storage/models.py`: SQLModel tables `Run`, `Iteration`, `VerificationRecord` with FKs
- `src/storage/db.py`: `init_db()`, `get_session()`
- Orchestrator persists a `Run` row + N `Iteration` rows + verification record per task

### Step 9 — Benchmark harness
- `src/benchmarks/problems.py`: 10 inline tasks (mix of easy/medium/hard) — `two_sum`, `fizzbuzz`, `is_palindrome`, `reverse_linked_list`, `merge_intervals`, `lru_cache`, `regex_match`, `min_window_substring`, `n_queens`, `word_break`
- `src/benchmarks/harness.py`: `async def run_benchmark(k: int = 1) -> None` — runs each problem k times, writes to DB
- CLI: `bench --k 1`

### Step 10 — Metrics + report
- `src/metrics/report.py`: pass@k, cost-per-correct (using token usage from `result.usage()` + per-1M-token price table in config), latency p50/p95, inter-tier agreement rate, failure taxonomy
- CLI: `report` — pretty-prints a `rich.Table` summary

### Step 11 — Adaptive routing
- `src/agents/router.py`: Haiku classifies task complexity → routes to Haiku / Sonnet / Opus generators accordingly
- Generator factory selects model based on `TaskComplexity.tier`
- Metric: "cost saved vs. always-Opus baseline" tracked in `runs.db` so the report shows it

### Step 12 — Streamlit dashboard
- `dashboard/app.py`: Streamlit reading `runs.db`. Multi-page:
  - **Overview** — totals: runs, pass rate, total cost, p95 latency
  - **Per-problem** — table of every benchmark task with pass@k, average iterations, total cost
  - **Per-model** — accuracy and cost-per-correct by model role
  - **Agreement heatmap** — pairwise tier-vs-tier agreement on the verification panel
- Run via `uv run streamlit run dashboard/app.py`

---

## Critical Files to Reference

PydanticAI patterns gleaned from research (no existing codebase to mine):
- Agent definition: `Agent('<provider>:<model>', output_type=PydanticModel, instructions=...)` returns typed `result.output`
- Agent delegation: call `other_agent.run(prompt, usage=ctx.usage)` inside a `@tool` for token accounting
- Multi-provider model strings: `anthropic:`, `openai:`, `google-gla:` prefixes
- Async-first: `await agent.run(...)`; use `asyncio.gather` for fan-out

---

## Verification

After each step, run:
```bash
cd /Users/c270744/multi-agent-pipeline
uv run pytest tests/ -v        # unit tests (no API calls)
```

End-to-end smoke test after Step 6 (only needs the existing `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`):
```bash
uv run python -m src.cli single --task "Write a function `reverse_string(s: str) -> str`"
```

Full benchmark after Step 10:
```bash
uv run python -m src.cli bench --k 1
uv run python -m src.cli report
```

Dashboard after Step 12:
```bash
uv run streamlit run dashboard/app.py     # opens at http://localhost:8501
```

Expected artifacts after a full run:
- `runs.db` with one `Run` per problem, N `Iteration` rows each, three `VerificationRecord` rows each
- Console table showing per-tier accuracy, average iterations, total cost, p95 latency
- Streamlit dashboard with the four pages above

---

## Locked Decisions

- **Scope**: all 12 steps including the dashboard.
- **Models**: all-Claude tiers (Opus 4.6 generator, Sonnet 4.6 evaluator, Opus + Sonnet + Haiku verifier panel, Haiku router). Config-driven so any role can be retargeted to GPT-4o or Gemini by changing one constant.
- **Auth**: trust the existing CVS Anthropic proxy (`ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL`); no fallback code.
- **Sandbox**: subprocess + Python `resource` rlimits + `asyncio.wait_for` wall-clock timeout. No E2B, no Docker.
- **Tests**: PydanticAI `TestModel` for unit tests so they run offline; live API only in the smoke/benchmark commands.

---

## Resume Status (2026-05-19)

- Plan: APPROVED
- Step 1 status: NOT STARTED (previous session killed at `uv python install 3.11` permission prompt)
- Python 3.11.14 already installed via uv — can skip `uv python install`
- Project directory `/Users/c270744/multi-agent-pipeline` does NOT exist yet
- Next action: `uv init` the project and add dependencies
