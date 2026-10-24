from __future__ import annotations

import hashlib
import re
from itertools import combinations
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from .config import load_rules

CANDIDATE_COLUMNS = ["candidate_id", "client_id_1", "client_id_2", "match_method", "similarity_score", "matching_fields", "differing_fields", "explanation", "status"]
_SUFFIXES = {"limited", "ltd", "incorporated", "inc", "corporation", "corp", "company", "co", "llc", "plc", "lp"}


def normalize_company_name(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    words = [word for word in text.split() if word not in _SUFFIXES]
    return " ".join(words)


def _key(left: str, right: str, method: str) -> tuple[str, str, str]:
    first, second = sorted((left, right))
    return first, second, method


def _candidate_id(first: str, second: str, method: str) -> str:
    raw = "|".join((*_key(first, second, method),))
    return "DUP-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14].upper()


def _make_candidate(left: dict[str, Any], right: dict[str, Any], method: str, score: float, matching: list[str]) -> dict[str, Any]:
    left_id, right_id = str(left["client_id"]), str(right["client_id"])
    first, second = sorted((left_id, right_id))
    if left_id != first:
        left, right = right, left
    fields = ["legal_name", "registration_number", "jurisdiction", "registered_address", "country"]
    differences = [field for field in fields if str(left.get(field, "")).strip().casefold() != str(right.get(field, "")).strip().casefold()]
    if method == "exact_identifier":
        explanation = "Registration number and jurisdiction match exactly; compare legal names and addresses before confirming identity. No records are merged."
    else:
        explanation = f"Normalized legal names are {score:.1f}% similar. Review identifier, jurisdiction, and address evidence; name similarity alone is not a duplicate finding."
    return {
        "candidate_id": _candidate_id(first, second, method),
        "client_id_1": first,
        "client_id_2": second,
        "match_method": method,
        "similarity_score": round(float(score), 2),
        "matching_fields": ", ".join(matching) if matching else "normalized legal_name",
        "differing_fields": ", ".join(differences) if differences else "none in compared fields",
        "explanation": explanation,
        "status": "candidate",
    }


def detect_duplicate_candidates(clients: pd.DataFrame, rules: dict[str, Any] | None = None, threshold: float | None = None) -> pd.DataFrame:
    """Generate exact registration/jurisdiction matches and fuzzy name candidates.

    Returned pairs are investigation candidates only. This function never merges or confirms
    records and preserves dissimilar identifier/address evidence for analyst comparison.
    """
    config = rules or load_rules()
    configured_threshold = float(config["duplicate_threshold"] if threshold is None else threshold)
    if not 0 <= configured_threshold <= 100:
        raise ValueError("threshold must be between 0 and 100")
    required = {"client_id", "legal_name", "registration_number", "jurisdiction"}
    missing = required - set(clients.columns)
    if missing:
        raise ValueError(f"clients is missing required columns: {sorted(missing)}")

    records = clients.fillna("").to_dict(orient="records")
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    exact_keys: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        registration = re.sub(r"[^A-Z0-9]", "", str(record.get("registration_number", "")).upper())
        jurisdiction = str(record.get("jurisdiction", "")).strip().upper()
        if registration and jurisdiction:
            exact_keys.setdefault((jurisdiction, registration), []).append(record)
    for matches in exact_keys.values():
        if len(matches) > 1:
            for left, right in combinations(matches, 2):
                pair = _key(str(left["client_id"]), str(right["client_id"]), "exact_identifier")
                candidates[pair] = _make_candidate(left, right, "exact_identifier", 100.0, ["registration_number", "jurisdiction"])

    for left, right in combinations(records, 2):
        left_id, right_id = str(left["client_id"]), str(right["client_id"])
        if left_id == right_id:
            continue
        exact_key = _key(left_id, right_id, "exact_identifier")
        if config.get("duplicate_block_exact_pair_from_fuzzy", True) and exact_key in candidates:
            continue
        left_name = normalize_company_name(left.get("legal_name"))
        right_name = normalize_company_name(right.get("legal_name"))
        if not left_name or not right_name:
            continue
        # The maximum of sequence and token-sort ratios captures both a split compound
        # token ("Crownridge" vs "Crown Ridge") and re-ordered name components.
        score = float(max(fuzz.ratio(left_name, right_name), fuzz.token_sort_ratio(left_name, right_name)))
        if score >= configured_threshold:
            pair = _key(left_id, right_id, "fuzzy_name")
            candidates[pair] = _make_candidate(left, right, "fuzzy_name", score, [])
    return pd.DataFrame(list(candidates.values()), columns=CANDIDATE_COLUMNS).sort_values(
        ["match_method", "similarity_score", "client_id_1", "client_id_2"], ascending=[True, False, True, True], ignore_index=True
    ) if candidates else pd.DataFrame(columns=CANDIDATE_COLUMNS)


def evaluate_duplicate_candidates(seeded_defects: pd.DataFrame, candidates: pd.DataFrame) -> dict[str, Any]:
    expected = seeded_defects.loc[seeded_defects["defect_type"].isin(["duplicate_exact", "duplicate_fuzzy"])]
    expected_pairs = {tuple(sorted((row.client_id, row.client_id_2))) for row in expected.itertuples()}
    candidate_pairs = {tuple(sorted((row.client_id_1, row.client_id_2))) for row in candidates.itertuples()} if not candidates.empty else set()
    detected = expected_pairs & candidate_pairs
    missed = expected_pairs - candidate_pairs
    false_positive = candidate_pairs - expected_pairs
    precision = len(detected) / len(candidate_pairs) if candidate_pairs else (1.0 if not expected_pairs else 0.0)
    recall = len(detected) / len(expected_pairs) if expected_pairs else 1.0
    return {
        "seeded_true_duplicate_pairs": len(expected_pairs),
        "candidate_pairs_generated": len(candidate_pairs),
        "seeded_pairs_candidate_generated": len(detected),
        "missed_seeded_pairs": len(missed),
        "false_positive_candidates": len(false_positive),
        "candidate_precision_against_seeded_pairs": precision,
        "candidate_recall_against_seeded_pairs": recall,
        "interpretation": "Candidates require human investigation and are not confirmed duplicates.",
        "missed_pairs": [" / ".join(pair) for pair in sorted(missed)],
        "false_positive_pairs": [" / ".join(pair) for pair in sorted(false_positive)],
    }
