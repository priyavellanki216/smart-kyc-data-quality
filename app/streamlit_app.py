from __future__ import annotations

import os
import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from kyc_quality.database import (
    DEFAULT_DB_PATH,
    audit_for_entity,
    read_table,
    record_review_action,
    review_duplicate_candidate,
    review_queue,
    set_exception_status,
)
from kyc_quality.config import load_rules
from kyc_quality.reporting import build_report_frames, export_reports, summary_metrics
from kyc_quality.service import run_demo_pipeline

st.set_page_config(page_title="Smart KYC | Data Quality Review", page_icon="◇", layout="wide")

DB_PATH = Path(os.getenv("KYC_DB_PATH", str(DEFAULT_DB_PATH)))

st.markdown(
    """
    <style>
      .block-container {max-width: 1500px; padding-top: 1.4rem;}
      .synthetic-banner {padding: .7rem 1rem; border-radius: .5rem; background: #edf4e8; color: #37553d; border: 1px solid #d7e4d0; margin-bottom: 1rem;}
      .small-note {color: #667085; font-size: .88rem;}
      div[data-testid="stMetric"] {background: #fbfcfa; padding: .85rem 1rem; border: 1px solid #e6eae3; border-radius: .6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="synthetic-banner"><strong>SYNTHETIC DEMO DATA</strong> · All entities and activity are generated for this prototype. No live client records are used.</div>', unsafe_allow_html=True)

if "demo_initialized" not in st.session_state:
    try:
        with st.spinner("Preparing reproducible synthetic portfolio…"):
            st.session_state["pipeline_result"] = run_demo_pipeline(DB_PATH)
            st.session_state["demo_initialized"] = True
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        st.error(f"Could not initialize the local demo database: {exc}")
        st.stop()

st.title("Smart KYC · Client Data Quality")
st.caption("Analyst-led corporate onboarding controls · local SQLite persistence · synthetic records only")

pages = ["Operations overview", "Review queue", "Client records", "Duplicate candidates", "Audit history", "Reporting & exports"]
with st.sidebar:
    st.markdown("### Smart KYC")
    st.caption("SYNTHETIC PORTFOLIO")
    page = st.radio("Workspace", pages, label_visibility="collapsed")
    st.divider()
    st.markdown("**Prototype boundary**")
    st.caption("Rule-based prioritization is a work-ordering score, not a calibrated probability. This prototype does not replace a bank's KYC policy or compliance review.")
    st.caption(f"Database: local SQLite (`{DB_PATH.name}`)")


def dataframe_or_empty(frame: pd.DataFrame, message: str = "No rows to display.", **kwargs: object) -> None:
    if frame.empty:
        st.info(message)
    else:
        st.dataframe(frame, width="stretch", hide_index=True, **kwargs)


def refresh_page() -> None:
    st.rerun()


if page == "Operations overview":
    metrics = summary_metrics(DB_PATH)
    cols = st.columns(6)
    cols[0].metric("Clients", metrics["total_clients"])
    cols[1].metric("KYC complete", metrics["complete_clients"])
    cols[2].metric("Open exceptions", metrics["open_exceptions"])
    cols[3].metric("Open cases", metrics["open_review_cases"])
    cols[4].metric("Candidates", metrics["duplicate_candidates"])
    cols[5].metric("Overdue reviews", metrics["overdue_periodic_reviews"])
    st.caption(f"Open cases aged 14+ days: {metrics['aged_open_cases_14d']}")

    left, right = st.columns((1.15, 1))
    with left:
        st.subheader("Exception signals by category")
        exceptions = read_table(DB_PATH, "validation_exceptions")
        if exceptions.empty:
            st.info("No exceptions are present in this database.")
        else:
            open_exceptions = exceptions.loc[exceptions["status"] == "open"]
            if open_exceptions.empty:
                st.info("No open exceptions remain in this portfolio.")
            else:
                category_counts = open_exceptions.groupby(["category", "severity"]).size().unstack(fill_value=0)
                st.bar_chart(category_counts)
    with right:
        st.subheader("Review priority queue")
        queue = review_queue(DB_PATH)
        dataframe_or_empty(queue[["client_id", "legal_name", "priority_score", "priority_band", "status", "age_days"]].head(10) if not queue.empty else queue, "No cases are currently in the review queue.")

    st.subheader("Seeded defect-detection evidence")
    result = st.session_state["pipeline_result"]
    validation = result["validation_evaluation"]
    duplicate_eval = result["duplicate_evaluation"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Seeded validation defects", validation["seeded_defects"])
    m2.metric("Detected", validation["detected_defects"])
    m3.metric("Missed", validation["missed_defects"])
    m4.metric("Defect recall", f"{validation['recall']:.0%}")
    st.caption(f"Recall denominator: {validation['recall_denominator']}. Unseeded detected client-rule pairs (possible false positives): {validation['false_positive_exceptions']}.")
    st.write("**Duplicate candidate evaluation**")
    st.json(duplicate_eval)

elif page == "Review queue":
    st.subheader("Risk-prioritized review queue")
    st.caption("Transparent rule-based ordering only; scores are not probabilities. Filters operate on persistent case data.")
    statuses = ["All"] + sorted(read_table(DB_PATH, "review_cases")["status"].dropna().unique().tolist())
    bands = ["All", "Critical", "High", "Medium", "Low"]
    exceptions = read_table(DB_PATH, "validation_exceptions")
    categories = ["All"] + (sorted(exceptions["category"].dropna().unique().tolist()) if not exceptions.empty else [])
    reviewers = read_table(DB_PATH, "review_cases")["assigned_reviewer"].dropna().unique().tolist()
    age_thresholds = sorted(set(int(value) for value in load_rules()["priority"]["age_days"].values()))
    age_options = ["All"] + [f"{value}+ days" for value in age_thresholds]
    f1, f2, f3, f4, f5 = st.columns(5)
    status_filter = f1.selectbox("Status", statuses)
    priority_filter = f2.selectbox("Priority", bands)
    category_filter = f3.selectbox("Exception category", categories)
    reviewer_filter = f4.selectbox("Reviewer", ["All", "Unassigned"] + sorted(reviewers))
    age_filter = f5.selectbox("Case age", age_options)
    queue = review_queue(
        DB_PATH,
        status=None if status_filter == "All" else status_filter,
        priority_band=None if priority_filter == "All" else priority_filter,
        category=None if category_filter == "All" else category_filter,
        reviewer=None if reviewer_filter == "All" else "Unassigned" if reviewer_filter == "Unassigned" else reviewer_filter,
    )
    if age_filter != "All":
        queue = queue.loc[queue["age_days"] >= int(age_filter.split("+")[0])]
    search = st.text_input("Search client name or reference", placeholder="e.g., Northstar or SYN-0001")
    if search:
        mask = queue["legal_name"].str.contains(search, case=False, na=False) | queue["client_id"].str.contains(search, case=False, na=False)
        queue = queue.loc[mask]
    dataframe_or_empty(queue, "No review cases match the selected filters.")
    if not queue.empty:
        st.download_button("Export filtered review queue CSV", queue.to_csv(index=False).encode("utf-8-sig"), file_name="filtered_review_queue.csv", mime="text/csv")

    if not queue.empty:
        choices = queue["case_id"].tolist()
        selected = st.selectbox("Select a case to inspect", choices, format_func=lambda case_id: f"{queue.loc[queue['case_id'] == case_id, 'client_id'].iloc[0]} · {queue.loc[queue['case_id'] == case_id, 'legal_name'].iloc[0]}")
        case = queue.loc[queue["case_id"] == selected].iloc[0]
        client_col, case_col = st.columns((1, 1))
        with client_col:
            st.markdown("#### Client and exception evidence")
            st.write({"client_id": case["client_id"], "legal_name": case["legal_name"], "country": case["country"], "priority_score": int(case["priority_score"]), "priority_band": case["priority_band"], "priority_explanation": case["priority_explanation"], "open_exception_count": int(case["open_exception_count"])})
            client_exceptions = read_table(DB_PATH, "validation_exceptions", "client_id = ?", (case["client_id"],))
            dataframe_or_empty(client_exceptions, "This case has no recorded exceptions.")
        with case_col:
            st.markdown("#### Record a review action")
            allowed_next = [case["status"]] + load_rules()["case_transitions"].get(case["status"], [])
            with st.form("review_action_form", clear_on_submit=True):
                reviewer = st.text_input("Reviewer / analyst", value=case["assigned_reviewer"] or "", max_chars=80)
                new_status = st.selectbox("Case status", allowed_next, index=0)
                action_type = st.selectbox("Action type", ["review_note", "remediation_recorded", "reviewer_assignment", "evidence_requested"])
                note = st.text_area("Review or remediation note", max_chars=2000, placeholder="Record the evidence reviewed and the next action.")
                submitted = st.form_submit_button("Save review action", type="primary")
                if submitted:
                    try:
                        record_review_action(DB_PATH, selected, new_status=new_status, reviewer=reviewer or None, note=note, action_type=action_type)
                        st.success("Review action saved to SQLite and appended to the audit history.")
                        refresh_page()
                    except (ValueError, KeyError, sqlite3.DatabaseError) as exc:
                        st.error(f"Review action was not saved: {exc}")

elif page == "Client records":
    st.subheader("Client search and KYC completeness")
    clients = read_table(DB_PATH, "clients")
    if clients.empty:
        st.info("No client records. Run `python -m kyc_quality.cli run-demo` to generate the synthetic portfolio.")
    else:
        query = st.text_input("Search synthetic clients", placeholder="Legal name or client ID")
        if query:
            clients = clients.loc[clients["legal_name"].str.contains(query, case=False, na=False) | clients["client_id"].str.contains(query, case=False, na=False)]
        completeness = read_table(DB_PATH, "client_completeness")
        completeness = completeness.loc[completeness["client_id"].isin(clients["client_id"])]
        dataframe_or_empty(completeness, "No completeness results are available.")
        st.download_button("Export filtered client quality CSV", completeness.to_csv(index=False).encode("utf-8-sig"), file_name="filtered_client_quality.csv", mime="text/csv")
        if not clients.empty:
            selected_client = st.selectbox("Inspect client", clients["client_id"].tolist(), format_func=lambda client_id: f"{client_id} · {clients.loc[clients['client_id'] == client_id, 'legal_name'].iloc[0]}")
            client = clients.loc[clients["client_id"] == selected_client].iloc[0]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Original client record")
                st.json(client.to_dict())
                st.markdown("#### Beneficial owners")
                dataframe_or_empty(read_table(DB_PATH, "beneficial_owners", "client_id = ?", (selected_client,)), "No beneficial owners recorded.")
            with c2:
                st.markdown("#### Supporting documents")
                dataframe_or_empty(read_table(DB_PATH, "documents", "client_id = ?", (selected_client,)), "No supporting documents recorded.")
                st.markdown("#### Validation exceptions")
                client_exceptions = read_table(DB_PATH, "validation_exceptions", "client_id = ?", (selected_client,))
                dataframe_or_empty(client_exceptions, "No exceptions recorded for this client.")
                if not client_exceptions.empty:
                    st.download_button("Export client exceptions CSV", client_exceptions.to_csv(index=False).encode("utf-8-sig"), file_name=f"{selected_client}_exceptions.csv", mime="text/csv")
                    exception_ids = client_exceptions["exception_id"].tolist()
                    exception_id = st.selectbox("Exception to update", exception_ids, format_func=lambda item: f"{item} · {client_exceptions.loc[client_exceptions['exception_id'] == item, 'rule_id'].iloc[0]}")
                    with st.form("exception_status_form"):
                        status = st.selectbox("Exception status", ["open", "in_review", "resolved", "false_positive"])
                        note = st.text_input("Disposition note", max_chars=500)
                        if st.form_submit_button("Save exception disposition"):
                            try:
                                set_exception_status(DB_PATH, exception_id, status, "streamlit_analyst", note)
                                st.success("Exception disposition saved and audited.")
                                refresh_page()
                            except (ValueError, KeyError, sqlite3.DatabaseError) as exc:
                                st.error(f"Disposition was not saved: {exc}")

elif page == "Duplicate candidates":
    st.subheader("Duplicate candidates · analyst investigation required")
    st.info("Exact identifiers and RapidFuzz name similarity surface candidates; neither method merges client records. Name similarity alone does not confirm identity.")
    candidates = read_table(DB_PATH, "duplicate_candidates")
    if candidates.empty:
        st.success("No candidate pairs were generated for the current synthetic data and threshold.")
    else:
        dataframe_or_empty(candidates)
        cases = read_table(DB_PATH, "clients")
        name_map = dict(zip(cases["client_id"], cases["legal_name"]))
        candidate_id = st.selectbox(
            "Candidate to investigate",
            candidates["candidate_id"].tolist(),
            format_func=lambda item: f"{name_map.get(candidates.loc[candidates['candidate_id'] == item, 'client_id_1'].iloc[0], '')} ↔ {name_map.get(candidates.loc[candidates['candidate_id'] == item, 'client_id_2'].iloc[0], '')}",
        )
        candidate = candidates.loc[candidates["candidate_id"] == candidate_id].iloc[0]
        st.write({"method": candidate["match_method"], "similarity_score": candidate["similarity_score"], "matching_fields": candidate["matching_fields"], "differing_fields": candidate["differing_fields"], "explanation": candidate["explanation"]})
        with st.form("duplicate_review_form"):
            decision = st.selectbox("Manual disposition", ["candidate", "confirmed_duplicate", "false_positive"], format_func=lambda value: {"candidate": "Keep for review", "confirmed_duplicate": "Confirm after investigation", "false_positive": "Mark as false positive"}[value])
            note = st.text_input("Investigation note", max_chars=1000)
            if st.form_submit_button("Save duplicate disposition"):
                try:
                    review_duplicate_candidate(DB_PATH, candidate_id, decision, "streamlit_analyst", note)
                    st.success("Manual disposition saved; no records were merged.")
                    refresh_page()
                except (ValueError, KeyError, sqlite3.DatabaseError) as exc:
                    st.error(f"Disposition was not saved: {exc}")

elif page == "Audit history":
    st.subheader("Append-only audit history")
    st.caption("Status changes, assignment and remediation actions are recorded with actor, previous/new status, note, and timestamp. Database triggers reject updates and deletions to audit rows.")
    audit = audit_for_entity(DB_PATH)
    dataframe_or_empty(audit, "No audit events are recorded yet.")

elif page == "Reporting & exports":
    st.subheader("Reporting and reconciliation exports")
    st.caption("Power BI-compatible fact/dimension CSVs and Excel reconciliation tables are generated from current SQLite state.")
    metrics = summary_metrics(DB_PATH)
    st.json(metrics)
    frames = build_report_frames(DB_PATH)
    report_names = ["client_quality_summary", "exceptions", "duplicate_candidates", "review_queue", "case_aging", "reviewer_workload", "audit_history", "dim_client", "dim_rule", "fact_exceptions", "fact_review_cases", "fact_review_actions"]
    selected_report = st.selectbox("Preview a reporting table", report_names)
    dataframe_or_empty(frames[selected_report], "This reporting table currently has no rows.")
    csv_bytes = frames[selected_report].to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download selected table as CSV", csv_bytes, file_name=f"{selected_report}.csv", mime="text/csv")
    export_dir = Path(os.getenv("KYC_REPORT_DIR", str(DEFAULT_DB_PATH.parent.parent / "reports" / "generated")))
    if st.button("Build CSV set and XLSX reconciliation workbook"):
        try:
            exported = export_reports(DB_PATH, export_dir)
            st.success(f"Generated {len(exported) - 1} CSV files and the reconciliation workbook in {export_dir}.")
            workbook = exported["xlsx_workbook"].read_bytes()
            st.download_button("Download reconciliation workbook", workbook, file_name="smart_kyc_reconciliation.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            st.error(f"Export failed: {exc}")


def load_transitions(status: str) -> list[str]:
    from kyc_quality.config import load_rules

    return load_rules()["case_transitions"].get(status, [])
