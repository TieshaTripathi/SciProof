"""Normalized research domain. JSON is reserved for scientific metadata."""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (String, Text, Integer, Float, Boolean, DateTime, JSON,
                        ForeignKey, UniqueConstraint, CheckConstraint, Enum, Uuid)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
class Base(DeclarativeBase): pass
class Entity:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
class Visibility(str, enum.Enum):
    PUBLIC='PUBLIC'; PRIVATE='PRIVATE'; RESTRICTED='RESTRICTED'
class ArtifactType(str, enum.Enum):
    MANUSCRIPT='MANUSCRIPT'; DATASET='DATASET'; ANALYSIS_CODE='ANALYSIS_CODE'; SUPPLEMENTARY='SUPPLEMENTARY'; REPORT='REPORT'
class VersionState(str, enum.Enum):
    DRAFT='DRAFT'; SEALED='SEALED'
class RunState(str, enum.Enum):
    QUEUED='QUEUED'; RUNNING='RUNNING'; COMPLETED='COMPLETED'; FAILED='FAILED'
class Outcome(str, enum.Enum):
    SUPPORTED='SUPPORTED'; PARTIALLY_SUPPORTED='PARTIALLY_SUPPORTED'; UNSUPPORTED='UNSUPPORTED'; UNVERIFIABLE='UNVERIFIABLE'; CONFLICTING='CONFLICTING'
class VerificationStatus(str, enum.Enum):
    VERIFIED='VERIFIED'; VERIFIED_WITH_WARNINGS='VERIFIED_WITH_WARNINGS'; NEEDS_REVIEW='NEEDS_REVIEW'; FAILED_VERIFICATION='FAILED_VERIFICATION'; INSUFFICIENT_EVIDENCE='INSUFFICIENT_EVIDENCE'
def constrained(cls): return Enum(cls, native_enum=False, create_constraint=True, validate_strings=True, name=cls.__name__.lower())

class User(Entity, Base):
    __tablename__='users'
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
class AuthSession(Entity, Base):
    __tablename__='auth_sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
class ResearchProject(Entity, Base):
    __tablename__='research_projects'
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
class ResearchVersion(Entity, Base):
    __tablename__='research_versions'
    __table_args__=(UniqueConstraint('project_id','version_number'), CheckConstraint('version_number > 0'))
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    state: Mapped[VersionState] = mapped_column(constrained(VersionState), default=VersionState.DRAFT)
class ResearchArtifact(Entity, Base):
    __tablename__='research_artifacts'
    __table_args__=(UniqueConstraint('research_version_id','artifact_type'), CheckConstraint('size > 0'), CheckConstraint('length(sha256) = 64'))
    research_version_id: Mapped[str] = mapped_column(ForeignKey('research_versions.id'), index=True)
    artifact_type: Mapped[ArtifactType] = mapped_column(constrained(ArtifactType))
    visibility: Mapped[Visibility] = mapped_column(constrained(Visibility), default=Visibility.PRIVATE)
    filename: Mapped[str] = mapped_column(String(200))
    sanitized_filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_backend: Mapped[str] = mapped_column(String(50), default='local_encrypted')
    storage_reference: Mapped[str] = mapped_column(String(500), unique=True)
    encryption_status: Mapped[str] = mapped_column(String(30), default='ENCRYPTED')
class Manuscript(Entity, Base):
    __tablename__='manuscripts'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('research_artifacts.id'), unique=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
class Dataset(Entity, Base):
    __tablename__='datasets'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('research_artifacts.id'), unique=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
class AnalysisCode(Entity, Base):
    __tablename__='analysis_code'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('research_artifacts.id'), unique=True)
    execution_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__=(CheckConstraint('execution_enabled = false'),)
class VerificationRun(Entity, Base):
    __tablename__='verification_runs'
    research_version_id: Mapped[str] = mapped_column(ForeignKey('research_versions.id'), unique=True)
    job_status: Mapped[RunState] = mapped_column(constrained(RunState), default=RunState.QUEUED, index=True)
    verification_status: Mapped[VerificationStatus | None] = mapped_column(constrained(VerificationStatus))
    engine_version: Mapped[str] = mapped_column(String(50), default='0.3.0')
    ruleset_version: Mapped[str] = mapped_column(String(50), default='2026-10')
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ai_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    scientific_report: Mapped[dict | None] = mapped_column(JSON)
class Claim(Entity, Base):
    __tablename__='claims'
    research_version_id: Mapped[str] = mapped_column(ForeignKey('research_versions.id'), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(String(100))
    reported_value: Mapped[float] = mapped_column(Float)
    tolerance: Mapped[float] = mapped_column(Float)
    source_page: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    input_fields: Mapped[list] = mapped_column(JSON)
    __table_args__=(CheckConstraint('confidence >= 0 AND confidence <= 1'),CheckConstraint('tolerance >= 0'),CheckConstraint('source_page > 0'))
class Evidence(Entity, Base):
    __tablename__='evidence'
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey('research_artifacts.id'), index=True)
    dataset_columns: Mapped[list] = mapped_column(JSON)
    calculated_value: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(200))
