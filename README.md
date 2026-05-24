# Multi-Agent Pipeline

A PydanticAI multi-agent coding assistant that takes a **repo + a user request** and processes it through a typed agent chain with **human-in-the-loop confirmation** at every load-bearing decision. Repos are indexed once into a persistent `AGENT_CATALOG.md` so agents can search the right section instead of re-scanning every file on every invocation.

Three Claude tiers (Opus 4.6 / Sonnet 4.6 / Haiku 4.5) play different roles via PydanticAI. The architecture is provider-agnostic — any role can be retargeted to GPT-4o or Gemini by changing one constant in `src/config.py`.

`mapipe ask` is the single unified entrypoint: the Intent Router classifies **each turn** as a question or a change request and routes accordingly, so you can switch from asking to implementing in the same conversation without starting a new session.

See [`docs/PLAN.md`](docs/PLAN.md) for the full design (v1 archived at `docs/PLAN-v1-coding-benchmark.md`).

## Pipeline

```
repo + message
      │
      ▼
[Catalog ensured]  →  [Intent Router]  ─ GATE#1 ─  per-turn branch
                                                       │
                                          ┌────────────┴────────────┐
                                          │                         │
                                     question:                 implement:
                                     [Locator]                 [Locator]
                                          │                         │
                                     [Answerer]                [Planner] ─ GATE#2 ─ [Generator (tier-escalating)]
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
                                              follow-up loop OR runs.db (sqlite)
```

Per-turn routing means the same `mapipe ask` invocation can answer a question on turn 1, plan and apply a code change on turn 2, etc. The Generator stage auto-escalates Haiku → Sonnet → Opus when a lower tier produces invalid structured output, so cheap-tier failures don't crash the run.

## Quick start

```bash
cp .env.example .env       # fill in ANTHROPIC_API_KEY (+ proxy URL if needed)
uv sync                    # install dependencies
uv run pytest tests/ -v    # unit tests (no API calls)
```

Unified entrypoint — works for both questions and change requests:

```bash
# Q&A
uv run python -m src.cli ask <repo-path> "where does the X logic live?"

# Same command for code changes — the router auto-routes to plan→generate→verify→apply
uv run python -m src.cli ask <repo-path> "add a --json flag to the parse command"
```

Inside the follow-up loop you can mix freely — ask a question, then describe a change, and the next turn switches into the full implement pipeline automatically.

Report and dashboard:

```bash
uv run python -m src.cli report                # CLI metrics summary
uv run streamlit run dashboard/app.py          # interactive dashboard
```

> **Deprecated:** `mapipe implement <repo> "<request>"` still works but prints a deprecation notice — use `mapipe ask` instead.

## Status

Currently at: **All 15 planned steps complete**, plus a v3 unification pass that collapses `ask`/`implement` into a single auto-routing entrypoint and adds a generator tier-escalation safety net. 82 tests passing.

See [`docs/CHEATSHEET.md`](docs/CHEATSHEET.md) for all commands.
