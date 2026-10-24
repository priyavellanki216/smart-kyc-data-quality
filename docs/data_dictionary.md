# Data dictionary

All packaged example values are synthetic. Date columns use ISO `YYYY-MM-DD`; application timestamps are UTC ISO 8601 strings.

## Source and operational entities

| Table | Key fields | Description |
|---|---|---|
| `clients` | `client_id` PK; `legal_name`; `registration_number`; `jurisdiction`; `registered_address`; `country`; `incorporation_date`; `onboarding_date`; `periodic_review_due`; `review_status`; `synthetic` | Corporate client source record. In this prototype `synthetic=1` for every generated row. |
| `beneficial_owners` | `owner_id` PK; `client_id` FK; `owner_name`; `ownership_percent`; `identity_reference` | Generated ownership metadata; percentage constraint 0–100 and rule checks for positive/aggregate values. |
| `documents` | `document_id` PK; `client_id` FK; `document_type`; `issue_date`; `expiry_date`; `document_reference` | Synthetic document metadata only; no document file is stored. |
| `validation_exceptions` | `exception_id` PK; `client_id` FK; `rule_id`; `category`; `severity`; `reason`; `evidence`; `detected_at`; `status` | Stable rule finding and review disposition. Status: open, in_review, resolved, false_positive. |
| `duplicate_candidates` | `candidate_id` PK; `client_id_1`/`client_id_2` FKs; `match_method`; `similarity_score`; `matching_fields`; `differing_fields`; `explanation`; `status` | Investigation candidate, not confirmed identity. Status: candidate, confirmed_duplicate, false_positive. |
| `review_cases` | `case_id` PK; unique `client_id` FK; `priority_score`; `priority_band`; `priority_explanation`; `status`; `assigned_reviewer`; `opened_at`; `updated_at` | Persistent review work item; score is a rule-based priority, not probability. |
| `review_actions` | `action_id` PK; `case_id` FK; `action_type`; `reviewer`; `note`; `previous_status`; `new_status`; `created_at` | Persisted analyst action history for a case. |
| `audit_history` | `audit_id` PK; `entity_type`; `entity_id`; `action`; `actor`; `previous_value`; `new_value`; `notes`; `timestamp` | Append-only application event log protected by SQLite update/delete triggers. |

## Derived/reporting fields

`client_completeness` view exposes `required_fields_complete`, `kyc_complete`, beneficial-owner/document counts, and open-exception count. `kyc_complete` requires all mandatory fields, at least one owner and document, no open validation exceptions, and no unresolved duplicate candidate. `client_quality_summary.csv` adds total detected exception count, categories, and a Complete/Needs review label.

`review_queue.csv` includes case/client identifiers, status, priority score/band/explanation, assigned analyst, age in days, open exception categories and count. `case_aging.csv` is its case-aging projection. `reviewer_workload.csv` groups persisted cases by assigned reviewer and status.

Power BI tables: `dim_client` (one current-state row per client); `dim_rule` (rule ID/category/severity/title); `fact_exceptions`; `fact_review_cases`; `fact_review_actions`; `fact_duplicate_candidates`. Duplicate candidate facts have two client roles (`client_id_1`, `client_id_2`). See `powerbi/dashboard_spec.md` for relationships and measures.
