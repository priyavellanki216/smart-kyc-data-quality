from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .config import load_rules

EXCEPTION_COLUMNS = ["exception_id", "client_id", "rule_id", "category", "severity", "reason", "evidence", "detected_at", "status"]


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (not isinstance(value, str) and pd.isna(value))


def _parse_date(value: Any, fmt: str) -> date | None:
    if _missing(value):
        return None
    try:
        return datetime.strptime(str(value).strip(), fmt).date()
    except (TypeError, ValueError):
        return None


def _stable_exception_id(client_id: str, rule_id: str, evidence_key: str) -> str:
    payload = f"{client_id}|{rule_id}|{evidence_key}".encode("utf-8")
    return "EXC-" + hashlib.sha256(payload).hexdigest()[:14].upper()


def validate_clients(
    clients: pd.DataFrame,
    beneficial_owners: pd.DataFrame | None = None,
    documents: pd.DataFrame | None = None,
    rules: dict[str, Any] | None = None,
    now: date | datetime | None = None,
) -> pd.DataFrame:
    """Validate records without mutating inputs; return stable-ID, explainable exceptions."""
    config = rules or load_rules()
    today = now.date() if isinstance(now, datetime) else (now or date.today())
    detected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    owners = beneficial_owners if beneficial_owners is not None else pd.DataFrame(columns=["client_id", "owner_name", "ownership_percent"])
    docs = documents if documents is not None else pd.DataFrame(columns=["client_id", "document_id", "expiry_date"])
    if "client_id" not in clients.columns:
        raise ValueError("clients must include client_id")

    rows: list[dict[str, Any]] = []

    def emit(client_id: str, rule_id: str, field: str, reason: str, evidence: str) -> None:
        meta = config["rules"][rule_id]
        rows.append({
            "exception_id": _stable_exception_id(client_id, rule_id, field),
            "client_id": client_id,
            "rule_id": rule_id,
            "category": meta["category"],
            "severity": meta["severity"],
            "reason": reason,
            "evidence": evidence,
            "detected_at": detected_at,
            "status": "open",
        })

    for record in clients.to_dict(orient="records"):
        client_id = str(record.get("client_id", ""))
        for field in config["mandatory_client_fields"]:
            if field not in record or _missing(record.get(field)):
                emit(client_id, "REQ-001", field, f"Mandatory client field '{field}' is missing.", f"field={field}; value=<blank>")

        registration = record.get("registration_number")
        if not _missing(registration) and not re.fullmatch(config["registration_number_pattern"], str(registration).strip().upper()):
            emit(client_id, "REG-001", "registration_number", "Registration number does not match the configured format.", f"registration_number={registration}")

        incorporation = _parse_date(record.get("incorporation_date"), config["date_format"])
        if not _missing(record.get("incorporation_date")) and incorporation is None:
            emit(client_id, "INC-001", "incorporation_date", "Incorporation date is not in the permitted format.", f"value={record.get('incorporation_date')}")
        elif incorporation is not None and incorporation > today:
            emit(client_id, "INC-001", "incorporation_date", "Incorporation date is in the future.", f"value={incorporation.isoformat()}; as_of={today.isoformat()}")

        address = record.get("registered_address")
        if not _missing(address):
            components = [part.strip() for part in str(address).split(",") if part.strip()]
            if len(components) < int(config["mandatory_address_components"]):
                emit(client_id, "ADDR-001", "registered_address", "Registered address is incomplete under the configured component rule.", f"address={address}; components={len(components)}")

        jurisdiction, country = record.get("jurisdiction"), record.get("country")
        if not _missing(jurisdiction) and not _missing(country) and str(jurisdiction).strip().upper() != str(country).strip().upper():
            emit(client_id, "ATTR-001", "jurisdiction/country", "Country of registration conflicts with the client country attribute.", f"jurisdiction={jurisdiction}; country={country}")

        onboarding = _parse_date(record.get("onboarding_date"), config["date_format"])
        review_due = _parse_date(record.get("periodic_review_due"), config["date_format"])
        if not _missing(record.get("onboarding_date")) and onboarding is None:
            emit(client_id, "DATE-001", "onboarding_date", "Onboarding date is invalid or uses an unsupported format.", f"value={record.get('onboarding_date')}")
        if not _missing(record.get("periodic_review_due")) and review_due is None:
            emit(client_id, "DATE-001", "periodic_review_due", "Periodic-review due date is invalid or uses an unsupported format.", f"value={record.get('periodic_review_due')}")
        elif onboarding is not None and review_due is not None and review_due < onboarding:
            emit(client_id, "DATE-001", "periodic_review_due", "Periodic-review due date precedes onboarding.", f"onboarding={onboarding.isoformat()}; due={review_due.isoformat()}")
        elif review_due is not None and review_due < today:
            emit(client_id, "REV-001", "periodic_review_due", "Periodic client review is overdue.", f"due={review_due.isoformat()}; as_of={today.isoformat()}")

        client_owners = owners.loc[owners.get("client_id", pd.Series(dtype=str)).astype(str) == client_id] if not owners.empty else owners
        if client_owners.empty:
            emit(client_id, "BO-001", "beneficial_owners", "No beneficial-owner information is recorded for this corporate client.", "beneficial_owner_count=0")
        else:
            percentages = pd.to_numeric(client_owners.get("ownership_percent", pd.Series(dtype=float)), errors="coerce")
            invalid = percentages.isna() | (percentages <= 0) | (percentages > 100)
            if invalid.any() or percentages.sum() > 100.0001:
                emit(client_id, "BO-002", "ownership_percent", "Beneficial-owner percentages are missing, non-positive, above 100, or total more than 100.", f"percentages={percentages.fillna(-1).tolist()}; total={percentages.sum():.2f}")

        client_docs = docs.loc[docs.get("client_id", pd.Series(dtype=str)).astype(str) == client_id] if not docs.empty else docs
        if client_docs.empty:
            emit(client_id, "DOC-001", "documents", "No supporting document metadata is recorded for this client.", "document_count=0")
        else:
            for document in client_docs.to_dict(orient="records"):
                expiry = _parse_date(document.get("expiry_date"), config["date_format"])
                if not _missing(document.get("expiry_date")) and expiry is None:
                    emit(client_id, "DOC-002", f"documents.expiry_date:{document.get('document_id', 'unknown')}", "Document expiry date is invalid or uses an unsupported format.", f"document_id={document.get('document_id')}; expiry={document.get('expiry_date')}")
                elif expiry is not None and expiry < today:
                    emit(client_id, "DOC-002", f"documents.expiry_date:{document.get('document_id', 'unknown')}", "Supporting document has expired.", f"document_id={document.get('document_id')}; expiry={expiry.isoformat()}; as_of={today.isoformat()}")

    return pd.DataFrame(rows, columns=EXCEPTION_COLUMNS).drop_duplicates(subset=["exception_id"]).reset_index(drop=True)


def evaluate_seeded_defects(seeded_defects: pd.DataFrame, exceptions: pd.DataFrame) -> dict[str, Any]:
    """Measure validation defect detection using seeded rule/client pairs as the denominator."""
    expected = seeded_defects.loc[seeded_defects["defect_type"] == "validation", ["client_id", "rule_id"]].drop_duplicates()
    expected_pairs = set(map(tuple, expected.to_numpy()))
    detected_pairs = set(map(tuple, exceptions[["client_id", "rule_id"]].drop_duplicates().to_numpy())) if not exceptions.empty else set()
    detected = expected_pairs & detected_pairs
    missed = expected_pairs - detected_pairs
    unseeded = detected_pairs - expected_pairs
    denominator = len(expected_pairs)
    return {
        "seeded_defects": denominator,
        "detected_defects": len(detected),
        "missed_defects": len(missed),
        "false_positive_exceptions": len(unseeded),
        "recall": (len(detected) / denominator) if denominator else 1.0,
        "recall_denominator": "distinct seeded (client_id, rule_id) validation defects",
        "missed": sorted(f"{client}:{rule}" for client, rule in missed),
        "unseeded_detected": sorted(f"{client}:{rule}" for client, rule in unseeded),
    }
