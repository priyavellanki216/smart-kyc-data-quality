from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_rules, project_root

DEFAULT_DB_PATH = project_root() / "data" / "kyc_demo.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db(path: str | Path = DEFAULT_DB_PATH) -> Path:
    schema_path = project_root() / "sql" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    with connect_db(path) as connection:
        connection.executescript(schema)
    return Path(path)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    result: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if pd.isna(value):
                normalized[key] = None
            elif hasattr(value, "item"):
                normalized[key] = value.item()
            else:
                normalized[key] = value
        result.append(normalized)
    return result


def seed_database(
    path: str | Path,
    dataset: dict[str, pd.DataFrame],
    exceptions: pd.DataFrame,
    duplicate_candidates: pd.DataFrame,
    priority_scores: pd.DataFrame,
) -> None:
    """Idempotently load synthetic source data and calculated findings without deleting actions."""
    init_db(path)
    now = utc_now()
    with connect_db(path) as connection:
        for row in _records(dataset["clients"]):
            connection.execute(
                """INSERT OR IGNORE INTO clients
                (client_id, legal_name, registration_number, jurisdiction, registered_address, country,
                 incorporation_date, onboarding_date, periodic_review_due, review_status, synthetic)
                VALUES (:client_id, :legal_name, :registration_number, :jurisdiction, :registered_address,
                        :country, :incorporation_date, :onboarding_date, :periodic_review_due, :review_status, :synthetic)""",
                row,
            )
        for row in _records(dataset["beneficial_owners"]):
            connection.execute(
                """INSERT OR IGNORE INTO beneficial_owners
                (owner_id, client_id, owner_name, ownership_percent, identity_reference)
                VALUES (:owner_id, :client_id, :owner_name, :ownership_percent, :identity_reference)""",
                row,
            )
        for row in _records(dataset["documents"]):
            connection.execute(
                """INSERT OR IGNORE INTO documents
                (document_id, client_id, document_type, issue_date, expiry_date, document_reference)
                VALUES (:document_id, :client_id, :document_type, :issue_date, :expiry_date, :document_reference)""",
                row,
            )
        for row in _records(exceptions):
            connection.execute(
                """INSERT OR IGNORE INTO validation_exceptions
                (exception_id, client_id, rule_id, category, severity, reason, evidence, detected_at, status)
                VALUES (:exception_id, :client_id, :rule_id, :category, :severity, :reason, :evidence, :detected_at, :status)""",
                row,
            )
        for row in _records(duplicate_candidates):
            connection.execute(
                """INSERT OR IGNORE INTO duplicate_candidates
                (candidate_id, client_id_1, client_id_2, match_method, similarity_score,
                 matching_fields, differing_fields, explanation, status)
                VALUES (:candidate_id, :client_id_1, :client_id_2, :match_method, :similarity_score,
                        :matching_fields, :differing_fields, :explanation, :status)""",
                row,
            )
        score_rows = {row["client_id"]: row for row in _records(priority_scores)}
        affected = set(exceptions.get("client_id", pd.Series(dtype=str)).astype(str))
        if not duplicate_candidates.empty:
            affected.update(duplicate_candidates["client_id_1"].astype(str))
            affected.update(duplicate_candidates["client_id_2"].astype(str))
        for client_id in sorted(affected):
            score = score_rows.get(client_id, {"priority_score": 0, "priority_band": "Low", "priority_explanation": "No priority contributions."})
            case_id = "CASE-" + hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:12].upper()
            existing = connection.execute("SELECT case_id FROM review_cases WHERE client_id = ?", (client_id,)).fetchone()
            connection.execute(
                """INSERT INTO review_cases
                (case_id, client_id, priority_score, priority_band, priority_explanation, status, opened_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    priority_score=excluded.priority_score,
                    priority_band=excluded.priority_band,
                    priority_explanation=excluded.priority_explanation,
                    updated_at=excluded.updated_at""",
                (case_id, client_id, int(score["priority_score"]), score["priority_band"], score["priority_explanation"], now, now),
            )
            if existing is None:
                _append_audit(connection, "review_case", case_id, "case_created", "system:synthetic_seed", "", "pending", "Seeded synthetic review case", now)


def _append_audit(
    connection: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    previous_value: str,
    new_value: str,
    notes: str,
    timestamp: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO audit_history
        (entity_type, entity_id, action, actor, previous_value, new_value, notes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, action, actor, previous_value, new_value, notes, timestamp or utc_now()),
    )


