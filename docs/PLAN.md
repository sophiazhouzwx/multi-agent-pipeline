# Multi-Agent Pipeline v2 — Repo-Aware Coding Assistant

> **Pivot from v1** (see `PLAN-v1-coding-benchmark.md`): instead of a HumanEval-style
> coding-benchmark evaluator, the system is now a multi-agent coding assistant
> that takes a **real repo path** as input and processes a user question or
> implementation request through a chain of typed PydanticAI agents, with
> human-in-the-loop confirmation at every load-bearing decision.
>
> What carries over: PydanticAI orchestration, the three Claude tiers
> (Opus/Sonnet/Haiku), provider-agnostic config, sandboxed execution,
> evaluator/verifier patterns, SQLite storage, the dashboard.

> **v3 update (post-Step 15):** the `ask` and `implement` subcommands are
> unified under a single `mapipe ask` entrypoint that re-runs the Intent
> Router on **every turn** (initial input + each follow-up) and routes to
> Q&A or the full implement pipeline accordingly. The old `mapipe implement`
> command still works but prints a deprecation notice. The Generator stage
> auto-escalates Haiku → Sonnet → Opus when a lower tier produces invalid
> structured output (`ESCALATION_CHAIN` in `src/config.py`). The branching
> diagram below is still semantically correct — branching now happens
> per-turn rather than per-command-invocation.

---

## Why this design

Two problems with vanilla "let an LLM edit your repo":
1. The model re-scans the whole codebase on every invocation — expensive and slow.
2. The user has no insight into how the model interpreted the request until after files have been changed.

This pipeline addresses both:
- **Persistent `AGENT_CATALOG.md`** at the repo root: a standard-depth index (tree + per-file purpose + public symbols) that agents read instead of crawling the repo. Generated on first run, incrementally refreshed after every applied change.
- **3 HITL gates** at the points where misunderstandings compound: after intent classification, after the change plan, before files are written.

## Locked decisions

| Decision | Choice |
|---|---|
| Apply mode | Auto-apply after final HITL gate, on a working git branch + commit (safe rollback via `git reset`) |
| Catalog depth | Standard: file tree + per-file 1-line purpose + public symbols with one-line signatures |
| HITL gate density | 3 gates: intent confirmation, plan confirmation, final-apply confirmation. Each: confirm / edit / abort |
| Provider routing | All Claude today (Opus generator, Sonnet evaluator/locator, Haiku indexer/router/judge); config-driven to swap to GPT/Gemini later |
| Auth | Existing `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` proxy |
| Catalog update | Incremental — only re-summarize files touched by the apply step |
| Repo requirement | Target repo must be a git repo (`.git/` present); the pipeline refuses non-git roots |

---

## Pipeline flow

```
                        ┌─────────────────────────────────────┐
   user (repo, ask) ──▶ │   1. Catalog ensured (build/load)   │
                        │      AGENT_CATALOG.md @ repo root   │
                        └─────────────────┬───────────────────┘
                                          │
                        ┌─────────────────▼───────────────────┐
                        │   2. Intent Router (Haiku)          │
                        │      classify Q&A vs Implement,     │
                        │      extract canonical request      │
                        └─────────────────┬───────────────────┘
                                          │
                              ╔═══════════▼════════════╗
                              ║   HITL GATE #1: intent ║
                              ║   confirm / edit / abort
                              ╚═══════════╤════════════╝
                                          │
                        ┌─────────────────▼───────────────────┐
                        │   3. Locator (Sonnet)               │
                        │      catalog-search → relevant      │
                        │      sections + reads only those    │
                        │      files                          │
                        └─────────────────┬───────────────────┘
                                          │
                ┌─────────────────────────┴──────────────────────────┐
                │                                                    │
   if Q&A:      ▼                                       if implement:▼
   ┌─────────────────────┐                              ┌──────────────────────┐
   │ 4Q. Answerer (Opus) │                              │ 4I. Planner (Opus)   │
   │   write answer w/   │                              │   draft change plan: │
   │   citations         │                              │   files, what change │
   └──────────┬──────────┘                              └──────────┬───────────┘
              │                                                    │
              │                                       ╔════════════▼════════════╗
              │                                       ║  HITL GATE #2: plan      ║
              │                                       ║  confirm / edit / abort
              │                                       ╚════════════╤════════════╝
              │                                                    │
              │                                       ┌────────────▼────────────┐
              │                                       │ 5. Generator (Opus)     │
              │                                       │   produce FileEdits     │
              │                                       └────────────┬────────────┘
              │                                                    │
              │                                       ┌────────────▼────────────┐
              │                                       │ 6. Verifier panel       │
              │                                       │   Opus+Sonnet+Haiku in  │
              │                                       │   parallel; judge picks │
              │                                       │   consensus or abort    │
              │                                       └────────────┬────────────┘
              │                                                    │
              │                                       ╔════════════▼════════════╗
              │                                       ║ HITL GATE #3: apply      ║
              │                                       ║ confirm / edit / abort
              │                                       ╚════════════╤════════════╝
              │                                                    │
              │                                       ┌────────────▼────────────┐
              │                                       │ 7. Applier              │
              │                                       │   git branch + write +  │
              │                                       │   run repo tests in     │
              │                                       │   sandbox + commit OR   │
              │                                       │   rollback              │
              │                                       └────────────┬────────────┘
              │                                                    │
              │                                       ┌────────────▼────────────┐
              │                                       │ 8. Catalog updater      │
              │                                       │   re-summarize touched  │
              │                                       │   files; rewrite        │
              │                                       │   affected sections     │
              │                                       └────────────┬────────────┘
              │                                                    │
              └──────────────────────┬─────────────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  persist RepoRun    │
                          │  to runs.db         │
                          └─────────────────────┘
```

