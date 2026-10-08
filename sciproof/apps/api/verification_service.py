"""Idempotent persisted verification; scientific evidence commits atomically."""
import io
import logging
import platform
from importlib.metadata import version
from pathlib import Path
from sqlalchemy import select, update
from pypdf import PdfReader
from apps.api.models import *
from apps.api.storage import read_dataset
from packages.ai.provider import LocalProvider, PROMPT_VERSION
from packages.ai.semantic import augment
from packages.verification.engine import verify, canonical_hash

def run_payload(run):
    if run.job_status==RunState.COMPLETED:
        return {'id':run.id,'job_status':run.job_status.value,**run.scientific_report}
    return {'id':run.id,'job_status':run.job_status.value,'status':run.job_status.value,
            'error_code':run.error_code,'version_id':run.research_version_id}

def execute_run(run_id,sessions,storage):
    # Conditional claim supports duplicate broker delivery without duplicate execution.
    with sessions.begin() as db:
        result=db.execute(update(VerificationRun).where(VerificationRun.id==run_id,
                         VerificationRun.job_status==RunState.QUEUED).values(
                         job_status=RunState.RUNNING,started_at=now(),attempts=VerificationRun.attempts+1))
        if result.rowcount!=1: return
    try:
        with sessions() as db:
            run=db.get(VerificationRun,run_id)
            v=db.get(ResearchVersion,run.research_version_id)
            artifacts=list(db.scalars(select(ResearchArtifact).where(ResearchArtifact.research_version_id==v.id).order_by(ResearchArtifact.id)))
            selected={a.artifact_type:a for a in artifacts}
            artifact_bytes={a.id:storage.get(a.storage_reference,a.sha256) for a in artifacts}
            data=selected[ArtifactType.DATASET]; paper=selected[ArtifactType.MANUSCRIPT]
            df=read_dataset(artifact_bytes[data.id],Path(data.filename).suffix.lower())
            pages=[p.extract_text() or '' for p in PdfReader(io.BytesIO(artifact_bytes[paper.id])).pages]
            provider=LocalProvider(); claims=[c.model_dump() for c in provider.extract(pages,list(df.columns))]
            report=verify(df,claims,artifact_hashes_verified=True)
            created=now().isoformat()
            ai={'provider':provider.identifier,'prompt_version':PROMPT_VERSION,'timestamp':created,
                'structured_output':claims,'semantic_verification':'Unavailable; offline explicit extraction only','retries':0,'error':None,
                'semantic':augment(claims,list(df.columns),[a.visibility.value for a in artifacts])}
            manifest={'research_id':v.project_id,'version_id':v.id,'version_number':v.version_number,
                      'verification_run_id':run.id,'engine_version':run.engine_version,'ruleset_version':run.ruleset_version,
                      'software_versions':{'python':platform.python_version(),**{p:version(p) for p in ('pandas','numpy','scipy','pypdf')}},
                      'ai_provider':provider.identifier,'prompt_version':PROMPT_VERSION,'created_at':created,
                      'paper_sha256':paper.sha256,'dataset_sha256':data.sha256,
                      'analysis_code_sha256':selected[ArtifactType.ANALYSIS_CODE].sha256 if ArtifactType.ANALYSIS_CODE in selected else None,
                      'scores':report['scores'],'scoring_weights':report['weights'],
                      'numerical_conventions':report['numerical_conventions'],
                      'artifacts':[{'id':a.id,'sha256':a.sha256,'visibility':a.visibility.value,'storage_reference':'protected:'+a.id} for a in artifacts]}
        with sessions.begin() as db:
            run=db.scalar(select(VerificationRun).where(VerificationRun.id==run_id).with_for_update())
            if run.job_status!=RunState.RUNNING: return
            for claim,check in zip(claims,report['checks']):
                c=Claim(id=claim['claim_id'],research_version_id=v.id,run_id=run_id,claim_text=claim['claim_text'],
                        metric=claim['metric'],reported_value=claim['reported_value'],tolerance=claim['tolerance'],
                        source_page=claim['source_page'],confidence=claim['confidence'],input_fields=claim['columns'])
                db.add(c);db.flush()
                e=Evidence(run_id=run_id,artifact_id=data.id,dataset_columns=claim['columns'],calculated_value=check['calculated_value'],method=check['method'])
                db.add(e);db.flush()
                db.add(ClaimEvidenceLink(claim_id=c.id,evidence_id=e.id,outcome=Outcome(check['outcome']),explanation=check['explanation']))
                check.update(artifact_id=data.id,evidence_id=e.id)
                db.add(VerificationCheck(run_id=run_id,claim_id=c.id,evidence_id=e.id,check_type=claim['metric'],method=check['method'],
                       reported_value=claim['reported_value'],calculated_value=check['calculated_value'],tolerance=claim['tolerance'],
                       outcome=Outcome(check['outcome']),explanation=check['explanation'],software_versions=check['software_versions'],
                       **{field:check[field] for field in ('absolute_difference','relative_difference','relative_tolerance','comparison_method','rule_version','rule_context')}))
            for message in report['findings']: db.add(VerificationFinding(run_id=run_id,severity='warning',message=message))
            for dimension,value in report['scores'].items(): db.add(VerificationScore(run_id=run_id,dimension=dimension,value=value,weight=report['weights'].get(dimension)))
            profile=db.scalar(select(Dataset).where(Dataset.artifact_id==data.id));profile.profile=report['profile']
            manuscript=db.scalar(select(Manuscript).where(Manuscript.artifact_id==paper.id));manuscript.page_count=len(pages)
            provenance=ProvenanceRecord(run_id=run_id,research_version_id=v.id,manifest=manifest,provenance_hash=canonical_hash(manifest))
            db.add(provenance);db.flush()
            db.add(BlockchainAttestation(provenance_id=provenance.id,provenance_hash=provenance.provenance_hash))
            report.update(claims=claims,ai=ai,provenance={'manifest':manifest,'provenance_hash':provenance.provenance_hash},
                          attestation={'status':'NOT_REQUESTED','transaction_hash':None},version_id=v.id)
            run.scientific_report=report;run.ai_metadata=ai;run.verification_status=VerificationStatus(report['status'])
            run.job_status=RunState.COMPLETED;run.finished_at=now()
        logging.getLogger('sciproof').info('verification_completed',extra={'run_id':run_id})
    except Exception as error:
        # Parser exception text can contain private dataset values; log type only.
        logging.getLogger('sciproof').error('verification_failed',extra={'run_id':run_id,'error_type':type(error).__name__})
        with sessions.begin() as db:
            db.execute(update(VerificationRun).where(VerificationRun.id==run_id,VerificationRun.job_status==RunState.RUNNING).values(
                       job_status=RunState.FAILED,error_code='VERIFICATION_PROCESSING_FAILED',finished_at=now()))
