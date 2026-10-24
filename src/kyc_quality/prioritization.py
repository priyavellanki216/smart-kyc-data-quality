from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .config import load_rules


def _as_date(value: Any) -> date | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def calculate_priority_scores(
    exceptions: pd.DataFrame,
    duplicate_candidates: pd.DataFrame | None = None,
    cases: pd.DataFrame | None = None,
    rules: dict[str, Any] | None = None,
    now: date | datetime | None = None,
) -> pd.DataFrame:
    """Score clients for work sequencing; the score is not a probability or risk estimate."""
    config = rules or load_rules()
    today = now.date() if isinstance(now, datetime) else (now or date.today())
    weights = config["priority"]["weights"]
    age_cfg = config["priority"]["age_days"]
    bands = config["priority"]["bands"]
    duplicates = duplicate_candidates if duplicate_candidates is not None else pd.DataFrame(columns=["client_id_1", "client_id_2"])
    case_df = cases if cases is not None else pd.DataFrame(columns=["client_id", "opened_at"])
    exception_df = exceptions if exceptions is not None else pd.DataFrame(columns=["client_id", "rule_id", "severity", "category"])
    client_ids = set(exception_df.get("client_id", pd.Series(dtype=str)).astype(str))
    client_ids.update(duplicates.get("client_id_1", pd.Series(dtype=str)).astype(str))
    client_ids.update(duplicates.get("client_id_2", pd.Series(dtype=str)).astype(str))
    opened_by_client = {str(row.client_id): row.opened_at for row in case_df.itertuples() if hasattr(row, "opened_at")}
    duplicate_ids: set[str] = set()
    if not duplicates.empty:
        duplicate_ids.update(duplicates["client_id_1"].astype(str))
        duplicate_ids.update(duplicates["client_id_2"].astype(str))

    output: list[dict[str, Any]] = []
    for client_id in sorted(client_ids):
        client_exceptions = exception_df.loc[exception_df.get("client_id", pd.Series(dtype=str)).astype(str) == client_id] if not exception_df.empty else exception_df
        points = 0
        contributions: list[str] = []
        rules_seen = set(client_exceptions.get("rule_id", pd.Series(dtype=str)).astype(str))
        if rules_seen.intersection({"REQ-001", "BO-001", "DOC-001"}):
            points += int(weights["mandatory_missing"])
            contributions.append(f"mandatory information +{weights['mandatory_missing']}")
        if "DOC-002" in rules_seen:
            points += int(weights["expired_document"])
            contributions.append(f"expired document +{weights['expired_document']}")
        if "ATTR-001" in rules_seen:
            points += int(weights["conflicting_attributes"])
            contributions.append(f"conflicting attributes +{weights['conflicting_attributes']}")
        if client_id in duplicate_ids:
            points += int(weights["duplicate_candidate"])
            contributions.append(f"potential duplicate +{weights['duplicate_candidate']}")
        if not client_exceptions.empty:
            severity = set(client_exceptions["severity"].astype(str).str.lower())
            for level in ("critical", "high", "medium", "low"):
                if level in severity:
                    key = f"severity_{level}"
                    points += int(weights[key])
                    contributions.append(f"{level} exception +{weights[key]}")
                    break
        opened = _as_date(opened_by_client.get(client_id))
        age_days = max((today - opened).days, 0) if opened else 0
        if age_days >= int(age_cfg["second_threshold"]):
            points += int(weights["age_14_days"]) + int(weights["age_30_days"])
            contributions.extend([f"case age ≥14 days +{weights['age_14_days']}", f"case age ≥30 days +{weights['age_30_days']}"])
        elif age_days >= int(age_cfg["first_threshold"]):
            points += int(weights["age_14_days"])
            contributions.append(f"case age ≥14 days +{weights['age_14_days']}")
        score = min(points, int(config["priority"]["max_score"]))
        if score >= int(bands["critical"]):
            band = "Critical"
        elif score >= int(bands["high"]):
            band = "High"
        elif score >= int(bands["medium"]):
            band = "Medium"
        else:
            band = "Low"
        output.append({
            "client_id": client_id,
            "priority_score": score,
            "priority_band": band,
            "case_age_days": age_days,
            "priority_explanation": "; ".join(contributions) if contributions else "No configured priority contributions.",
            "score_type": "rule-based work-priority score; not a probability",
        })
    return pd.DataFrame(output, columns=["client_id", "priority_score", "priority_band", "case_age_days", "priority_explanation", "score_type"])
