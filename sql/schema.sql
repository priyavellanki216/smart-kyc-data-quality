PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL DEFAULT '',
    registration_number TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    registered_address TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    incorporation_date TEXT NOT NULL DEFAULT '',
    onboarding_date TEXT NOT NULL DEFAULT '',
    periodic_review_due TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'onboarding',
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS beneficial_owners (
    owner_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    owner_name TEXT NOT NULL,
    ownership_percent REAL NOT NULL CHECK (ownership_percent >= 0 AND ownership_percent <= 100),
    identity_reference TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_owners_client ON beneficial_owners(client_id);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    issue_date TEXT NOT NULL DEFAULT '',
    expiry_date TEXT NOT NULL DEFAULT '',
    document_reference TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documents_client_expiry ON documents(client_id, expiry_date);

CREATE TABLE IF NOT EXISTS validation_exceptions (
    exception_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    detected_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'resolved', 'false_positive'))
);
CREATE INDEX IF NOT EXISTS idx_exceptions_client_status ON validation_exceptions(client_id, status);
CREATE INDEX IF NOT EXISTS idx_exceptions_category_severity ON validation_exceptions(category, severity, status);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    candidate_id TEXT PRIMARY KEY,
    client_id_1 TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    client_id_2 TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    match_method TEXT NOT NULL CHECK (match_method IN ('exact_identifier', 'fuzzy_name')),
    similarity_score REAL NOT NULL CHECK (similarity_score >= 0 AND similarity_score <= 100),
    matching_fields TEXT NOT NULL,
    differing_fields TEXT NOT NULL,
    explanation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'confirmed_duplicate', 'false_positive')),
    CHECK (client_id_1 < client_id_2)
);
CREATE INDEX IF NOT EXISTS idx_duplicate_status_score ON duplicate_candidates(status, similarity_score DESC);

CREATE TABLE IF NOT EXISTS review_cases (
    case_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL UNIQUE REFERENCES clients(client_id) ON DELETE CASCADE,
    priority_score INTEGER NOT NULL CHECK (priority_score BETWEEN 0 AND 100),
    priority_band TEXT NOT NULL CHECK (priority_band IN ('Low', 'Medium', 'High', 'Critical')),
    priority_explanation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'awaiting_information', 'resolved', 'closed')),
    assigned_reviewer TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_queue_status_priority ON review_cases(status, priority_score DESC, opened_at ASC);
CREATE INDEX IF NOT EXISTS idx_review_assignee_status ON review_cases(assigned_reviewer, status);

CREATE TABLE IF NOT EXISTS review_actions (
    action_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES review_cases(case_id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_actions_case_time ON review_actions(case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_history (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    previous_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity_time ON audit_history(entity_type, entity_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_history(actor, timestamp DESC);

CREATE TRIGGER IF NOT EXISTS audit_history_no_update
BEFORE UPDATE ON audit_history
BEGIN
    SELECT RAISE(ABORT, 'audit_history is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_history_no_delete
BEFORE DELETE ON audit_history
BEGIN
    SELECT RAISE(ABORT, 'audit_history is append-only');
END;

CREATE VIEW IF NOT EXISTS client_completeness AS
SELECT c.client_id,
       c.legal_name,
       c.registration_number,
       c.country,
       c.jurisdiction,
       c.review_status,
       CASE WHEN TRIM(c.legal_name) <> '' AND TRIM(c.registration_number) <> '' AND TRIM(c.jurisdiction) <> ''
                 AND TRIM(c.registered_address) <> '' AND TRIM(c.country) <> ''
                 AND TRIM(c.incorporation_date) <> '' AND TRIM(c.onboarding_date) <> ''
                 AND TRIM(c.periodic_review_due) <> '' THEN 1 ELSE 0 END AS required_fields_complete,
       CASE WHEN TRIM(c.legal_name) <> '' AND TRIM(c.registration_number) <> '' AND TRIM(c.jurisdiction) <> ''
                 AND TRIM(c.registered_address) <> '' AND TRIM(c.country) <> ''
                 AND TRIM(c.incorporation_date) <> '' AND TRIM(c.onboarding_date) <> ''
                 AND TRIM(c.periodic_review_due) <> ''
                 AND (SELECT COUNT(*) FROM beneficial_owners o WHERE o.client_id = c.client_id) > 0
                 AND (SELECT COUNT(*) FROM documents d WHERE d.client_id = c.client_id) > 0
                 AND (SELECT COUNT(*) FROM validation_exceptions e WHERE e.client_id = c.client_id AND e.status = 'open') = 0
                 AND (SELECT COUNT(*) FROM duplicate_candidates dc WHERE (dc.client_id_1 = c.client_id OR dc.client_id_2 = c.client_id) AND dc.status = 'candidate') = 0
            THEN 1 ELSE 0 END AS kyc_complete,
       (SELECT COUNT(*) FROM beneficial_owners o WHERE o.client_id = c.client_id) AS beneficial_owner_count,
       (SELECT COUNT(*) FROM documents d WHERE d.client_id = c.client_id) AS document_count,
       (SELECT COUNT(*) FROM validation_exceptions e WHERE e.client_id = c.client_id AND e.status = 'open') AS open_exception_count
FROM clients c;
