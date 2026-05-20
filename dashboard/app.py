"""Streamlit dashboard for the multi-agent pipeline.

Reads ``runs.db`` (the SQLite store from Step 12) and renders three pages:

- Overview: headline counters + status × kind distribution
- Runs: filterable table of every CLI invocation; click a row to drill in
- Models: verifier-panel verdicts by model + agreement-score history

Launch with:
    uv run streamlit run dashboard/app.py
"""

from __future__ import annotations

# Streamlit needs imports first.
import sys
from pathlib import Path

# Allow `from src...` imports when running via `streamlit run dashboard/app.py`.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sqlmodel import select  # noqa: E402

from src.storage import db  # noqa: E402
from src.storage.models import GateRow, ReviewRow, RunRow  # noqa: E402


st.set_page_config(
    page_title="Multi-Agent Pipeline",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Data loading (cached so the dashboard is snappy on repeated rerenders)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10)
def load_runs() -> pd.DataFrame:
    with db.get_session() as session:
        rows = session.exec(select(RunRow)).all()
    return pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=10)
def load_gates() -> pd.DataFrame:
    with db.get_session() as session:
        rows = session.exec(select(GateRow)).all()
    return pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=10)
def load_reviews() -> pd.DataFrame:
    with db.get_session() as session:
        rows = session.exec(select(ReviewRow)).all()
    return pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame()


def _short_model(m: str) -> str:
    return m.split(":", 1)[-1] if isinstance(m, str) else m


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Multi-Agent Pipeline")
st.sidebar.caption("PydanticAI repo-aware coding assistant")
page = st.sidebar.radio("Page", ["Overview", "Runs", "Models"], label_visibility="collapsed")

if st.sidebar.button("↻ Refresh data"):
    st.cache_data.clear()
    st.rerun()

runs_df = load_runs()
gates_df = load_gates()
reviews_df = load_reviews()


