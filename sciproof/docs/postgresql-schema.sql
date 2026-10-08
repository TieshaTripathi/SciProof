-- Current model DDL at Alembic head 0004. Reference only; apply migrations for schema changes.

CREATE TABLE users (
	email VARCHAR(254) NOT NULL, 
	password_hash TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE auth_sessions (
	user_id UUID NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (token_hash)
);

CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE research_projects (
	owner_id UUID NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_research_projects_owner_id ON research_projects (owner_id);

CREATE TABLE research_versions (
	project_id UUID NOT NULL, 
	version_number INTEGER NOT NULL, 
	state VARCHAR(6) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (project_id, version_number), 
	CHECK (version_number > 0), 
	FOREIGN KEY(project_id) REFERENCES research_projects (id), 
	CONSTRAINT versionstate CHECK (state IN ('DRAFT', 'SEALED'))
);

CREATE INDEX ix_research_versions_project_id ON research_versions (project_id);

CREATE TABLE research_artifacts (
	research_version_id UUID NOT NULL, 
	artifact_type VARCHAR(13) NOT NULL, 
	visibility VARCHAR(10) NOT NULL, 
	filename VARCHAR(200) NOT NULL, 
	sanitized_filename VARCHAR(200) NOT NULL, 
	mime_type VARCHAR(100) NOT NULL, 
	size INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	storage_backend VARCHAR(50) NOT NULL, 
	storage_reference VARCHAR(500) NOT NULL, 
	encryption_status VARCHAR(30) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (research_version_id, artifact_type), 
	CHECK (size > 0), 
	CHECK (length(sha256) = 64), 
	FOREIGN KEY(research_version_id) REFERENCES research_versions (id), 
	CONSTRAINT artifacttype CHECK (artifact_type IN ('MANUSCRIPT', 'DATASET', 'ANALYSIS_CODE', 'SUPPLEMENTARY', 'REPORT')), 
	CONSTRAINT visibility CHECK (visibility IN ('PUBLIC', 'PRIVATE', 'RESTRICTED')), 
	UNIQUE (storage_reference)
);

CREATE INDEX ix_research_artifacts_sha256 ON research_artifacts (sha256);

CREATE INDEX ix_research_artifacts_research_version_id ON research_artifacts (research_version_id);

CREATE TABLE verification_runs (
	research_version_id UUID NOT NULL, 
	job_status VARCHAR(9) NOT NULL, 
	verification_status VARCHAR(22), 
	engine_version VARCHAR(50) NOT NULL, 
	ruleset_version VARCHAR(50) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(100), 
	attempts INTEGER NOT NULL, 
	ai_metadata JSON NOT NULL, 
	scientific_report JSON, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (research_version_id), 
	FOREIGN KEY(research_version_id) REFERENCES research_versions (id), 
	CONSTRAINT runstate CHECK (job_status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')), 
	CONSTRAINT verificationstatus CHECK (verification_status IN ('VERIFIED', 'VERIFIED_WITH_WARNINGS', 'NEEDS_REVIEW', 'FAILED_VERIFICATION', 'INSUFFICIENT_EVIDENCE'))
);

CREATE INDEX ix_verification_runs_job_status ON verification_runs (job_status);

CREATE TABLE manuscripts (
	artifact_id UUID NOT NULL, 
	page_count INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (artifact_id), 
	FOREIGN KEY(artifact_id) REFERENCES research_artifacts (id)
);

CREATE TABLE datasets (
	artifact_id UUID NOT NULL, 
	profile JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (artifact_id), 
	FOREIGN KEY(artifact_id) REFERENCES research_artifacts (id)
);

CREATE TABLE analysis_code (
	artifact_id UUID NOT NULL, 
	execution_enabled BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (execution_enabled = false), 
	UNIQUE (artifact_id), 
	FOREIGN KEY(artifact_id) REFERENCES research_artifacts (id)
);

CREATE TABLE claims (
	research_version_id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	claim_text TEXT NOT NULL, 
	metric VARCHAR(100) NOT NULL, 
	reported_value FLOAT NOT NULL, 
	tolerance FLOAT NOT NULL, 
	source_page INTEGER NOT NULL, 
	confidence FLOAT NOT NULL, 
	input_fields JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (confidence >= 0 AND confidence <= 1), 
	CHECK (tolerance >= 0), 
	CHECK (source_page > 0), 
	FOREIGN KEY(research_version_id) REFERENCES research_versions (id), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id)
);

CREATE INDEX ix_claims_run_id ON claims (run_id);

CREATE INDEX ix_claims_research_version_id ON claims (research_version_id);

CREATE TABLE evidence (
	run_id UUID NOT NULL, 
	artifact_id UUID NOT NULL, 
	dataset_columns JSON NOT NULL, 
	calculated_value FLOAT, 
	method VARCHAR(200) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id), 
	FOREIGN KEY(artifact_id) REFERENCES research_artifacts (id)
);

CREATE INDEX ix_evidence_run_id ON evidence (run_id);

CREATE INDEX ix_evidence_artifact_id ON evidence (artifact_id);

CREATE TABLE verification_findings (
	run_id UUID NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	message TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id)
);

