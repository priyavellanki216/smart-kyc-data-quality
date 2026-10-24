from datetime import date

import pandas as pd

from kyc_quality.prioritization import calculate_priority_scores


def test_priority_score_explains_contributions_and_is_not_probability():
    exceptions = pd.DataFrame([
        {"client_id": "A", "rule_id": "DOC-002", "severity": "high", "category": "documentation"},
        {"client_id": "A", "rule_id": "ATTR-001", "severity": "high", "category": "attributes"},
    ])
    candidates = pd.DataFrame([{"client_id_1": "A", "client_id_2": "B"}])
    result = calculate_priority_scores(exceptions, candidates, now=date(2026, 10, 24)).set_index("client_id")
    assert result.loc["A", "priority_score"] > result.loc["B", "priority_score"]
    assert "expired document" in result.loc["A", "priority_explanation"]
    assert "conflicting attributes" in result.loc["A", "priority_explanation"]
    assert "potential duplicate" in result.loc["A", "priority_explanation"]
    assert "not a probability" in result.loc["A", "score_type"]
    assert result["priority_score"].between(0, 100).all()


def test_age_contributions_are_configurable_and_score_is_capped():
    exceptions = pd.DataFrame([
        {"client_id": "A", "rule_id": "REQ-001", "severity": "critical", "category": "completeness"},
        {"client_id": "A", "rule_id": "DOC-002", "severity": "high", "category": "documentation"},
        {"client_id": "A", "rule_id": "ATTR-001", "severity": "high", "category": "attributes"},
    ])
    cases = pd.DataFrame([{"client_id": "A", "opened_at": "2026-09-01T00:00:00+00:00"}])
    result = calculate_priority_scores(exceptions, cases=cases, now=date(2026, 10, 24)).iloc[0]
    assert result["case_age_days"] == 53
    assert result["priority_score"] == 100
    assert "case age ≥14 days" in result["priority_explanation"]
    assert "case age ≥30 days" in result["priority_explanation"]
    assert result["priority_band"] == "Critical"
