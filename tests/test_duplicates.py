import pandas as pd
import pytest

from kyc_quality.duplicates import detect_duplicate_candidates, evaluate_duplicate_candidates, normalize_company_name
from kyc_quality.synthetic_data import generate_synthetic_dataset


def test_exact_match_requires_normalized_registration_and_jurisdiction():
    clients = pd.DataFrame([
        {"client_id": "A", "legal_name": "Alpha Ltd", "registration_number": "GB-123456", "jurisdiction": "GB", "registered_address": "1 A, London", "country": "GB"},
        {"client_id": "B", "legal_name": "Alpha Limited", "registration_number": "GB123456", "jurisdiction": "GB", "registered_address": "2 B, London", "country": "GB"},
        {"client_id": "C", "legal_name": "Alpha LLC", "registration_number": "GB123456", "jurisdiction": "US", "registered_address": "3 C, Boston", "country": "US"},
    ])
    result = detect_duplicate_candidates(clients)
    exact = result.loc[result["match_method"] == "exact_identifier"]
    assert len(exact) == 1
    assert set(exact.iloc[0][["client_id_1", "client_id_2"]]) == {"A", "B"}
    assert exact.iloc[0]["similarity_score"] == 100
    assert exact.iloc[0]["status"] == "candidate"
    assert "No records are merged" in exact.iloc[0]["explanation"]


def test_seeded_true_pairs_detected_and_lookalike_remains_unconfirmed_candidate():
    data = generate_synthetic_dataset()
    candidates = detect_duplicate_candidates(data["clients"])
    metrics = evaluate_duplicate_candidates(data["seeded_defects"], candidates)
    assert metrics["seeded_pairs_candidate_generated"] == 2
    assert metrics["missed_seeded_pairs"] == 0
    assert metrics["false_positive_candidates"] == 1
    assert metrics["candidate_recall_against_seeded_pairs"] == 1.0
    assert candidates["status"].eq("candidate").all()
    lookalike = candidates.loc[(candidates["client_id_1"] == "SYN-0033") & (candidates["client_id_2"] == "SYN-0034")]
    assert len(lookalike) == 1
    assert lookalike.iloc[0]["status"] != "confirmed_duplicate"
    assert "name similarity alone" in lookalike.iloc[0]["explanation"]


def test_normalization_removes_punctuation_and_legal_suffixes():
    assert normalize_company_name("Crownridge Logistics, Limited") == "crownridge logistics"


def test_threshold_is_configurable_and_validated():
    clients = pd.DataFrame([
        {"client_id": "A", "legal_name": "Harborfield Analytics Ltd", "registration_number": "GB-0001", "jurisdiction": "GB"},
        {"client_id": "B", "legal_name": "Harbor Field Analytics Inc", "registration_number": "GB-0002", "jurisdiction": "GB"},
    ])
    assert len(detect_duplicate_candidates(clients, threshold=86)) == 1
    assert detect_duplicate_candidates(clients, threshold=100).empty
    with pytest.raises(ValueError, match="between 0 and 100"):
        detect_duplicate_candidates(clients, threshold=101)
