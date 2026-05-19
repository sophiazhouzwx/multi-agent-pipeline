"""Central configuration: model IDs, thresholds, paths, pricing.

Every model role is a config string so swapping any Claude tier for GPT-4o
or Gemini is a one-line change. PydanticAI model strings use the format
``"<provider>:<model-id>"``; providers we support today: ``anthropic``,
``openai``, ``google-gla``.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Model assignments by role.
# ---------------------------------------------------------------------------
# Today: all Claude tiers via the existing ANTHROPIC_API_KEY (+ optional
# ANTHROPIC_BASE_URL proxy). Tomorrow: change one string to swap providers.
GENERATOR_MODEL = "anthropic:claude-opus-4-6"
EVALUATOR_MODEL = "anthropic:claude-sonnet-4-6"
ROUTER_MODEL = "anthropic:claude-haiku-4-5"
JUDGE_MODEL = "anthropic:claude-haiku-4-5"

# Verifier panel: parallel fan-out across these models.
VERIFIER_MODELS: tuple[str, ...] = (
    "anthropic:claude-opus-4-6",
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
)

# Adaptive routing: complexity-tier -> generator model.
ROUTER_TIER_TO_MODEL: dict[str, str] = {
    "easy": "anthropic:claude-haiku-4-5",
    "medium": "anthropic:claude-sonnet-4-6",
    "hard": "anthropic:claude-opus-4-6",
}

# ---------------------------------------------------------------------------
# Optimizer loop + sandbox.
# ---------------------------------------------------------------------------
MAX_ITERATIONS = 3
SCORE_THRESHOLD = 8  # Evaluation.overall must hit this to pass.

SANDBOX_TIMEOUT_S = 10
SANDBOX_MEM_MB = 256
SANDBOX_MAX_PROCS = 1  # forbids subprocess/fork from the executed code

# ---------------------------------------------------------------------------
# Paths.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "runs.db"
DB_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Pricing (USD per 1M tokens) for cost reporting. Update as needed.
# Cached input is priced separately on Anthropic; we track it for accuracy.
# ---------------------------------------------------------------------------
PRICE_PER_MTOK: dict[str, dict[str, float]] = {
    "anthropic:claude-opus-4-6": {"input": 15.00, "output": 75.00, "cached": 1.50},
    "anthropic:claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cached": 0.30},
    "anthropic:claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cached": 0.10},
    "openai:gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "google-gla:gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached": 0.025},
}


def price_for(model_id: str, kind: str) -> float:
    """USD per 1M tokens for ``model_id`` / ``kind`` (input | output | cached).

    Returns 0.0 if the model isn't priced yet — keeps reports robust when
    new models are dropped in before pricing is added.
    """
    return PRICE_PER_MTOK.get(model_id, {}).get(kind, 0.0)
