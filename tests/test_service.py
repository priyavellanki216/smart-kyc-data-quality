from datetime import date

from kyc_quality.database import read_table
from kyc_quality.service import run_demo_pipeline


def test_pipeline_persists_reproducible_demo_and_measured_evaluation(tmp_path):
    path = tmp_path / "pipeline.db"
    result = run_demo_pipeline(path, as_of=date(2026, 10, 24))
    assert result["summary"]["total_clients"] == 40
    assert result["validation_evaluation"]["detected_defects"] == 9
    assert result["validation_evaluation"]["missed_defects"] == 0
    assert result["validation_evaluation"]["recall"] == 1.0
    assert result["duplicate_evaluation"]["seeded_pairs_candidate_generated"] == 2
    assert result["duplicate_evaluation"]["false_positive_candidates"] == 1
    assert read_table(path, "clients")["synthetic"].eq(1).all()