---

## AGENT_CATALOG.md format (standard depth)

The catalog is plain markdown so it's human-readable too:

```markdown
# AGENT_CATALOG.md
> generated 2026-05-19 by multi-agent-pipeline v0.1.0
> repo: /path/to/repo @ commit abcd123
> use: agents read this instead of crawling the repo. one anchor per file.

## Tree
- src/
  - cli.py
  - parser/
    - lexer.py
    - ast.py
  - storage/
    - db.py

## Files

### src/cli.py
**Purpose:** typer CLI entrypoint; wires subcommands `parse`, `compile`.
**Public symbols:**
- `main() -> None` — typer app runner
- `parse_cmd(path: Path) -> None` — parse a source file
- `compile_cmd(path: Path, out: Path) -> None` — compile to bytecode

### src/parser/lexer.py
**Purpose:** tokenizes source into a stream of Token objects.
**Public symbols:**
- `class Lexer` — stateful tokenizer
- `class Token(BaseModel)` — token record
- `tokenize(src: str) -> list[Token]` — convenience wrapper
```

Stored at `<repo>/AGENT_CATALOG.md`. A `<repo>/.agent_catalog/` sidecar directory holds metadata: per-file content hashes (`hashes.json`) so the incremental updater knows what to re-summarize.

**LLM call profile** (clarifies that summarization is one-shot per repo, not per pipeline invocation):

| When | Cost |
|---|---|
| First-ever index of a repo (N files) | N Claude Haiku 4.5 calls |
| Subsequent pipeline runs on an unchanged repo | 0 LLM calls — catalog loaded verbatim from `AGENT_CATALOG.md` |
| After a successful apply touching k files | k Haiku calls (typically 1–5) |
| User edits a file outside the pipeline | 1 Haiku call per such file on the next index pass |

The indexer always computes a SHA-256 of the current file contents and compares against `.agent_catalog/hashes.json`. Identical hash → skip the LLM call entirely, reuse the existing purpose line. Public symbol extraction is deterministic via stdlib `ast` and is always free.

---

## Tech additions on top of v1

| Need | Choice |
|---|---|
| Walk a repo, respect `.gitignore` | `pathspec` (already in many transitive deps; add explicitly if missing) |
| Parse Python public symbols | stdlib `ast` |
| Git operations (branch, commit, reset) | `gitpython` |
| Diff display at gates | `difflib` (stdlib) + `rich` for color |
| Optional language detection | extension-based, no extra dep |

Everything else from v1 stays.

---

## Schemas to add (in `src/schemas.py`, beside the existing models)

```python
RequestKind = Literal["question", "implement"]

class Repo(BaseModel):
    path: Path
    git_commit: str            # HEAD at time of run
    branch: str                # currently checked-out branch

class Request(BaseModel):
    repo: Repo
    user_message: str
    kind: RequestKind | None = None   # filled by Intent Router

class Intent(BaseModel):
    kind: RequestKind
    canonical_request: str             # paraphrased ask the agent will act on
    rationale: str

class CatalogSymbol(BaseModel):
    name: str
    signature: str
    summary: str

class CatalogFile(BaseModel):
    path: str                          # repo-relative
    purpose: str
    public_symbols: list[CatalogSymbol]
    content_hash: str                  # for incremental updates

class Catalog(BaseModel):
    repo_path: Path
    git_commit: str
    files: list[CatalogFile]

class FileEdit(BaseModel):
    path: str                          # repo-relative
    new_content: str                   # full file content after edit
    rationale: str

class ChangePlan(BaseModel):
    summary: str
    affected_files: list[str]
    steps: list[str]                   # ordered narrative

class ChangeProposal(BaseModel):
    plan: ChangePlan
    edits: list[FileEdit]

class GateDecision(BaseModel):
    gate: Literal["intent", "plan", "apply"]
    action: Literal["confirm", "edit", "abort"]
    edited_payload: str | None = None  # the user's edit text if action=="edit"

class RepoRun(BaseModel):
    request: Request
    intent: Intent
    plan: ChangePlan | None = None
    proposal: ChangeProposal | None = None
    verification: VerificationPanel | None = None
    applied_commit: str | None = None  # commit sha created by Applier
    test_result: ExecutionResult | None = None
    gates: list[GateDecision] = []
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
```

