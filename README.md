# Multi-Agent Pipeline

A PydanticAI multi-agent coding assistant that takes a **repo + a user request** and processes it through a typed agent chain with **human-in-the-loop confirmation** at every load-bearing decision. Repos are indexed once into a persistent `AGENT_CATALOG.md` so agents can search the right section instead of re-scanning every file on every invocation.

Three Claude tiers (Opus 4.6 / Sonnet 4.6 / Haiku 4.5) play different roles via PydanticAI. The architecture is provider-agnostic — any role can be retargeted to GPT-4o or Gemini by changing one constant in `src/config.py`.

See [`docs/PLAN.md`](docs/PLAN.md) for the full design (v1 archived at `docs/PLAN-v1-coding-benchmark.md`).

## Pipeline

```
repo + ask
    │
    ▼
[Catalog ensured]  →  [Intent Router]  ─ GATE#1 ─  [Locator]
                                                       │
                                          ┌────────────┴────────────┐
                                          │                         │
                                     question:                 implement:
                                     [Answerer]               [Planner] ─ GATE#2 ─ [Generator]
                                          │                                                │
                                          │                              [Verifier panel] ─┘
                                          │                                                │
                                          │                                         GATE#3
                                          │                                                │
                                          │                              [Applier (git branch + tests + commit/rollback)]
                                          │                                                │
                                          │                                       [Catalog updater]
                                          └─────────────────────┬──────────────────────────┘
                                                                ▼
                                                         runs.db (sqlite)
```

## Quick start

```bash
cp .env.example .env       # fill in ANTHROPIC_API_KEY (+ proxy URL if needed)
uv sync                    # install dependencies
uv run pytest tests/ -v    # unit tests (no API calls)
```

After Step 6 (Q&A path):

```bash
uv run python -m src.cli ask <repo-path> "where does the X logic live?"
```

After Step 10 (implement path with auto-apply on a working branch):

```bash
uv run python -m src.cli implement <repo-path> "add a --json flag to the parse command"
```

After Step 13 (report):

```bash
uv run python -m src.cli report
```

After Step 15 (dashboard):

```bash
uv run streamlit run dashboard/app.py
```

## Status

Currently at: **Step 6 complete — Q&A path end-to-end. `ask <repo> "<question>"` works against any git repo (42 tests passing, validated live against this project).**
