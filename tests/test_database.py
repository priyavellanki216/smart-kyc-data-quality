from datetime import date
import sqlite3

import pandas as pd
import pytest

from kyc_quality.database import (
    audit_for_entity, connect_db, init_db, read_table, record_review_action,
    review_duplicate_candidate, review_queue, seed_database, set_exception_status,
)
from kyc_quality.duplicates import detect_duplicate_candidates
from kyc_quality.prioritization import calculate_priority_scores
from kyc_quality.service import run_demo_pipeline
from kyc_quality.synthetic_data import generate_synthetic_dataset
from kyc_quality.validation import validate_clients


def build_db(path):
    data = generate_synthetic_dataset()
    exceptions = validate_clients(data["clients"], data["beneficial_owners"], data["documents"], now=date(2026, 10, 24))
    candidates = detect_duplicate_candidates(data["clients"])
    scores = calculate_priority_scores(exceptions, candidates, now=date(2026, 10, 24))
    seed_database(path, data, exceptions, candidates, scores)
    return data, exceptions, candidates


def test_schema_foreign_keys_and_seeded_relationships(tmp_path):
    path = tmp_path / "demo.db"
    build_db(path)
    assert len(read_table(path, "clients")) == 40
    assert len(read_table(path, "review_cases")) > 0
    with connect_db(path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO beneficial_owners(owner_id,client_id,owner_name,ownership_percent) VALUES('BAD','NO-SUCH','bad',20)")


def test_case_action_status_transition_and_audit_persistence(tmp_path):
    path = tmp_path / "demo.db"
    build_db(path)
    case = read_table(path, "review_cases").iloc[0]
    action_id = record_review_action(path, case["case_id"], new_status="in_review", reviewer="Analyst A", note="Reviewed source evidence", action_type="review_note")
    assert action_id.startswith("ACT-")
    updated = read_table(path, "review_cases", "case_id = ?", (case["case_id"],)).iloc[0]
    assert updated["status"] == "in_review"
    assert updated["assigned_reviewer"] == "Analyst A"
    events = audit_for_entity(path, "review_case", case["case_id"])
    assert "Reviewed source evidence" in set(events["notes"])
    # A rejected transition is rolled back and does not add an audit action.
    count_before = len(events)
    with pytest.raises(ValueError, match="Invalid case transition"):
        record_review_action(path, case["case_id"], new_status="invented_status", reviewer="Analyst A", note="invalid")
    assert len(audit_for_entity(path, "review_case", case["case_id"])) == count_before
    # Close/reopen semantics are constrained; closing is permitted from in_review.
    record_review_action(path, case["case_id"], new_status="closed", reviewer="Analyst A", note="Complete", action_type="remediation_recorded")
    with pytest.raises(ValueError, match="Invalid case transition"):
        record_review_action(path, case["case_id"], new_status="in_review", reviewer="Analyst A", note="try reopen")
    # Restart/re-read persists the action and current status.
    assert read_table(path, "review_cases", "case_id = ?", (case["case_id"],)).iloc[0]["status"] == "closed"
    assert len(read_table(path, "review_actions", "case_id = ?", (case["case_id"],))) == 2


def test_audit_history_rejects_updates_and_deletes(tmp_path):
    path = tmp_path / "demo.db"
    build_db(path)
    with connect_db(path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE audit_history SET notes='changed' WHERE audit_id=1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM audit_history WHERE audit_id=1")


def test_exception_and_duplicate_dispositions_are_audited(tmp_path):
    path = tmp_path / "demo.db"
    _, exceptions, candidates = build_db(path)
    exc_id = exceptions.iloc[0]["exception_id"]
    set_exception_status(path, exc_id, "resolved", "Analyst B", "Evidence refreshed")
    assert read_table(path, "validation_exceptions", "exception_id = ?", (exc_id,)).iloc[0]["status"] == "resolved"
    candidate_id = candidates.iloc[0]["candidate_id"]
    review_duplicate_candidate(path, candidate_id, "false_positive", "Analyst B", "Distinct registration and address")
    assert read_table(path, "duplicate_candidates", "candidate_id = ?", (candidate_id,)).iloc[0]["status"] == "false_positive"
    assert len(audit_for_entity(path, "duplicate_candidate", candidate_id)) == 1


def test_queue_filters_return_workable_cases(tmp_path):
    path = tmp_path / "demo.db"
    build_db(path)
    full = review_queue(path)
    assert not full.empty
    assert full["priority_score"].between(0, 100).all()
    high = review_queue(path, priority_band="High")
    assert high["priority_band"].eq("High").all()


def test_reseeding_and_app_restart_preserve_actions(tmp_path):
    path = tmp_path / "demo.db"
    run_demo_pipeline(path, as_of=date(2026, 10, 24))
    case = read_table(path, "review_cases").iloc[0]
    record_review_action(path, case["case_id"], new_status="in_review", reviewer="Analyst C", note="Persistent note")
    count_before = len(read_table(path, "review_actions"))
    run_demo_pipeline(path, as_of=date(2026, 10, 24))
    assert len(read_table(path, "review_actions")) == count_before
    persisted = read_table(path, "review_cases", "case_id = ?", (case["case_id"],)).iloc[0]
    assert persisted["status"] == "in_review"
    assert persisted["assigned_reviewer"] == "Analyst C"