The existing `CodeSolution`, `Evaluation`, `VerificationVote/Panel`, `TaskComplexity`, `ExecutionResult`, `TokenUsage`, `PipelineRun` stay — `VerificationPanel` is reused by Step 6; `ExecutionResult` is reused by the Applier's sandbox test run.

---

## Implementation steps

Each step is small + testable. **Pause point: Step 6** — that's when you have a working `ask <repo> "<question>"` command end-to-end.

| # | Step | Notes |
|---|---|---|
| 1 | ✅ Scaffolding | done |
| 2 | ✅ Existing schemas + config | done; new schemas added in Step 3 |
| 3 | **Repo-aware schemas** + sandbox executor | Append new models to `src/schemas.py`; build `src/execution/sandbox.py` (now also runs `pytest` inside a repo) |
| 4 | **Repo Indexer + AGENT_CATALOG.md** | `src/catalog/indexer.py`: walk repo (respect `.gitignore`), summarize each file via Haiku (cheap), write `AGENT_CATALOG.md`. Hash sidecar for incremental updates. |
| 5 | **Intent Router (Gate #1) + Locator** | `src/agents/router.py` (classify Q&A vs Implement), `src/agents/locator.py` (catalog → relevant files). HITL gate UX via `rich.prompt.Prompt`. |
| 6 | **Q&A path + CLI `ask`** ← *pause here* | `src/agents/answerer.py` (Opus, cites catalog sections), `src/cli.py` with `ask <repo> "<question>"`. End-to-end demo against a real repo. |
| 7 | **Planner (Gate #2)** | `src/agents/planner.py` → `ChangePlan`. CLI `implement` subcommand starts working. |
| 8 | **Generator** | `src/agents/generator.py` reworked to produce `FileEdit[]` rather than a single module. |
| 9 | **Verifier panel** | reuses v1 design: Opus + Sonnet + Haiku in parallel, judge picks consensus. |
| 10 | **Applier (Gate #3) + rollback** | `src/apply/applier.py`: `git checkout -b agent/<slug>`, write files, `pytest` in sandbox, `git commit` on success or `git reset --hard` on failure. |
| 11 | **Catalog updater** | `src/catalog/updater.py`: diff hashes, re-summarize touched files, rewrite affected sections of `AGENT_CATALOG.md`. |
| 12 | **Storage layer** | SQLModel tables: `RepoRunRow`, `GateRow`, `CatalogSnapshotRow`. |
| 13 | **Metrics + report** | per-run cost, p50/p95 latency, gate accept/edit/abort rates, model agreement rate. CLI `report`. |
| 14 | **Adaptive routing** | Haiku-classified complexity routes generator to Haiku/Sonnet/Opus. Cost-vs-always-Opus baseline tracked. |
| 15 | **Streamlit dashboard** | runs list, per-run gate transcript, catalog viewer, model comparison. |

---

## Verification at the pause point (after Step 6)

```bash
# Q&A path against this very project (eats its own dogfood):
uv run python -m src.cli ask /Users/c270744/multi-agent-pipeline \
  "where does the sandbox enforce its memory limit?"

# Expected:
# - First run: builds AGENT_CATALOG.md in the target repo
# - Subsequent runs: reads catalog directly
# - Output: an answer that names src/execution/sandbox.py and the relevant symbol,
#   based on catalog hits + a targeted file read (not a full repo scan)
# - Gate #1 fires once for intent confirmation
```

---

## What this demonstrates to an interviewer

- **AI Engineering**: PydanticAI agent graph, typed I/O, async fan-out, multi-tier model routing, evaluator/verifier patterns, persistent context engineering (the catalog), HITL design.
- **MLE**: instrumented metrics (cost, latency, agreement, gate-action distributions), sandboxed eval against real tests, cost-vs-quality trade-offs measured against a baseline.
- **Production craft**: typed schemas end-to-end, git-aware safety, rollback on test failure, provider-agnostic config, async-native, observable.