class ClaimEvidenceLink(Entity, Base):
    __tablename__='claim_evidence_links'
    __table_args__=(UniqueConstraint('claim_id','evidence_id'),)
    claim_id: Mapped[str] = mapped_column(ForeignKey('claims.id'), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey('evidence.id'), index=True)
    outcome: Mapped[Outcome] = mapped_column(constrained(Outcome))
    explanation: Mapped[str] = mapped_column(Text)
class VerificationCheck(Entity, Base):
    __tablename__='verification_checks'
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey('claims.id'), unique=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey('evidence.id'))
    check_type: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(200))
    reported_value: Mapped[float] = mapped_column(Float)
    calculated_value: Mapped[float | None] = mapped_column(Float)
    tolerance: Mapped[float] = mapped_column(Float)
    outcome: Mapped[Outcome] = mapped_column(constrained(Outcome))
    explanation: Mapped[str] = mapped_column(Text)
    software_versions: Mapped[dict] = mapped_column(JSON)
    absolute_difference: Mapped[float | None] = mapped_column(Float)
    relative_difference: Mapped[float | None] = mapped_column(Float)
    relative_tolerance: Mapped[float | None] = mapped_column(Float)
    comparison_method: Mapped[str | None] = mapped_column(String(100))
    rule_version: Mapped[str | None] = mapped_column(String(50))
    rule_context: Mapped[dict | None] = mapped_column(JSON)

class VerificationFinding(Entity, Base):
    __tablename__='verification_findings'
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
class VerificationScore(Entity, Base):
    __tablename__='verification_scores'
    __table_args__=(UniqueConstraint('run_id','dimension'),CheckConstraint('value >= 0 AND value <= 100'))
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), index=True)
    dimension: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    weight: Mapped[float | None] = mapped_column(Float)
class ProvenanceRecord(Entity, Base):
    __tablename__='provenance_records'
    run_id: Mapped[str] = mapped_column(ForeignKey('verification_runs.id'), unique=True)
    research_version_id: Mapped[str] = mapped_column(ForeignKey('research_versions.id'), unique=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    provenance_hash: Mapped[str] = mapped_column(String(64), index=True)
class BlockchainAttestation(Entity, Base):
    __tablename__='blockchain_attestations'
    provenance_id: Mapped[str] = mapped_column(ForeignKey('provenance_records.id'), unique=True)
    status: Mapped[str] = mapped_column(String(40), default='NOT_REQUESTED')
    chain_id: Mapped[int | None] = mapped_column(Integer)
    transaction_hash: Mapped[str | None] = mapped_column(String(100))
    contract_address: Mapped[str | None] = mapped_column(String(42))
    signer_address: Mapped[str | None] = mapped_column(String(42))
    researcher_address: Mapped[str | None] = mapped_column(String(42))
    provenance_hash: Mapped[str | None] = mapped_column(String(64))
    block_number: Mapped[int | None] = mapped_column(Integer)
    block_hash: Mapped[str | None] = mapped_column(String(66))
    confirmations_required: Mapped[int | None] = mapped_column(Integer)
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nonce: Mapped[int | None] = mapped_column(Integer)
    signed_transaction: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__=(CheckConstraint("status IN ('NOT_REQUESTED','PENDING','SUBMITTED','CONFIRMED','FAILED')",name='attestation_state'),)

class ArtifactPublication(Entity, Base):
    __tablename__='artifact_publications'
    artifact_id: Mapped[str] = mapped_column(ForeignKey('research_artifacts.id'), unique=True)
    status: Mapped[str] = mapped_column(String(30),default='NOT_PUBLISHED')
    provider: Mapped[str | None] = mapped_column(String(50))
    cid: Mapped[str | None] = mapped_column(String(120))
    artifact_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__=(CheckConstraint("status IN ('NOT_PUBLISHED','PUBLISHING','PUBLISHED','FAILED')"),)
