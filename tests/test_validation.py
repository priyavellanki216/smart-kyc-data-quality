from datetime import date

import pandas as pd
import pytest

from kyc_quality.synthetic_data import generate_synthetic_dataset
from kyc_quality.validation import evaluate_seeded_defects, validate_clients


def valid_bundle():
    clients = pd.DataFrame([{
        "client_id": "TST-0001", "legal_name": "Example Sample Ltd",
        "registration_number": "GB-12345678", "jurisdiction": "GB",
        "registered_address": "1 Main Street, London", "country": "GB",
        "incorporation_date": "2010-05-12", "onboarding_date": "2020-06-01",
        "periodic_review_due": "2027-06-01", "review_status": "onboarding", "synthetic": True,
    }])
    owners = pd.DataFrame([{"owner_id": "OWN-T1", "client_id": "TST-0001", "owner_name": "Sample Owner T1", "ownership_percent": 100.0, "identity_reference": "SYN-ID-T1"}])
    docs = pd.DataFrame([{"document_id": "DOC-T1", "client_id": "TST-0001", "document_type": "incorporation", "issue_date": "2020-01-01", "expiry_date": "2027-01-01", "document_reference": "SYN-DOC-T1"}])
    return clients, owners, docs


@pytest.mark.parametrize(
    "rule_id,mutator",
    [
        ("REQ-001", lambda c, o, d: c.__setitem__("legal_name", "")),
        ("REG-001", lambda c, o, d: c.__setitem__("registration_number", "bad??")),
        ("INC-001", lambda c, o, d: c.__setitem__("incorporation_date", "2028-01-01")),
        ("DATE-001", lambda c, o, d: c.__setitem__("onboarding_date", "not-a-date")),
        ("BO-001", lambda c, o, d: (c, o.iloc[0:0].copy(), d)),
        ("BO-002", lambda c, o, d: o.__setitem__("ownership_percent", [120.0])),
        ("DOC-001", lambda c, o, d: (c, o, d.iloc[0:0].copy())),
        ("DOC-002", lambda c, o, d: d.__setitem__("expiry_date", "2024-01-01")),
        ("ADDR-001", lambda c, o, d: c.__setitem__("registered_address", "London")),
        ("ATTR-001", lambda c, o, d: c.__setitem__("jurisdiction", "US")),
        ("REV-001", lambda c, o, d: c.__setitem__("periodic_review_due", "2024-01-01")),
    ],
)
def test_each_individual_rule(rule_id, mutator):
    clients, owners, docs = valid_bundle()
    replacement = mutator(clients, owners, docs)
    if replacement is not None:
        clients, owners, docs = replacement
    found = validate_clients(clients, owners, docs, now=date(2026, 10, 24))
    assert rule_id in set(found["rule_id"])
    assert found["exception_id"].is_unique
    assert found["reason"].str.len().gt(0).all()
    assert found["evidence"].str.len().gt(0).all()
    assert found["status"].eq("open").all()


def test_valid_record_has_no_exceptions_and_inputs_are_not_mutated():
    clients, owners, docs = valid_bundle()
    original_clients, original_owners, original_docs = clients.copy(deep=True), owners.copy(deep=True), docs.copy(deep=True)
    result = validate_clients(clients, owners, docs, now=date(2026, 10, 24))
    assert result.empty
    pd.testing.assert_frame_equal(clients, original_clients)
    pd.testing.assert_frame_equal(owners, original_owners)
    pd.testing.assert_frame_equal(docs, original_docs)


def test_exception_ids_are_stable_across_runs():
    clients, owners, docs = valid_bundle()
    clients.loc[0, "legal_name"] = ""
    first = validate_clients(clients, owners, docs, now=date(2026, 10, 24))
    second = validate_clients(clients, owners, docs, now=date(2026, 10, 25))
    assert first["exception_id"].tolist() == second["exception_id"].tolist()
    assert first.iloc[0]["exception_id"].startswith("EXC-")


def test_seeded_defect_evaluation_has_truthful_defect_level_denominator():
    data = generate_synthetic_dataset()
    exceptions = validate_clients(data["clients"], data["beneficial_owners"], data["documents"], now=date(2026, 10, 24))
    metrics = evaluate_seeded_defects(data["seeded_defects"], exceptions)
    assert metrics["seeded_defects"] == 9
    assert metrics["detected_defects"] == 9
    assert metrics["missed_defects"] == 0
    assert metrics["false_positive_exceptions"] == 0
    assert metrics["recall"] == 1.0
    assert "distinct seeded" in metrics["recall_denominator"]
