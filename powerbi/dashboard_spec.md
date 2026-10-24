# Power BI-compatible model and dashboard specification

This repository exports Power BI-compatible CSV fact/dimension tables; it does **not** contain a native `.pbix` or claim an integrated Power BI Desktop dashboard. Power BI Desktop is not available in the Linux build environment. The included data and DAX are the delivered artifacts; the steps below remain manual in Desktop.

## Source tables

Import `dim_client.csv`, `dim_rule.csv`, `fact_exceptions.csv`, `fact_review_cases.csv`, `fact_review_actions.csv`, and `fact_duplicate_candidates.csv` from the export folder. `dim_client` contains one row per client plus derived current completeness/owner/document/open-exception fields. `dim_rule` contains one row per rule. `fact_review_cases` is one row per case. `fact_review_actions` is one row per saved case action. `fact_duplicate_candidates` is one row per candidate pair and retains both client IDs.

## Relationships

- `dim_client[client_id]` 1:* `fact_exceptions[client_id]`.
- `dim_rule[rule_id]` 1:* `fact_exceptions[rule_id]`.
- `dim_client[client_id]` 1:* `fact_review_cases[client_id]`.
- `fact_review_cases[case_id]` 1:* `fact_review_actions[case_id]`.
- `dim_client[client_id]` 1:* `fact_duplicate_candidates[client_id_1]` (active). For analysis by `client_id_2`, create a second/inactive relationship or a role-playing client dimension. Avoid bidirectional ambiguous filter paths.

## Suggested pages

**Operations overview:** KPI cards for clients, complete KYC files, incomplete files, open exceptions, open review cases, overdue periodic reviews, and open candidate pairs; bar chart of open exceptions by category/severity; queue by priority band/status.

**Review queue:** case table sorted by score and age with status, assigned reviewer, score explanation and client. Score is a configured work-ordering score, not probability or calibrated risk.

**Data quality:** completeness by country/jurisdiction; exception count by rule/category/severity; filters for exception status. Candidate pairs shown separately as unconfirmed investigations.

**Review operations:** open/closed cases, age distribution, reviewer workload, review outcomes and recent actions; do not expose free-text remediation notes on broad shared reports without appropriate access controls.

## Manual Desktop steps

1. Import the six CSVs from the export directory. Preserve identifier columns as Text.
2. Create relationships above; use single-direction filtering.
3. Add measures from `measures.dax` and verify card totals against the SQLite-generated CSVs.
4. Add report pages and visuals using the suggested layout; label candidates as candidates.
5. Save a `.pbix` in a controlled desktop environment if required. That file is not produced or checked in by this repository.

Do not use the sample dashboard to make regulated KYC acceptance, rejection, suspicious-activity or financial-crime determinations.