# ---------------------------------------------------------------------------
# Page: Overview
# ---------------------------------------------------------------------------
if page == "Overview":
    st.title("Overview")

    if runs_df.empty:
        st.info(
            "No runs in the store yet. "
            "Try `uv run python -m src.cli ask <repo> \"<question>\"` first."
        )
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total runs", len(runs_df))
        success_rate = (runs_df["status"] == "success").mean() * 100
        c2.metric("Success rate", f"{success_rate:.0f}%")
        successful = runs_df[runs_df["status"] == "success"]
        if not successful.empty:
            c3.metric("Mean latency (success)", f"{int(successful['total_runtime_ms'].mean())} ms")
        else:
            c3.metric("Mean latency (success)", "-")
        impl_attempts = runs_df[runs_df["kind"] == "implement"]
        applied = impl_attempts["applied_commit"].notna() & (impl_attempts.get("test_passed") == True)
        if applied.any():
            c4.metric("Apply pass rate", f"{int(applied.mean() * 100)}%")
        else:
            c4.metric("Apply pass rate", "-")

        st.subheader("Runs by kind × status")
        pivot = (
            runs_df.groupby(["kind", "status"])
            .size()
            .reset_index(name="count")
            .pivot(index="status", columns="kind", values="count")
            .fillna(0)
            .astype(int)
        )
        st.dataframe(pivot, use_container_width=True)

        if not gates_df.empty:
            st.subheader("HITL gate actions")
            gate_pivot = (
                gates_df.groupby(["gate", "action"])
                .size()
                .reset_index(name="count")
                .pivot(index="gate", columns="action", values="count")
                .fillna(0)
                .astype(int)
            )
            # Order columns predictably.
            for col in ("confirm", "edit", "abort"):
                if col not in gate_pivot.columns:
                    gate_pivot[col] = 0
            st.dataframe(gate_pivot[["confirm", "edit", "abort"]], use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Runs (filterable list + drill-down)
# ---------------------------------------------------------------------------
elif page == "Runs":
    st.title("Runs")

    if runs_df.empty:
        st.info("No runs yet.")
    else:
        kinds = ["(all)"] + sorted(runs_df["kind"].unique().tolist())
        statuses = ["(all)"] + sorted(runs_df["status"].unique().tolist())
        col_k, col_s = st.columns(2)
        kind_filter = col_k.selectbox("Kind", kinds)
        status_filter = col_s.selectbox("Status", statuses)

        filtered = runs_df.copy()
        if kind_filter != "(all)":
            filtered = filtered[filtered["kind"] == kind_filter]
        if status_filter != "(all)":
            filtered = filtered[filtered["status"] == status_filter]

        display_cols = [
            "id",
            "kind",
            "status",
            "request",
            "started_at",
            "total_runtime_ms",
            "applied_commit",
        ]
        display_cols = [c for c in display_cols if c in filtered.columns]
        st.dataframe(
            filtered[display_cols].sort_values("id", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("Drill into a run")
        run_ids = sorted(filtered["id"].tolist(), reverse=True)
        if run_ids:
            run_id = st.selectbox("Run id", run_ids)
            row = filtered[filtered["id"] == run_id].iloc[0]

            st.markdown(f"### Run {run_id} — `{row['kind']}`")
            st.markdown(f"**Status:** `{row['status']}`")
            st.markdown(f"**Request:** {row['request']}")
            if pd.notna(row.get("intent_canonical")):
                st.markdown(f"**Canonical request:** {row['intent_canonical']}")
            if pd.notna(row.get("consensus_verdict")):
                st.markdown(
                    f"**Panel verdict:** `{row['consensus_verdict']}` "
                    f"(confidence {row.get('consensus_confidence', 0):.2f}, "
                    f"agreement {row.get('agreement_score', 0):.2f})"
                )
            if pd.notna(row.get("applied_commit")):
                st.markdown(
                    f"**Applied:** branch `{row.get('branch_name')}` @ "
                    f"`{row.get('applied_commit', '')[:12]}`"
                )

            run_gates = (
                gates_df[gates_df["run_id"] == run_id].sort_values("ordinal")
                if not gates_df.empty
                else pd.DataFrame()
            )
            if not run_gates.empty:
                st.markdown("#### Gate transcript")
                st.dataframe(
                    run_gates[["ordinal", "gate", "action", "edited_payload"]],
                    use_container_width=True,
                    hide_index=True,
                )

            run_reviews = (
                reviews_df[reviews_df["run_id"] == run_id]
                if not reviews_df.empty
                else pd.DataFrame()
            )
            if not run_reviews.empty:
                st.markdown("#### Verifier reviews")
                disp = run_reviews.copy()
                disp["model"] = disp["model_id"].map(_short_model)
                st.dataframe(
                    disp[["model", "verdict", "confidence", "reasoning"]],
                    use_container_width=True,
                    hide_index=True,
                )


# ---------------------------------------------------------------------------
# Page: Models
# ---------------------------------------------------------------------------
elif page == "Models":
    st.title("Verifier panel — model comparison")

    if reviews_df.empty:
        st.info("No verifier reviews yet. Run `implement` (without `--no-verify`) to populate.")
    else:
        st.subheader("Verdict distribution by model")
        disp = reviews_df.copy()
        disp["model"] = disp["model_id"].map(_short_model)
        crosstab = (
            pd.crosstab(disp["model"], disp["verdict"])
            .reindex(columns=["approve", "suggest", "reject"], fill_value=0)
        )
        st.dataframe(crosstab, use_container_width=True)
        st.bar_chart(crosstab)

        st.divider()
        if not runs_df.empty and "agreement_score" in runs_df.columns:
            verified = runs_df[runs_df["agreement_score"].notna()]
            if not verified.empty:
                st.subheader("Agreement score over time")
                chart_df = verified.set_index("started_at")[["agreement_score"]]
                st.line_chart(chart_df)

        st.subheader("Mean confidence by model + verdict")
        mean_conf = (
            disp.groupby(["model", "verdict"])["confidence"].mean().unstack(fill_value=0)
        )
        st.dataframe(mean_conf.round(2), use_container_width=True)
