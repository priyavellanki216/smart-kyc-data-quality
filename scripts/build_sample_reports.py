from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

from kyc_quality.database import read_table, record_review_action
from kyc_quality.reporting import export_reports, summary_metrics
from kyc_quality.service import run_demo_pipeline


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "reports" / "sample"


def main() -> None:
    reference_date = date(2026, 10, 24)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smart-kyc-sample-") as temporary:
        db_path = Path(temporary) / "sample.db"
        result = run_demo_pipeline(db_path, n_clients=40, seed=2026, as_of=reference_date)
        sample_case = read_table(db_path, "review_cases", "client_id = ?", ("SYN-0002",)).iloc[0]
        record_review_action(
            db_path,
            sample_case["case_id"],
            new_status="in_review",
            reviewer="Demo Analyst",
            note="Synthetic sample action: requested a corrected legal-name record; follow-up remains open.",
            action_type="evidence_requested",
        )
        exports = export_reports(db_path, OUTPUT_DIR)
        evidence = {
            "dataset": {"synthetic": True, "clients": 40, "seed": 2026, "as_of": reference_date.isoformat()},
            "validation_evaluation": result["validation_evaluation"],
            "duplicate_evaluation": result["duplicate_evaluation"],
            "portfolio_summary": summary_metrics(db_path, as_of=reference_date),
            "sample_review_action": {"case_id": sample_case["case_id"], "client_id": "SYN-0002", "status": "in_review", "reviewer": "Demo Analyst"},
            "report_files": sorted(path.name for path in exports.values()),
        }
        (OUTPUT_DIR / "detection_evaluation.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built {len(exports)} synthetic CSV/XLSX outputs and detection_evaluation.json in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
