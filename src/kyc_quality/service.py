from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .database import DEFAULT_DB_PATH, read_table, seed_database
from .duplicates import detect_duplicate_candidates, evaluate_duplicate_candidates
from .prioritization import calculate_priority_scores
from .reporting import summary_metrics
from .synthetic_data import generate_synthetic_dataset
from .validation import evaluate_seeded_defects, validate_clients


def run_demo_pipeline(
    database_path: str | Path = DEFAULT_DB_PATH,
    n_clients: int = 40,
    seed: int = 2026,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Generate/reconcile deterministic synthetic inputs without deleting analyst actions."""
    dataset = generate_synthetic_dataset(n_clients=n_clients, seed=seed)
    reference_date = as_of or date.today()
    exceptions = validate_clients(
        dataset["clients"], dataset["beneficial_owners"], dataset["documents"], now=reference_date
    )
    candidates = detect_duplicate_candidates(dataset["clients"])
    existing_cases = read_table(database_path, "review_cases") if Path(database_path).exists() else pd.DataFrame()
    scores = calculate_priority_scores(exceptions, candidates, cases=existing_cases, now=reference_date)
    seed_database(database_path, dataset, exceptions, candidates, scores)
    return {
        "dataset": dataset,
        "exceptions": exceptions,
        "duplicate_candidates": candidates,
        "priority_scores": scores,
        "validation_evaluation": evaluate_seeded_defects(dataset["seeded_defects"], exceptions),
        "duplicate_evaluation": evaluate_duplicate_candidates(dataset["seeded_defects"], candidates),
        "summary": summary_metrics(database_path, as_of=reference_date),
        "database_path": str(database_path),
        "as_of": reference_date.isoformat(),
    }
