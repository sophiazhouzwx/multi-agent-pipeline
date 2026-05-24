"""Render the multi-agent-pipeline workflow as a PNG.

Layout: vertical branching tree. Entry section at top (catalog + intent +
gate #1), then two parallel columns under it — question path (left) and
implement path (right) — with a shared persistence section at the bottom.
Pastel boxes, diamond HITL gates, italic model-tier tags. Matches the
horizontal-lane / ribbon style of the user's reference architecture diagram
while keeping arrows short and orthogonal.

Usage:
    python docs/generate_pipeline_diagram.py [output.png]

Default output: docs/pipeline_workflow.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


# ---------- palette ----------------------------------------------------------
COL = {
    "entry":     {"fill": "#DCE6FF", "edge": "#3D5A99"},
    "question":  {"fill": "#D4EEDD", "edge": "#2E7D5B"},
    "implement": {"fill": "#FFE4C2", "edge": "#B86E1F"},
    "gate":      {"fill": "#FFE082", "edge": "#7A5B00"},
    "persist":   {"fill": "#E3E3E3", "edge": "#404040"},
}
TEXT_DARK = "#1B1B1B"
TEXT_MUTE = "#5C5C5C"
ARROW     = "#37474F"
BG_LANE   = "#FAFAFA"
BG_BORDER = "#D0D0D0"

# ---------- geometry ---------------------------------------------------------
# Coordinate system is 24 wide x 32 tall. Each "row" of boxes sits at a fixed
# y; arrows always go straight down (no diagonals). Both columns share an x
# offset so vertical alignment is consistent.

BOX_W = 5.6
BOX_H = 1.5
GATE_W = 1.8
GATE_H = 1.8
COL_Q_X = 5.5     # centre x of question column
COL_I_X = 18.5    # centre x of implement column
TRUNK_X = 12.0    # centre x of entry trunk (above the split)


# ---------- primitives -------------------------------------------------------
def lane(ax, x, y, w, h, label, color, *, ribbon=0.22, label_y_offset=-0.30):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=BG_LANE,
                           edgecolor=BG_BORDER, lw=0.8, zorder=0))
    ax.add_patch(Rectangle((x, y), ribbon, h, facecolor=color,
                           edgecolor=color, zorder=1))
    ax.text(x + ribbon + 0.25, y + h + label_y_offset, label,
            fontsize=11, fontweight="bold", color=color, zorder=2)


def box(ax, cx, cy, label, *, fill, edge, model=None, sub=None,
        w=BOX_W, h=BOX_H, fontsize=11):
    x, y = cx - w / 2, cy - h / 2
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.22",
        facecolor=fill, edgecolor=edge, linewidth=1.8,
    ))
    # vertical text stack: model (italic, small) on top, label centre, sub bottom
    label_y = cy + (0.10 if model else 0.0) + (0.0 if sub else -0.05)
    if model:
        ax.text(cx, cy + 0.45, model, ha="center", va="center",
                fontsize=8.5, style="italic", color=TEXT_MUTE)
    ax.text(cx, label_y, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold", color=TEXT_DARK)
    if sub:
        ax.text(cx, cy - 0.40, sub, ha="center", va="center",
                fontsize=8.5, color=TEXT_MUTE)


def gate(ax, cx, cy, label, sub="confirm / edit / abort", w=GATE_W, h=GATE_H):
    ax.add_patch(Polygon(
        [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
        closed=True, facecolor=COL["gate"]["fill"],
        edgecolor=COL["gate"]["edge"], linewidth=1.8,
    ))
    ax.text(cx, cy + 0.18, label, ha="center", va="center",
            fontsize=10, fontweight="bold", color=TEXT_DARK)
    ax.text(cx, cy - 0.22, sub, ha="center", va="center",
            fontsize=7.5, style="italic", color=TEXT_MUTE)


def arrow(ax, x1, y1, x2, y2, *, color=ARROW, lw=1.7, dashed=False,
          label=None, label_xy=None):
    a = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=14, linewidth=lw,
        color=color, linestyle="--" if dashed else "-",
        joinstyle="miter",
    )
    ax.add_patch(a)
    if label:
        lx, ly = label_xy if label_xy else ((x1 + x2) / 2 + 0.15, (y1 + y2) / 2)
        ax.text(lx, ly, label, fontsize=8.5, color=TEXT_MUTE, va="center")


def vdown(ax, cx, y_from, y_to, **kw):
    """Short vertical arrow between two box edges in the same column."""
    arrow(ax, cx, y_from, cx, y_to, **kw)


# ---------- diagram ----------------------------------------------------------
def main(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(15, 19), dpi=160)
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 32)
    ax.set_aspect("equal")
    ax.axis("off")

    # Title block
    ax.text(12, 31.3, "Multi-Agent Pipeline — Process Workflow",
            ha="center", va="center", fontsize=20, fontweight="bold",
            color=TEXT_DARK)
    ax.text(12, 30.6,
            "Unified `mapipe ask` entrypoint  ·  per-turn intent routing  ·  HITL gates  ·  tier-escalating generator",
            ha="center", va="center", fontsize=10.5, style="italic",
            color=TEXT_MUTE)

    # ====================== ENTRY LANE ======================================
    lane(ax, 0.7, 23.5, 22.6, 6.4, "ENTRY  ·  every turn (initial + each follow-up)",
         COL["entry"]["edge"])

    # 1. user message
    box(ax, TRUNK_X, 28.8, "repo + user message",
        fill=COL["entry"]["fill"], edge=COL["entry"]["edge"],
        sub="initial CLI call OR follow-up prompt", h=1.4)
    # 2. catalog
    vdown(ax, TRUNK_X, 28.10, 27.45)
    box(ax, TRUNK_X, 26.75, "Stage 1: Catalog",
        fill=COL["entry"]["fill"], edge=COL["entry"]["edge"],
        sub="AGENT_CATALOG.md  ·  incremental re-summarise", h=1.4)
    # 3. intent router
    vdown(ax, TRUNK_X, 26.05, 25.40)
    box(ax, TRUNK_X, 24.70, "Stage 2: Intent Router",
        fill=COL["entry"]["fill"], edge=COL["entry"]["edge"],
        model="Haiku 4.5",
        sub="Intent { kind: question | implement, canonical_request, rationale }",
        h=1.4)
    # 4. Gate #1 (sits to the right of intent router so the split below stays clean)
    arrow(ax, TRUNK_X + 2.8, 24.70, TRUNK_X + 5.0, 24.70)
    gate(ax, TRUNK_X + 5.7, 24.70, "Gate #1", "intent confirm")

    # Branch hint
    ax.text(12, 22.65, "switch on  intent.kind", ha="center", va="center",
            fontsize=10.5, fontweight="bold", color=TEXT_DARK,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFFFFF",
                      edgecolor=BG_BORDER, lw=1.0))

    # Trunk down to split point
    vdown(ax, TRUNK_X, 23.95, 23.10)
    # Horizontal split: trunk → each column
    arrow(ax, TRUNK_X, 22.30, COL_Q_X + 0.05, 21.70,
          label="question", label_xy=(7.5, 22.2))
    arrow(ax, TRUNK_X, 22.30, COL_I_X - 0.05, 21.70,
          label="implement", label_xy=(15.0, 22.2))

    # ====================== QUESTION COLUMN =================================
    lane(ax, 0.7, 12.5, 10.5, 8.6, "QUESTION PATH  ·  Q&A with citations",
         COL["question"]["edge"], label_y_offset=0.25)

    box(ax, COL_Q_X, 20.30, "Stage 3: Locator",
        fill=COL["question"]["fill"], edge=COL["question"]["edge"],
        model="Sonnet 4.6",
        sub="catalog → relevant files (+ prior turns)", h=1.4)
    vdown(ax, COL_Q_X, 19.60, 18.95)
    box(ax, COL_Q_X, 18.25, "Stage 4: Answerer",
        fill=COL["question"]["fill"], edge=COL["question"]["edge"],
        model="Opus 4.6",
        sub="answer + cited_files", h=1.4)
    vdown(ax, COL_Q_X, 17.55, 16.90)
    box(ax, COL_Q_X, 16.20, "Render answer",
        fill=COL["question"]["fill"], edge=COL["question"]["edge"],
        sub="rich Panel + citations", h=1.4)
    vdown(ax, COL_Q_X, 15.50, 14.85)
    box(ax, COL_Q_X, 14.15, "Save run  (kind='ask')",
        fill=COL["question"]["fill"], edge=COL["question"]["edge"],
        sub="→ runs.db", h=1.4)
    vdown(ax, COL_Q_X, 13.45, 12.95)
    box(ax, COL_Q_X, 13.20, "next follow-up turn",
        fill="#FFFFFF", edge=COL["question"]["edge"],
        sub="re-classified by Intent Router",
        h=0.95, fontsize=9.5)

    # Loop-back arrow: question column → top of Entry (next turn)
    arrow(ax, COL_Q_X - 2.8, 13.20, 1.6, 13.20, dashed=True, color=TEXT_MUTE)
    arrow(ax, 1.6, 13.20, 1.6, 28.80, dashed=True, color=TEXT_MUTE)
    arrow(ax, 1.6, 28.80, TRUNK_X - 2.8, 28.80, dashed=True, color=TEXT_MUTE,
          label="loop: next turn", label_xy=(4.5, 29.10))

    # ====================== IMPLEMENT COLUMN ================================
    lane(ax, 12.5, 4.1, 10.8, 17.0,
         "IMPLEMENT PATH  ·  plan → generate → verify → apply",
         COL["implement"]["edge"], label_y_offset=0.25)

    box(ax, COL_I_X, 20.30, "Stage 3: Locator",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        model="Sonnet 4.6",
        sub="catalog → relevant files", h=1.4)
    vdown(ax, COL_I_X, 19.60, 18.95)
    box(ax, COL_I_X, 18.25, "Stage 4: Planner",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        model="Opus 4.6",
        sub="ChangePlan { summary, affected_files, steps }", h=1.4)
    vdown(ax, COL_I_X, 17.55, 16.90)
    gate(ax, COL_I_X, 16.15, "Gate #2", "plan confirm", w=1.7, h=1.6)
    vdown(ax, COL_I_X, 15.30, 14.65)
    box(ax, COL_I_X, 13.95, "Stage 5a: Complexity Router",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        model="Haiku 4.5",
        sub="easy / medium / hard  →  tier", h=1.4)
    vdown(ax, COL_I_X, 13.25, 12.60)
    box(ax, COL_I_X, 11.90, "Stage 5: Generator",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        model="tier-escalating",
        sub="Haiku → Sonnet → Opus  on  UnexpectedModelBehavior", h=1.4)
    vdown(ax, COL_I_X, 11.20, 10.55)
    box(ax, COL_I_X, 9.85, "Stage 6: Verifier panel",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        model="Opus + Sonnet + Haiku (parallel)  +  Haiku judge",
        sub="approve | reject | suggest", h=1.4)
    vdown(ax, COL_I_X, 9.15, 8.50)
    gate(ax, COL_I_X, 7.75, "Gate #3", "apply confirm", w=1.7, h=1.6)
    vdown(ax, COL_I_X, 6.90, 6.25)
    box(ax, COL_I_X, 5.55, "Stage 7: Applier",
        fill=COL["implement"]["fill"], edge=COL["implement"]["edge"],
        sub="branch + write + pytest in sandbox  →  commit OR rollback", h=1.4)
    vdown(ax, COL_I_X, 4.85, 4.20)

    # Annotation: verifier-reject early exit (dashed out to the right)
    arrow(ax, COL_I_X + 2.85, 9.85, COL_I_X + 4.40, 9.85,
          dashed=True, color=COL["gate"]["edge"])
    ax.text(COL_I_X + 4.50, 9.85, "reject  →  abort",
            fontsize=9, style="italic", color=COL["gate"]["edge"],
            va="center")
    # Annotation: gate #2 / #3 abort path
    arrow(ax, COL_I_X + 0.85, 16.15, COL_I_X + 4.40, 16.15,
          dashed=True, color=COL["gate"]["edge"])
    ax.text(COL_I_X + 4.50, 16.15, "abort  →  end turn",
            fontsize=9, style="italic", color=COL["gate"]["edge"],
            va="center")

    # ====================== PERSISTENCE LANE ================================
    lane(ax, 0.7, 0.8, 22.6, 2.6,
         "PERSISTENCE  ·  every run", COL["persist"]["edge"])

    box(ax, 6.5, 2.10, "runs.db  (SQLite)",
        fill=COL["persist"]["fill"], edge=COL["persist"]["edge"],
        sub="RunRow + GateRows + ReviewRows", h=1.3)
    box(ax, 13.5, 2.10, "Stage 8: Catalog updater",
        fill=COL["persist"]["fill"], edge=COL["persist"]["edge"],
        model="Haiku 4.5",
        sub="re-summarise changed files  →  AGENT_CATALOG.md", h=1.3)
    box(ax, 20.0, 2.10, "agent/<slug>  branch",
        fill=COL["persist"]["fill"], edge=COL["persist"]["edge"],
        sub="merge or discard manually", w=5.4, h=1.3)

    # Persistence inputs
    arrow(ax, COL_Q_X, 12.50, COL_Q_X, 3.40, dashed=True, color=TEXT_MUTE)
    arrow(ax, COL_Q_X, 3.40, 6.5, 2.80, dashed=True, color=TEXT_MUTE,
          label="save ask run", label_xy=(3.4, 4.0))
    arrow(ax, COL_I_X, 4.05, COL_I_X, 3.40, color=TEXT_MUTE)
    arrow(ax, COL_I_X, 3.40, 13.5, 2.80, color=TEXT_MUTE,
          label="save implement run + refresh catalog",
          label_xy=(11.0, 3.55))

    # ====================== LEGEND ==========================================
    ly = 0.10
    swatch_y = ly + 0.12

    def swatch_box(x, c, label):
        ax.add_patch(FancyBboxPatch(
            (x, swatch_y - 0.10), 0.55, 0.42,
            boxstyle="round,pad=0.03,rounding_size=0.10",
            facecolor=COL[c]["fill"], edgecolor=COL[c]["edge"], lw=1.2,
        ))
        ax.text(x + 0.75, swatch_y + 0.11, label,
                fontsize=8.5, va="center", color=TEXT_DARK)

    swatch_box(0.7, "entry", "ENTRY")
    swatch_box(3.2, "question", "QUESTION")
    swatch_box(6.0, "implement", "IMPLEMENT")
    swatch_box(9.2, "persist", "PERSISTENCE")

    # Gate swatch
    gx = 12.5
    ax.add_patch(Polygon(
        [(gx + 0.28, swatch_y + 0.35), (gx + 0.55, swatch_y + 0.11),
         (gx + 0.28, swatch_y - 0.13), (gx + 0.01, swatch_y + 0.11)],
        closed=True, facecolor=COL["gate"]["fill"],
        edgecolor=COL["gate"]["edge"], lw=1.2,
    ))
    ax.text(gx + 0.75, swatch_y + 0.11, "HITL gate",
            fontsize=8.5, va="center", color=TEXT_DARK)

    # Arrow legends
    ax.annotate("", xy=(15.6, swatch_y + 0.12), xytext=(14.7, swatch_y + 0.12),
                arrowprops=dict(arrowstyle="-|>", color=ARROW, lw=1.5))
    ax.text(15.75, swatch_y + 0.12, "control flow", fontsize=8.5, va="center",
            color=TEXT_DARK)
    ax.annotate("", xy=(19.4, swatch_y + 0.12), xytext=(18.5, swatch_y + 0.12),
                arrowprops=dict(arrowstyle="-|>", color=TEXT_MUTE,
                                lw=1.5, ls="--"))
    ax.text(19.55, swatch_y + 0.12, "loop-back / abort",
            fontsize=8.5, va="center", color=TEXT_DARK)

    fig.savefig(out, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / "pipeline_workflow.png"
    main(out)
