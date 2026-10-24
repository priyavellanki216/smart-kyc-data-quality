"""Metrics for seeded synthetic defects; values are computed, never hand-entered."""

from .duplicates import evaluate_duplicate_candidates
from .validation import evaluate_seeded_defects

__all__ = ["evaluate_seeded_defects", "evaluate_duplicate_candidates"]
