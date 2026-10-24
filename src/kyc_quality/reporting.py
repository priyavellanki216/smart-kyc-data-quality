from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_rules
from .database import audit_for_entity, read_table, review_queue


def build_report_frames(database_path: str | Path) -> dict[str, pd.DataFrame]:
    clients = read_table(database_path, "clients")
    owners = read_table(database_path, "beneficial_owners")
    documents = read_table(database_path, "documents")
    exceptions = read_table(database_path, "validation_exceptions")
    duplicates = read_table(database_path, "duplicate_candidates")
    cases = read_table(database_path, "review_cases")
    actions = read_table(database_path, "review_actions")
    audit = audit_for_entity(database_path)
    completeness = read_table(database_path, "client_completeness")
    queue = review_queue(database_path)

    if not exceptions.empty:
        exception_counts = exceptions.groupby("client_id").agg(
            total_exception_count=("exception_id", "count"),
            exception_categories=("category", lambda s: ", ".join(sorted(set(s)))),
        ).reset_index()
    else:
        exception_counts = pd.DataFrame(columns=["client_id", "total_exception_count", "exception_categories"])
    client_quality = completeness.merge(exception_counts, on="client_id", how="left")
    for col in ("total_exception_count", "open_exception_count"):
        client_quality[col] = client_quality[col].fillna(0).astype(int)
    client_quality["quality_status"] = client_quality.apply(
        lambda row: "Complete" if row["kyc_complete"] else "Needs review", axis=1
    )

    aging = queue[[c for c in ["case_id", "client_id", "legal_name", "status", "priority_score", "priority_band", "assigned_reviewer", "opened_at", "age_days", "open_exception_count"] if c in queue.columns]].copy()
    if not cases.empty:
        workload = cases.groupby(["assigned_reviewer", "status"], dropna=False).size().reset_index(name="case_count")
        workload["assigned_reviewer"] = workload["assigned_reviewer"].astype("object").fillna("Unassigned")
    else:
        workload = pd.DataFrame(columns=["assigned_reviewer", "status", "case_count"])

    rule_rows = [
        {"rule_id": rule_id, "category": detail["category"], "severity": detail["severity"], "title": detail["title"]}
        for rule_id, detail in load_rules()["rules"].items()
    ]
    return {
        "clients": clients,
        "client_quality_summary": client_quality,
        "beneficial_owners": owners,
        "documents": documents,
        "exceptions": exceptions,
        "duplicate_candidates": duplicates,
        "review_queue": queue,
        "case_aging": aging,
        "reviewer_workload": workload,
        "review_actions": actions,
        "audit_history": audit,
        "dim_client": client_quality.copy(),
        "dim_rule": pd.DataFrame(rule_rows),
        "fact_exceptions": exceptions.copy(),
        "fact_review_cases": cases.copy(),
        "fact_review_actions": actions.copy(),
        "fact_duplicate_candidates": duplicates.copy(),
    }


def export_reports(database_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """Write UTF-8 CSV reporting tables and a multi-sheet Excel workbook."""
    frames = build_report_frames(database_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    exported: dict[str, Path] = {}
    for name, frame in frames.items():
        path = destination / f"{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        exported[name] = path
    workbook = destination / "smart_kyc_reconciliation.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        for name, frame in frames.items():
            sheet = name[:31]
            frame.to_excel(writer, sheet_name=sheet, index=False)
            worksheet = writer.sheets[sheet]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                max_len = max((len(str(cell.value or "")) for cell in column_cells[:200]), default=10)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 10), 42)
    exported["xlsx_workbook"] = workbook
    return exported


def summary_metrics(database_path: str | Path, as_of: Any = None) -> dict[str, Any]:
    from datetime import date

    clients = read_table(database_path, "clients")
    completeness = read_table(database_path, "client_completeness")
    exceptions = read_table(database_path, "validation_exceptions")
    duplicates = read_table(database_path, "duplicate_candidates")
    cases = read_table(database_path, "review_cases")
    queue = review_queue(database_path)
    today = as_of or date.today()
    due_dates = pd.to_datetime(clients.get("periodic_review_due", pd.Series(dtype=str)), errors="coerce").dt.date
    overdue_reviews = int((due_dates.notna() & (due_dates < today)).sum()) if not clients.empty else 0
    open_exceptions = exceptions.loc[exceptions["status"] == "open"] if not exceptions.empty else exceptions
    open_cases = queue.loc[~queue["status"].isin(["resolved", "closed"])] if not queue.empty else queue
    age_threshold = int(load_rules()["priority"]["age_days"]["first_threshold"])
    return {
        "total_clients": int(len(clients)),
        "complete_clients": int(completeness["kyc_complete"].sum()) if not completeness.empty else 0,
        "incomplete_clients": int(len(clients) - completeness["kyc_complete"].sum()) if not completeness.empty else int(len(clients)),
        "required_fields_complete": int(completeness["required_fields_complete"].sum()) if not completeness.empty else 0,
        "open_exceptions": int(len(open_exceptions)),
        "exceptions_by_category": open_exceptions.groupby("category").size().to_dict() if not open_exceptions.empty else {},
        "exceptions_by_severity": open_exceptions.groupby("severity").size().to_dict() if not open_exceptions.empty else {},
        "duplicate_candidates": int((duplicates["status"] == "candidate").sum()) if not duplicates.empty else 0,
        "open_review_cases": int((~cases["status"].isin(["resolved", "closed"])).sum()) if not cases.empty else 0,
        "overdue_periodic_reviews": overdue_reviews,
        "aged_open_cases_14d": int((open_cases["age_days"] >= age_threshold).sum()) if not open_cases.empty else 0,
        "case_aging_mean_days": round(float(open_cases["age_days"].mean()), 2) if not open_cases.empty else 0.0,
        "review_outcomes": cases["status"].value_counts().to_dict() if not cases.empty else {},
    }
