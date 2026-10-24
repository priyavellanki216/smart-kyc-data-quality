from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database import DEFAULT_DB_PATH, init_db
from .reporting import export_reports
from .service import run_demo_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic Smart KYC data-quality prototype")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path (default: data/kyc_demo.db)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create the SQLite schema and reporting views")
    run = sub.add_parser("run-demo", help="Generate synthetic records, validate, match, score, and persist sample cases")
    run.add_argument("--clients", type=int, default=40)
    run.add_argument("--seed", type=int, default=2026)
    validate = sub.add_parser("validate", help="Run the synthetic validation and print measured defect metrics")
    validate.add_argument("--clients", type=int, default=40)
    validate.add_argument("--seed", type=int, default=2026)
    dup = sub.add_parser("detect-duplicates", help="Run exact and RapidFuzz candidate detection on synthetic data")
    dup.add_argument("--clients", type=int, default=40)
    dup.add_argument("--seed", type=int, default=2026)
    export = sub.add_parser("export", help="Export current database reporting tables to CSV and XLSX")
    export.add_argument("--output", type=Path, default=Path("reports/generated"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "init-db":
        print(f"Initialized SQLite schema at {init_db(args.database)}")
        return
    if args.command in {"run-demo", "validate", "detect-duplicates"}:
        result = run_demo_pipeline(args.database, n_clients=args.clients, seed=args.seed)
        if args.command == "validate":
            print(json.dumps({"validation_evaluation": result["validation_evaluation"], "exceptions": len(result["exceptions"])}, indent=2))
        elif args.command == "detect-duplicates":
            print(json.dumps({"duplicate_evaluation": result["duplicate_evaluation"], "candidate_count": len(result["duplicate_candidates"])}, indent=2))
        else:
            print(json.dumps({
                "database": result["database_path"],
                "summary": result["summary"],
                "validation_evaluation": result["validation_evaluation"],
                "duplicate_evaluation": result["duplicate_evaluation"],
            }, indent=2, default=str))
        return
    if args.command == "export":
        exported = export_reports(args.database, args.output)
        print(json.dumps({name: str(path) for name, path in exported.items()}, indent=2))


if __name__ == "__main__":
    main()
