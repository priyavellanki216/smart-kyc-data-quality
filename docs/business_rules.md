# Business rules and evaluation

## Configurable controls

`config/rules.json` is the source for mandatory client fields, permitted date format, comma-delimited address component threshold, registration-number regex, RapidFuzz candidate threshold, priority weights/bands/age thresholds, and case transition map. Validation rule IDs/categories/severities/titles are also stored there. Source records are never silently repaired to pass a rule.

## Validation catalogue

| Rule | Category | Default severity | Behaviour |
|---|---|---:|---|
| `REQ-001` | completeness | high | Emits one exception for each blank mandatory client field. |
| `REG-001` | identity | high | Tests a populated registration number against the configured, case-insensitive pattern. |
| `INC-001` | dates | high | Flags invalid date format or an incorporation date after the run date. |
| `DATE-001` | dates | medium | Flags invalid onboarding/review-due date formats or a due date before onboarding. |
| `BO-001` | ownership | high | Flags a client with no beneficial-owner rows. |
| `BO-002` | ownership | high | Flags missing, non-positive, >100%, or aggregate ownership above 100%. |
| `DOC-001` | documentation | high | Flags a client with no supporting-document metadata. |
| `DOC-002` | documentation | high | Flags invalid or expired document expiry dates. |
| `ADDR-001` | address | medium | Flags populated registered addresses with fewer than the configured comma-delimited components. |
| `ATTR-001` | attributes | high | Flags unequal jurisdiction and client-country codes. |
| `REV-001` | review | medium | Flags a periodic-review due date earlier than the run date. |

Each exception includes a deterministic `EXC-` ID based on client, rule, and evidence field, plus rule ID, category, severity, readable reason, evidence, detection timestamp, and review status. It is stable across repeated evaluation of the same client/rule/field; detection timestamps are run-specific.

## Duplicate candidates

Exact matching removes non-alphanumeric separators from registration numbers and requires jurisdiction to match. Same numbers under different jurisdictions are not treated as an exact pair. Fuzzy matching normalizes Unicode-like punctuation/case/spacing and removes common legal suffix tokens, then uses RapidFuzz `max(fuzz.ratio, fuzz.token_sort_ratio)` against the configurable default threshold of 86. Results preserve identifier/jurisdiction/address differences as evidence. Candidate generation does not merge or confirm records; analysts manually choose `candidate`, `confirmed_duplicate`, or `false_positive` after investigation.

The known legitimate pair `SYN-0033` / `SYN-0034` intentionally receives a fuzzy candidate. It counts as a false-positive *candidate* in evaluation and stays unconfirmed in the initial seed. A generated candidate must not be reported as a confirmed duplicate.

## Review priority

For each client with an exception or candidate, the configured score adds (at most once per condition): missing-required-information 25; expired document 20; attribute conflict 15; potential duplicate 15; highest severity contribution critical 30/high 20/medium 10/low 5; open-case age 14+ days 10 and 30+ days an additional 10. The result caps at 100; default bands are medium ≥30, high ≥60, critical ≥80 (otherwise low). Contributions are rendered as strings in queue data. This is only a review-ordering score and is not a calibrated probability or a financial-crime/client risk estimate.

## Case workflow and audit

Cases use the explicit transition map in `config/rules.json`. Resolved and closed are terminal. Reject invalid transitions before writes. Review notes/assignment/status and exception/duplicate dispositions append actor, previous/new value, note, and UTC timestamp to `audit_history` in the same transaction as the state change. SQLite triggers reject ordinary `UPDATE` and `DELETE` on audit rows. Filesystem/database-owner tampering is outside this local prototype's threat model.

## Seed evaluation

Validation recall denominator: distinct seeded `(client_id, rule_id)` validation defects, not raw rows or exception count. A detected pair matches the same client and rule. False-positive exception count is a detected client-rule pair not in seeded validation truth. Duplicate evaluation denominator: two seeded true client pairs, exact and fuzzy. Candidate precision counts only candidate pairs matching those seeded true pairs; a legitimate lookalike is a false-positive candidate, never a confirmed duplicate. All values are computed by `validation.evaluate_seeded_defects` and `duplicates.evaluate_duplicate_candidates`.