CREATE INDEX ix_verification_findings_run_id ON verification_findings (run_id);

CREATE TABLE verification_scores (
	run_id UUID NOT NULL, 
	dimension VARCHAR(100) NOT NULL, 
	value FLOAT NOT NULL, 
	weight FLOAT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (run_id, dimension), 
	CHECK (value >= 0 AND value <= 100), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id)
);

CREATE INDEX ix_verification_scores_run_id ON verification_scores (run_id);

CREATE TABLE provenance_records (
	run_id UUID NOT NULL, 
	research_version_id UUID NOT NULL, 
	manifest JSON NOT NULL, 
	provenance_hash VARCHAR(64) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (run_id), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id), 
	UNIQUE (research_version_id), 
	FOREIGN KEY(research_version_id) REFERENCES research_versions (id)
);

CREATE INDEX ix_provenance_records_provenance_hash ON provenance_records (provenance_hash);

CREATE TABLE artifact_publications (
	artifact_id UUID NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	provider VARCHAR(50), 
	cid VARCHAR(120), 
	artifact_hash VARCHAR(64) NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(100), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (status IN ('NOT_PUBLISHED','PUBLISHING','PUBLISHED','FAILED')), 
	UNIQUE (artifact_id), 
	FOREIGN KEY(artifact_id) REFERENCES research_artifacts (id)
);

CREATE TABLE claim_evidence_links (
	claim_id UUID NOT NULL, 
	evidence_id UUID NOT NULL, 
	outcome VARCHAR(19) NOT NULL, 
	explanation TEXT NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (claim_id, evidence_id), 
	FOREIGN KEY(claim_id) REFERENCES claims (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id), 
	CONSTRAINT outcome CHECK (outcome IN ('SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'UNVERIFIABLE', 'CONFLICTING'))
);

CREATE INDEX ix_claim_evidence_links_claim_id ON claim_evidence_links (claim_id);

CREATE INDEX ix_claim_evidence_links_evidence_id ON claim_evidence_links (evidence_id);

CREATE TABLE verification_checks (
	run_id UUID NOT NULL, 
	claim_id UUID NOT NULL, 
	evidence_id UUID NOT NULL, 
	check_type VARCHAR(100) NOT NULL, 
	method VARCHAR(200) NOT NULL, 
	reported_value FLOAT NOT NULL, 
	calculated_value FLOAT, 
	tolerance FLOAT NOT NULL, 
	outcome VARCHAR(19) NOT NULL, 
	explanation TEXT NOT NULL, 
	software_versions JSON NOT NULL, 
	absolute_difference FLOAT, 
	relative_difference FLOAT, 
	relative_tolerance FLOAT, 
	comparison_method VARCHAR(100), 
	rule_version VARCHAR(50), 
	rule_context JSON, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES verification_runs (id), 
	UNIQUE (claim_id), 
	FOREIGN KEY(claim_id) REFERENCES claims (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id), 
	CONSTRAINT outcome CHECK (outcome IN ('SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'UNVERIFIABLE', 'CONFLICTING'))
);

CREATE INDEX ix_verification_checks_run_id ON verification_checks (run_id);

CREATE TABLE blockchain_attestations (
	provenance_id UUID NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	chain_id INTEGER, 
	transaction_hash VARCHAR(100), 
	contract_address VARCHAR(42), 
	signer_address VARCHAR(42), 
	researcher_address VARCHAR(42), 
	provenance_hash VARCHAR(64), 
	block_number INTEGER, 
	block_hash VARCHAR(66), 
	confirmations_required INTEGER, 
	attested_at TIMESTAMP WITH TIME ZONE, 
	nonce INTEGER, 
	signed_transaction TEXT, 
	error_code VARCHAR(100), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT attestation_state CHECK (status IN ('NOT_REQUESTED','PENDING','SUBMITTED','CONFIRMED','FAILED')), 
	UNIQUE (provenance_id), 
	FOREIGN KEY(provenance_id) REFERENCES provenance_records (id)
);
