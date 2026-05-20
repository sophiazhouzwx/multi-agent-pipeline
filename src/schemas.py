"""Single source of truth for all inter-agent message types.

Every Pydantic model the pipeline passes between agents lives here so the
typed contracts are easy to audit in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared literals.
# ---------------------------------------------------------------------------
Difficulty = Literal["easy", "medium", "hard"]
ErrorCategory = Literal["syntax", "runtime", "assertion", "timeout", "none"]
RequestKind = Literal["question", "implement"]
GateName = Literal["intent", "plan", "apply"]
GateAction = Literal["confirm", "edit", "abort"]
Verdict = Literal["approve", "reject", "suggest"]


# ---------------------------------------------------------------------------
# v1 schemas (kept as the contracts for evaluator/verifier/sandbox roles).
# ---------------------------------------------------------------------------
class Task(BaseModel):
    task_id: str
    prompt: str
    test_code: str
    difficulty: Difficulty | None = None


class CodeSolution(BaseModel):
    code: str
    entry_point: str
    explanation: str


class ExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    timed_out: bool
    error_category: ErrorCategory


class Evaluation(BaseModel):
    correctness: int = Field(ge=0, le=10)
    efficiency: int = Field(ge=0, le=10)
    safety: int = Field(ge=0, le=10)
    overall: int = Field(ge=0, le=10)
    critique: str
    passes_threshold: bool


class VerificationVote(BaseModel):
    model_id: str
    answer: CodeSolution
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class VerificationPanel(BaseModel):
    votes: list[VerificationVote]
    consensus: CodeSolution | None
    agreement_score: float = Field(ge=0.0, le=1.0)


class TaskComplexity(BaseModel):
    tier: Difficulty
    reasoning: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


class PipelineRun(BaseModel):
    task_id: str
    final_solution: CodeSolution
    iterations: int
    final_evaluation: Evaluation
    final_execution: ExecutionResult
    verification: VerificationPanel | None = None
    total_cost_usd: float
    total_latency_ms: int
    per_model_tokens: dict[str, TokenUsage] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# v2 schemas: repo-aware coding-assistant flow.
# ---------------------------------------------------------------------------
class Repo(BaseModel):
    path: Path
    git_commit: str
    branch: str


class Request(BaseModel):
    repo: Repo
    user_message: str
    kind: RequestKind | None = None


class Intent(BaseModel):
    kind: RequestKind
    canonical_request: str
    rationale: str


class CatalogSymbol(BaseModel):
    name: str
    signature: str
    summary: str = ""


class CatalogFile(BaseModel):
    path: str
    purpose: str
    public_symbols: list[CatalogSymbol] = Field(default_factory=list)
    content_hash: str


class Catalog(BaseModel):
    repo_path: Path
    git_commit: str
    files: list[CatalogFile] = Field(default_factory=list)


class LocatedFiles(BaseModel):
    paths: list[str]
    reasoning: str


class Answer(BaseModel):
    body: str
    cited_files: list[str] = Field(default_factory=list)


class FileEdit(BaseModel):
    path: str
    new_content: str
    rationale: str


class ChangePlan(BaseModel):
    summary: str
    affected_files: list[str]
    steps: list[str]


class ChangeProposal(BaseModel):
    plan: ChangePlan
    edits: list[FileEdit]


class ProposalReview(BaseModel):
    """One verifier's independent review of a ChangeProposal."""

    model_id: str = ""  # filled by the panel after the call returns
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    suggestions: list[str] = Field(default_factory=list)


class JudgeDecision(BaseModel):
    """Judge agent's consensus call across multiple ProposalReview objects."""

    consensus_verdict: Verdict
    consensus_confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PanelVerdict(BaseModel):
    """Full output of the verifier panel: reviews + judged consensus."""

    reviews: list[ProposalReview]
    consensus_verdict: Verdict
    consensus_confidence: float = Field(ge=0.0, le=1.0)
    agreement_score: float = Field(ge=0.0, le=1.0)
    judge_reasoning: str


class GateDecision(BaseModel):
    gate: GateName
    action: GateAction
    edited_payload: str | None = None


class ApplyResult(BaseModel):
    """Outcome of the Applier: branch created, tests run, commit OR rollback."""

    branch_name: str
    applied_commit: str | None = None  # commit sha on success; None if rolled back
    test_result: ExecutionResult | None = None
    rolled_back: bool = False
    rollback_reason: str = ""


class RepoRun(BaseModel):
    request: Request
    intent: Intent
    plan: ChangePlan | None = None
    proposal: ChangeProposal | None = None
    verification: PanelVerdict | None = None
    applied_commit: str | None = None
    test_result: ExecutionResult | None = None
    gates: list[GateDecision] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
