# Excel reconciliation workbook and Power Query setup

## Workbook

Run the demo and export commands in the repository README. The workbook `reports/generated/smart_kyc_reconciliation.xlsx` includes filtered/structured tables for clients, KYC quality summary, exceptions, duplicate candidates, review queue, case aging, reviewer workload, audit history, and Power BI fact/dimension data. Header filters and freeze panes are set in the generator; output is derived from SQLite at export time.

## Power Query from a folder of CSV exports

1. Run `python -m kyc_quality.cli --database data/kyc_demo.db export --output reports/generated`.
2. In Excel, choose **Data → Get Data → From File → From Folder** and select the `reports/generated` folder. Choose **Combine & Transform** or load specific files individually.
3. Keep one query per required table: `clients`, `client_quality_summary`, `exceptions`, `duplicate_candidates`, `review_queue`, `case_aging`, `reviewer_workload`, `audit_history`, `dim_client`, `dim_rule`, and fact tables.
4. In Power Query, set identifiers and rule/status/category fields to Text; ownership percentages and priority/similarity scores to Decimal Number; case counts and ages to Whole Number; date-only fields to Date; timestamp fields to Date/Time/Timezone where supported.
5. Preserve client/case/exception/candidate IDs as text to avoid formatting changes. Do not merge duplicate candidate pairs into one client row.
6. Load the queries to an Excel data model. Create relationships on `client_id` for client facts, `rule_id` for exception facts, and `case_id` for review action facts. Keep both client roles in duplicate candidates; use separate role-playing client tables if both directions are needed.
7. Reconcile portfolio counts to `client_quality_summary`: total client rows; complete vs needs-review clients; open exception counts by category/severity; open case counts/status; and candidate status counts. Candidate counts are not confirmed duplicate counts.
8. Use **Refresh All** after regenerating CSVs. To change the path, edit the Folder Source step and ensure the same export directory contains the current file set.

## Power Query date-safe transformation sample

For an ISO date column such as `periodic_review_due`, use a culture-invariant transform:

```powerquery
Table.TransformColumnTypes(Source, {{"periodic_review_due", type date}}, "en-US")
```

If a custom locale is required, parse explicitly with `Date.FromText([periodic_review_due], [Format="yyyy-MM-dd", Culture="en-US"])`. Treat blank strings as null before converting. The workbook is a reporting/reconciliation artifact; it does not add KYC policy decisions or replace the source system.