def record_review_action(
    path: str | Path,
    case_id: str,
    *,
    new_status: str | None = None,
    reviewer: str | None = None,
    note: str = "",
    action_type: str = "review_update",
) -> str:
    """Persist a validated case action and matching audit event in one transaction."""
    config = load_rules()
    timestamp = utc_now()
    note = str(note or "").strip()
    reviewer = str(reviewer or "").strip()
    with connect_db(path) as connection:
        row = connection.execute("SELECT * FROM review_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(f"Review case not found: {case_id}")
        previous_status = row["status"]
        target_status = new_status or previous_status
        allowed = config["case_transitions"].get(previous_status, [])
        if target_status != previous_status and target_status not in allowed:
            raise ValueError(f"Invalid case transition: {previous_status} -> {target_status}")
        assigned = reviewer or row["assigned_reviewer"]
        actor = reviewer or row["assigned_reviewer"] or "analyst:unassigned"
        if target_status == previous_status and not note and not reviewer:
            raise ValueError("Provide a note, reviewer assignment, or status change")
        connection.execute(
            "UPDATE review_cases SET status = ?, assigned_reviewer = ?, updated_at = ? WHERE case_id = ?",
            (target_status, assigned, timestamp, case_id),
        )
        action_id = "ACT-" + uuid.uuid4().hex[:14].upper()
        connection.execute(
            """INSERT INTO review_actions
            (action_id, case_id, action_type, reviewer, note, previous_status, new_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (action_id, case_id, action_type, actor, note, previous_status, target_status, timestamp),
        )
        _append_audit(
            connection, "review_case", case_id, action_type, actor,
            previous_status, target_status, note or (f"Assigned to {reviewer}" if reviewer else "Status updated"), timestamp,
        )
        return action_id


def set_exception_status(path: str | Path, exception_id: str, status: str, actor: str, note: str = "") -> None:
    if status not in {"open", "in_review", "resolved", "false_positive"}:
        raise ValueError(f"Unsupported exception status: {status}")
    timestamp = utc_now()
    with connect_db(path) as connection:
        row = connection.execute("SELECT status FROM validation_exceptions WHERE exception_id = ?", (exception_id,)).fetchone()
        if row is None:
            raise KeyError(f"Exception not found: {exception_id}")
        previous = row["status"]
        connection.execute("UPDATE validation_exceptions SET status = ? WHERE exception_id = ?", (status, exception_id))
        _append_audit(connection, "validation_exception", exception_id, "exception_status_changed", actor, previous, status, note, timestamp)


def review_duplicate_candidate(path: str | Path, candidate_id: str, decision: str, actor: str, note: str = "") -> None:
    if decision not in {"confirmed_duplicate", "false_positive", "candidate"}:
        raise ValueError("decision must be confirmed_duplicate, false_positive, or candidate")
    timestamp = utc_now()
    with connect_db(path) as connection:
        row = connection.execute("SELECT status FROM duplicate_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(f"Duplicate candidate not found: {candidate_id}")
        previous = row["status"]
        connection.execute("UPDATE duplicate_candidates SET status = ? WHERE candidate_id = ?", (decision, candidate_id))
        _append_audit(connection, "duplicate_candidate", candidate_id, "duplicate_reviewed", actor, previous, decision, note, timestamp)


def read_table(path: str | Path, table: str, where: str = "", params: tuple[Any, ...] = ()) -> pd.DataFrame:
    allowed = {"clients", "beneficial_owners", "documents", "validation_exceptions", "duplicate_candidates", "review_cases", "review_actions", "audit_history", "client_completeness"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    query = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "")
    with connect_db(path) as connection:
        return pd.read_sql_query(query, connection, params=params)


def review_queue(path: str | Path, status: str | None = None, priority_band: str | None = None, category: str | None = None, reviewer: str | None = None) -> pd.DataFrame:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("rc.status = ?")
        params.append(status)
    if priority_band:
        conditions.append("rc.priority_band = ?")
        params.append(priority_band)
    if reviewer:
        if reviewer == "Unassigned":
            conditions.append("(rc.assigned_reviewer IS NULL OR TRIM(rc.assigned_reviewer) = '')")
        else:
            conditions.append("rc.assigned_reviewer = ?")
            params.append(reviewer)
    if category:
        conditions.append("EXISTS (SELECT 1 FROM validation_exceptions e WHERE e.client_id = c.client_id AND e.category = ? AND e.status = 'open')")
        params.append(category)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""SELECT rc.case_id, c.client_id, c.legal_name, c.registration_number,
        c.country, rc.status, rc.priority_score, rc.priority_band, rc.priority_explanation,
        rc.assigned_reviewer, rc.opened_at, rc.updated_at,
        CAST(MAX(julianday('now') - julianday(rc.opened_at), 0) AS INTEGER) AS age_days,
        COALESCE((SELECT group_concat(DISTINCT e.category) FROM validation_exceptions e
                  WHERE e.client_id = c.client_id AND e.status = 'open'), '') AS exception_categories,
        (SELECT COUNT(*) FROM validation_exceptions e WHERE e.client_id = c.client_id AND e.status = 'open') AS open_exception_count
        FROM review_cases rc JOIN clients c USING(client_id){where}
        ORDER BY rc.priority_score DESC, rc.opened_at ASC"""
    with connect_db(path) as connection:
        return pd.read_sql_query(query, connection, params=params)


def audit_for_entity(path: str | Path, entity_type: str | None = None, entity_id: str | None = None) -> pd.DataFrame:
    conditions: list[str] = []
    params: list[Any] = []
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with connect_db(path) as connection:
        return pd.read_sql_query(f"SELECT * FROM audit_history{where} ORDER BY timestamp DESC, audit_id DESC", connection, params=params)
