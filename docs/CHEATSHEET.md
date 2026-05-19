# CHEATSHEET.md

Quick command reference for the multi-agent pipeline. Run all commands from `/Users/c270744/multi-agent-pipeline`.

---

## 1. First-time setup (once per machine)

```bash
# Sync deps (after a fresh clone)
uv sync

# Create .env with your Anthropic credentials.
# If you already have ANTHROPIC_API_KEY exported in your shell, the file below
# will copy it in. Otherwise, edit it by hand afterwards.
{
  echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-PASTE_YOUR_KEY_HERE}"
  echo "ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
} > .env && chmod 600 .env

# Sanity-check
uv run python -m src.cli --help
```

---

## 2. Q&A against a repo — `ask`

```bash
# Basic (interactive — pauses at HITL Gate #1 for intent confirmation)
uv run python -m src.cli ask <repo-path> "<your question>"

# Skip the gate (scripted / fast)
uv run python -m src.cli ask <repo-path> "<your question>" -y

# Force re-index (discards catalog cache, re-summarizes every file)
uv run python -m src.cli ask <repo-path> "<your question>" --rebuild-index -y
```

Examples against this project:

```bash
# Architecture question
uv run python -m src.cli ask /Users/c270744/multi-agent-pipeline \
  "how many agents are there in the pipeline?" -y

# Implementation detail
uv run python -m src.cli ask /Users/c270744/multi-agent-pipeline \
  "where is the sandbox memory limit enforced?" -y

# Locate-style question
uv run python -m src.cli ask /Users/c270744/multi-agent-pipeline \
  "which file defines the HITL gate?" -y
```

**HITL Gate #1 prompts:**
- `c` (or Enter) — confirm and continue
- `e` — supply a correction; Router re-runs with your edit appended
- `a` — abort the pipeline

---

## 3. Implementation requests — `implement` *(planning ready; apply lands at Step 10)*

```bash
# Plan a change (stops after Gate #2 today; full apply coming at Step 10)
uv run python -m src.cli implement <repo-path> "<your change request>"

# Auto-confirm both gates
uv run python -m src.cli implement <repo-path> "<your change request>" -y
```

Example:

```bash
uv run python -m src.cli implement /Users/c270744/multi-agent-pipeline \
  "add a --verbose flag to the ask command that prints the full Router and Locator outputs"
```

You'll see Gates #1 (intent) and #2 (plan). After Gate #2 it prints the approved plan and exits — code generation + git apply land in Steps 8-10.

---

## 4. Test suite (hermetic, no API calls)

```bash
# Run everything (~5 seconds)
uv run pytest tests/ -v

# Run a single file
uv run pytest tests/test_indexer.py -v

# Run a single test
uv run pytest tests/test_sandbox.py::test_wall_clock_timeout -v

# Quiet mode for CI
uv run pytest tests/ -q
```

All tests use PydanticAI's `TestModel` to stub LLM calls — they never hit the real API.

---

## 5. Inspect the catalog

```bash
# Human-readable catalog (markdown)
less /Users/c270744/multi-agent-pipeline/AGENT_CATALOG.md

# Typed source of truth (with content hashes)
jq . /Users/c270744/multi-agent-pipeline/.agent_catalog/catalog.json | less

# How many files are indexed?
jq '.files | length' /Users/c270744/multi-agent-pipeline/.agent_catalog/catalog.json

# Show one file's catalog entry
jq '.files[] | select(.path=="src/cli.py")' \
  /Users/c270744/multi-agent-pipeline/.agent_catalog/catalog.json
```

Catalogs work against any git repo — point the CLI at one and it writes its own `AGENT_CATALOG.md` + `.agent_catalog/` at that repo's root.

---

## 6. Git operations on this project

```bash
git status                       # what's changed
git log --oneline                # commit history
git diff <commit>~..<commit>     # diff a commit
```

The pipeline never writes to your repo without an explicit final HITL gate (Gate #3, coming at Step 10). Even then, apply happens on a working branch (`agent/<slug>`), and tests must pass before the branch keeps its commit.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `UserError: Set the ANTHROPIC_API_KEY environment variable` | Shell doesn't have the var, and no `.env` | Run the setup block in section 1 to create `.env` |
| `ModelHTTPError 404 ... Model 'claude-haiku-4-5' not found` | Proxy needs date-suffixed model ID | Already fixed in `src/config.py` — pull latest |
| `ModelHTTPError 429 ... RESOURCE_EXHAUSTED` | Upstream Vertex quota burst | Wait 30-60 s and retry; the request is idempotent |
| `ValueError: <path> is not a git repository` | Target dir has no `.git/` | `cd` into the target and run `git init && git add -A && git commit -m init` |
| `dquote>` prompt in zsh after running a command | You escaped the opening `"` with `\` | Press Ctrl+C; retype without the backslash |
| First indexing of a big repo is slow | Haiku call per file on first run | Wait it out — second run on the same content uses 0 LLM calls |
| Catalog seems stale | Files changed but cache hasn't refreshed | `--rebuild-index` flag forces a full re-summarization |

---

## 8. Cost reference (approximate, USD)

| Action | Calls | Typical cost |
|---|---|---|
| First-time index of a 30-file repo | 30 Haiku | ~$0.005 |
| Re-index after no changes | 0 | $0 |
| Re-index after 1 file changed | 1 Haiku | ~$0.0002 |
| Single `ask` (after catalog warm) | 1 Haiku + 1 Sonnet + 1 Opus | ~$0.02-0.10 |
| Single `implement` plan (after catalog warm) | 1 Haiku + 1 Sonnet + 1 Opus | ~$0.02-0.10 |

Cost scales with question/file size, not with repeat use of an unchanged catalog.

---

## 9. Model role assignments

| Role | Model | Why |
|---|---|---|
| Indexer summarizer | Haiku 4.5 | Cheapest; one-line purposes are easy |
| Intent Router | Haiku 4.5 | Cheap classification |
| Locator | Sonnet 4.6 | Needs more reasoning over the catalog |
| Answerer | Opus 4.6 | Best quality output for prose answers |
| Planner | Opus 4.6 | Best reasoning for change plans |
| Generator *(Step 8)* | Opus 4.6 | Code generation needs precision |
| Verifier panel *(Step 9)* | Opus + Sonnet + Haiku | Independent reviews |
| Judge *(Step 9)* | Haiku 4.5 | Cheap consensus pick |

All in `src/config.py`. Change one constant to retarget a role to GPT or Gemini once those keys are configured.

---

## 10. What's coming

| Step | Adds | Command exposed |
|---|---|---|
| 8 | Code Generator (Opus) | `implement` produces FileEdits |
| 9 | Cross-tier Verifier panel | `implement` runs review automatically |
| 10 | Git Applier + Gate #3 + rollback | `implement` actually writes files on a working branch |
| 11 | Catalog updater (incremental) | catalog refreshes after every apply |
| 12 | Storage (SQLite) | every run persisted to `runs.db` |
| 13 | Metrics + report | `report` subcommand for cost/agreement/latency |
| 14 | Adaptive model routing | Generator picks tier by request complexity |
| 15 | Streamlit dashboard | `uv run streamlit run dashboard/app.py` |
