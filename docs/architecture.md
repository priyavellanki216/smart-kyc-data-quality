# System architecture

## Runtime components

`synthetic_data.py` creates deterministic synthetic tables and explicit fixture truth labels. `validation.py` evaluates client, owner, and document records without mutating input data. `duplicates.py` applies jurisdiction-scoped exact identifier matching and RapidFuzz name candidate generation. `prioritization.py` calculates a configurable work-ordering score with visible component explanations. `service.py` orchestrates those functions and idempotently loads source and derived findings into SQLite.

`database.py` owns connection settings, schema initialization, query helpers, transaction boundaries, review action persistence, exception/duplicate dispositions, and audit writes. `schema.sql` defines constraints, indexes, the completeness view, and audit no-update/no-delete triggers. `reporting.py` reads persisted database state to build CSV/XLSX and Power BI-compatible fact/dimension tables. `cli.py` exposes initialization, demo, validation, duplicate, and export commands. `app/streamlit_app.py` is the user interface and calls the same service/database/report modules as the CLI.

## Data flow

1. Generate 40 clients by default using seed `2026`, their sample owners/documents, and seeded known-defect truth labels.
2. Validate all generated source records and attach stable rule/client/field-based exception identifiers.
3. Build exact and fuzzy duplicate investigation candidates; do not modify or combine client rows.
4. Calculate queue priority and explanation from configured factors and (when present) persisted case age.
5. Insert source rows/findings/cases idempotently into SQLite. Existing case status and reviewer actions remain intact on app restart.
6. Analysts record review notes, assignments, status transitions, exception dispositions, and duplicate decisions. Review-action and audit rows are written transactionally.
7. Reports and exports query SQLite; they describe current data, not a separately fabricated dashboard extract.

## Persistence and operational boundary

Default database: `data/kyc_demo.db`, ignored by Git. Set `KYC_DB_PATH` to use another location. A fresh database is created from `sql/schema.sql`; an existing database is not dropped or cleared by demo seeding. The application is intentionally local/single-user and has no login/permission enforcement. It is a portfolio prototype, not a production regulated workflow.

## Reporting model

Power Query consumes row-oriented CSV exports or the same worksheets in the XLSX workbook. Power BI can import `dim_client`, `dim_rule`, `fact_exceptions`, `fact_review_cases`, `fact_review_actions`, and `fact_duplicate_candidates`. `client_id` is the client key; `rule_id` joins exceptions to the rule dimension; case actions join through `case_id`. Duplicate candidates contain two client roles; create a second/inactive role-playing relationship for `client_id_2` when needed.
