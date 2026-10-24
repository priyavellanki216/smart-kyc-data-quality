-- Pending cases prioritized by a transparent rule-based score (not a probability).
SELECT rc.case_id, c.client_id, c.legal_name, rc.status, rc.priority_score,
       rc.priority_band, rc.priority_explanation, rc.assigned_reviewer,
       rc.opened_at, CAST(julianday('now') - julianday(rc.opened_at) AS INTEGER) AS age_days
FROM review_cases rc JOIN clients c USING (client_id)
WHERE rc.status NOT IN ('resolved', 'closed')
ORDER BY rc.priority_score DESC, rc.opened_at ASC;

-- Open exceptions by category and severity.
SELECT category, severity, COUNT(*) AS exception_count
FROM validation_exceptions WHERE status = 'open'
GROUP BY category, severity ORDER BY severity, category;

-- Overdue periodic reviews; ISO date strings sort lexicographically.
SELECT client_id, legal_name, periodic_review_due
FROM clients WHERE periodic_review_due <> '' AND periodic_review_due < date('now')
ORDER BY periodic_review_due;

-- Client completeness and remediation counts.
SELECT client_id, legal_name, required_fields_complete, kyc_complete,
       beneficial_owner_count, document_count, open_exception_count
FROM client_completeness ORDER BY open_exception_count DESC, legal_name;

-- Potential duplicate candidates; candidates are not confirmed matches.
SELECT dc.candidate_id, a.legal_name AS client_a, b.legal_name AS client_b,
       dc.match_method, dc.similarity_score, dc.matching_fields, dc.differing_fields,
       dc.status, dc.explanation
FROM duplicate_candidates dc
JOIN clients a ON a.client_id = dc.client_id_1
JOIN clients b ON b.client_id = dc.client_id_2
WHERE dc.status = 'candidate'
ORDER BY dc.similarity_score DESC;

-- Reviewer workload by open case status.
SELECT COALESCE(assigned_reviewer, 'Unassigned') AS reviewer, status, COUNT(*) AS case_count
FROM review_cases WHERE status NOT IN ('resolved', 'closed')
GROUP BY COALESCE(assigned_reviewer, 'Unassigned'), status
ORDER BY reviewer, status;

-- Remediation outcomes and recorded actions.
SELECT action_type, previous_status, new_status, COUNT(*) AS action_count
FROM review_actions GROUP BY action_type, previous_status, new_status
ORDER BY action_type, previous_status, new_status;

-- Case aging distribution.
SELECT case_id, client_id, status, priority_band, priority_score,
       CAST(julianday('now') - julianday(opened_at) AS INTEGER) AS age_days
FROM review_cases ORDER BY age_days DESC;
