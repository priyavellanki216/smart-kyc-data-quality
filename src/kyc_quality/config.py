from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    """Load business-rule configuration, rejecting malformed or incomplete files."""
    config_path = Path(path) if path is not None else project_root() / "config" / "rules.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Business-rules file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in business-rules file: {config_path}") from exc

    required = {"mandatory_client_fields", "registration_number_pattern", "duplicate_threshold", "priority", "rules"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Business-rules configuration is missing keys: {sorted(missing)}")
    threshold = int(config["duplicate_threshold"])
    if not 0 <= threshold <= 100:
        raise ValueError("duplicate_threshold must be between 0 and 100")
    if not isinstance(config["rules"], dict) or not config["rules"]:
        raise ValueError("rules must be a non-empty object")
    return config


def rule_details(rule_id: str, rules: dict[str, Any] | None = None) -> dict[str, str]:
    config = rules or load_rules()
    try:
        return config["rules"][rule_id]
    except KeyError as exc:
        raise KeyError(f"No business-rule definition found for {rule_id}") from exc
