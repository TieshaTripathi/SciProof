"""HTTP boundary; scientific work lives in the worker service."""
import hashlib, logging, os, secrets, uuid
from datetime import timedelta, timezone
from typing import Literal
from fastapi import FastAPI, APIRouter, Query, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from argon2 import PasswordHasher
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from apps.api.database import make_database
from apps.api.models import *
from apps.api.storage import LocalEncryptedStorage, MAX_BYTES
from apps.api.parser_boundary import isolated_validate
from apps.api.storage_providers import configured_storage
from apps.api.ipfs import configured_publisher, valid_cid
from apps.api.verification_service import execute_run, run_payload
from apps.api.logging_config import configure_logging

configure_logging()
log=logging.getLogger('sciproof'); ph=PasswordHasher()
class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=12,max_length=128)
    @field_validator('email')
    @classmethod
    def email_format(cls,value):
        value=value.strip().lower()
        if value.count('@')!=1 or any(c.isspace() for c in value) or not all(value.split('@')): raise ValueError('Invalid email')
        return value
class ProjectInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    @field_validator('title')
    @classmethod
    def clean_title(cls,value):
        if not value.strip(): raise ValueError('Title is required')
        return value.strip()
class AttestationConsent(BaseModel):
    confirm_attestation:Literal[True]
    researcher_address:str=Field(pattern=r'^0x[0-9a-fA-F]{40}$')

class PublicationConsent(BaseModel):
    confirm_publication:Literal[True]

KINDS={'manuscript':ArtifactType.MANUSCRIPT,'dataset':ArtifactType.DATASET,'analysis':ArtifactType.ANALYSIS_CODE}

def create_app(database_url=None,storage=None,execution_mode=None):
    from apps.api.blockchain import configured_attestor, DisabledAttestationProvider
    configured_attestor()  # Validate configuration; no RPC request.
    from packages.ai.semantic import configured_provider
    configured_publisher()  # Validate optional publication configuration.
    configured_provider()  # Validate enabled optional configuration without making a request.
    from apps.api.configuration import validate_configuration
    validated_mode=validate_configuration(database_url,execution_mode,storage)
    app=FastAPI(title='SciProof',version='0.3.0')
    from apps.api.body_limit import BodyLimitMiddleware
    app.add_middleware(BodyLimitMiddleware,max_bytes=MAX_BYTES+1024*1024)
    engine,sessions=make_database(database_url)
    app.state.engine=engine;app.state.sessions=sessions;app.state.storage=storage
    mode=validated_mode
    if mode not in ('celery','inline','manual'): raise ValueError('Invalid VERIFICATION_MODE')
    origin=os.getenv('WEB_ORIGIN','http://localhost:3000')
    def storage_backend():
        if app.state.storage is None: app.state.storage=configured_storage()
        return app.state.storage
    def db_session():
        with sessions() as db: yield db
    def current_user(request:Request,db=Depends(db_session)):
        digest=hashlib.sha256(request.cookies.get('session','').encode()).hexdigest()
        session=db.scalar(select(AuthSession).where(AuthSession.token_hash==digest))
        if not session: raise HTTPException(401,'Sign in required')
        expiry=session.expires_at
        if expiry.tzinfo is None: expiry=expiry.replace(tzinfo=timezone.utc)
        if expiry<now(): raise HTTPException(401,'Session expired')
        return session.user_id
    def project_owned(db,pid,uid,lock=False):
        query=select(ResearchProject).where(ResearchProject.id==str(pid),ResearchProject.owner_id==uid)
        p=db.scalar(query.with_for_update() if lock else query)
        if not p: raise HTTPException(404,'Not found')
        return p
    def version_owned(db,vid,uid,lock=False):
        query=select(ResearchVersion).join(ResearchProject).where(ResearchVersion.id==str(vid),ResearchProject.owner_id==uid)
        v=db.scalar(query.with_for_update(of=ResearchVersion) if lock else query)
        if not v: raise HTTPException(404,'Not found')
        return v
    def artifact_payload(a):
        return {'id':a.id,'artifact_id':a.id,'research_version_id':a.research_version_id,
                'artifact_type':a.artifact_type.value,'visibility':a.visibility.value,
                'filename':a.filename,'sanitized_filename':a.sanitized_filename,'mime_type':a.mime_type,
                'size':a.size,'sha256':a.sha256,'storage_backend':a.storage_backend,
                'storage_reference':'protected:'+a.id,'encryption_status':a.encryption_status,'created_at':a.created_at.isoformat()}
    def current_report_payload(db,run):
        payload=run_payload(run)
        if run.job_status==RunState.COMPLETED:
            a=db.scalar(select(BlockchainAttestation).join(ProvenanceRecord).where(ProvenanceRecord.run_id==run.id))
            if a: payload['attestation']=attestation_payload(a)
        return payload
    from apps.api.rate_limit import RequestLimiter
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    limiter=RequestLimiter()
    def error_response(request,status,message,code):
        return JSONResponse({'detail':message,'error':{'code':code,'message':message,
            'request_id':getattr(request.state,'request_id',None)}},status_code=status)
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,error):
        return error_response(request,error.status_code,str(error.detail),'HTTP_'+str(error.status_code))
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error):
        # Pydantic input/context fields may contain credentials; expose only safe locations/types.
        response=error_response(request,422,'Invalid request','REQUEST_VALIDATION_FAILED')
        return response
    @app.middleware('http')
    async def request_context(request,call_next):
        rid=str(uuid.uuid4());request.state.request_id=rid
        path=request.url.path.removeprefix('/api/v1')
        group='auth' if path.startswith('/auth/') else 'write' if request.method=='POST' else 'read'
        limit=30 if group=='auth' else 60 if group=='write' else 240
        if not path.startswith('/health') and not limiter.allow(request.client.host if request.client else 'unknown',group,limit):
            response=error_response(request,429,'Too many requests; retry shortly','RATE_LIMITED')
            response.headers['Retry-After']='60';response.headers['X-Request-ID']=rid;return response
        length=request.headers.get('content-length')
        if length:
            try: oversized=int(length)>MAX_BYTES+1024*1024
            except ValueError: return error_response(request,400,'Invalid Content-Length','INVALID_REQUEST')
            if oversized: return error_response(request,413,'Request exceeds upload limit','PAYLOAD_TOO_LARGE')
        if request.method=='POST' and (request.headers.get('origin') not in (None,origin) or
            (request.headers.get('sec-fetch-site')=='cross-site' and not request.headers.get('origin'))):
            return error_response(request,403,'Invalid origin','INVALID_ORIGIN')
        try: response=await call_next(request)
        except Exception as error:
            log.error('request_failed',extra={'request_id':rid,'error_type':type(error).__name__})
            response=error_response(request,500,'Request could not be completed','INTERNAL_ERROR')
        response.headers['X-Request-ID']=rid
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store' 
        log.info('request',extra={'request_id':rid,'path':request.url.path,'status':response.status_code})
        return response
    @app.post('/auth/signup')
    def signup(c:Credentials,db=Depends(db_session)):
        db.add(User(email=c.email,password_hash=ph.hash(c.password)))
        try: db.commit()
        except IntegrityError: db.rollback();raise HTTPException(409,'Account exists')
        return {'ok':True}
    @app.post('/auth/login')
    def login(c:Credentials,response:Response,db=Depends(db_session)):
        u=db.scalar(select(User).where(User.email==c.email))
        try:
            if not u: raise ValueError()
            ph.verify(u.password_hash,c.password)
        except Exception: raise HTTPException(401,'Invalid credentials')
        token=secrets.token_urlsafe(48)
        db.add(AuthSession(user_id=u.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=now()+timedelta(hours=8)));db.commit()
        response.set_cookie('session',token,httponly=True,samesite='lax',secure=os.getenv('SECURE_COOKIES')=='true',max_age=28800)
        return {'ok':True}
    @app.post('/auth/logout')
    def logout(request:Request,response:Response,uid=Depends(current_user),db=Depends(db_session)):
        s=db.scalar(select(AuthSession).where(AuthSession.token_hash==hashlib.sha256(request.cookies.get('session','').encode()).hexdigest(),AuthSession.user_id==uid))
        if s: db.delete(s);db.commit()
        response.delete_cookie('session');return {'ok':True}
    @app.get('/projects')
    def projects(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),uid=Depends(current_user),db=Depends(db_session)):
        return [{'id':p.id,'title':p.title,'created_at':p.created_at.isoformat()} for p in db.scalars(select(ResearchProject).where(ResearchProject.owner_id==uid).order_by(ResearchProject.created_at,ResearchProject.id).offset(offset).limit(limit))]
    @app.post('/projects')
    def create_project(p:ProjectInput,uid=Depends(current_user),db=Depends(db_session)):
        project=ResearchProject(owner_id=uid,title=p.title);db.add(project);db.commit()
        return {'id':project.id,'title':project.title}
    @app.post('/projects/{pid}/versions')
    def create_version(pid:uuid.UUID,uid=Depends(current_user),db=Depends(db_session)):
        project_owned(db,pid,uid,lock=True)
        number=(db.scalar(select(func.max(ResearchVersion.version_number)).where(ResearchVersion.project_id==str(pid))) or 0)+1
        v=ResearchVersion(project_id=str(pid),version_number=number);db.add(v)
        try: db.commit()
        except IntegrityError: db.rollback();raise HTTPException(409,'Concurrent version creation; retry')
        return {'id':v.id,'research_id':v.project_id,'version_number':v.version_number,'state':v.state.value}
    @app.get('/projects/{pid}/versions')
    def versions(pid:uuid.UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),uid=Depends(current_user),db=Depends(db_session)):
        project_owned(db,pid,uid)
        return [{'id':v.id,'version_number':v.version_number,'state':v.state.value} for v in db.scalars(select(ResearchVersion).where(ResearchVersion.project_id==str(pid)).order_by(ResearchVersion.version_number).offset(offset).limit(limit))]
    @app.get('/projects/{pid}/runs')
    def project_runs(pid:uuid.UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),uid=Depends(current_user),db=Depends(db_session)):
        project_owned(db,pid,uid)
        rows=db.execute(select(VerificationRun,ResearchVersion.version_number).join(ResearchVersion).where(ResearchVersion.project_id==str(pid)).order_by(ResearchVersion.version_number.desc()).offset(offset).limit(limit)).all()
        return [{'id':r.id,'version_number':number,'job_status':r.job_status.value,
                 'verification_status':r.verification_status.value if r.verification_status else None,'created_at':r.created_at.isoformat()} for r,number in rows]
    @app.post('/versions/{vid}/artifacts/{kind}')
    async def upload(vid:uuid.UUID,kind:Literal['manuscript','dataset','analysis'],file:UploadFile=File(...),
                     visibility:Visibility=Form(Visibility.PRIVATE),uid=Depends(current_user),db=Depends(db_session)):
        v=version_owned(db,vid,uid,lock=True)
        if v.state!=VersionState.DRAFT: raise HTTPException(409,'Sealed versions are immutable; create a new version')
        raw=await file.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise HTTPException(413,'20 MB maximum')
        try: metadata=await run_in_threadpool(isolated_validate,file.filename,KINDS[kind].value,raw)
        except Exception as e: raise HTTPException(400,'Content does not match supported format or filename') from e
        existing=db.scalar(select(ResearchArtifact).where(ResearchArtifact.research_version_id==v.id,ResearchArtifact.artifact_type==KINDS[kind]))
        if existing:
            if existing.sha256==metadata['sha256'] and existing.visibility==visibility: return artifact_payload(existing)
            raise HTTPException(409,'Artifact already exists; create a new version to replace it')
        a=ResearchArtifact(id=str(uuid.uuid4()),research_version_id=v.id,artifact_type=KINDS[kind],visibility=visibility,
                           storage_reference=str(uuid.uuid4()),**metadata)
        backend=storage_backend();a.storage_backend=backend.backend;written=False
        try:
            await run_in_threadpool(backend.put,a.storage_reference,raw);written=True
            db.add(a);db.flush()
            subtype=Manuscript if kind=='manuscript' else Dataset if kind=='dataset' else AnalysisCode
            db.add(subtype(artifact_id=a.id));db.commit()
        except Exception:
            db.rollback()
            if written: backend.delete(a.storage_reference)
            raise
        return artifact_payload(a)
    @app.get('/versions/{vid}/artifacts')
    def artifacts(vid:uuid.UUID,uid=Depends(current_user),db=Depends(db_session)):
        version_owned(db,vid,uid)
        return [artifact_payload(a) for a in db.scalars(select(ResearchArtifact).where(ResearchArtifact.research_version_id==str(vid)))]
    def publication_payload(p):
        return {'status':p.status,'provider':p.provider,'cid':p.cid,'artifact_hash':p.artifact_hash,
                'published_at':p.published_at.isoformat() if p.published_at else None,'error_code':p.error_code}
    def artifact_owned(db,aid,uid,lock=False):
        query=select(ResearchArtifact).join(ResearchVersion).join(ResearchProject).where(
            ResearchArtifact.id==str(aid),ResearchProject.owner_id==uid)
        artifact=db.scalar(query.with_for_update(of=ResearchArtifact) if lock else query)
        if not artifact: raise HTTPException(404,'Not found')
        return artifact
    @app.get('/artifacts/{aid}/publication')
    def publication(aid:uuid.UUID,uid=Depends(current_user),db=Depends(db_session)):
        artifact_owned(db,aid,uid)
        p=db.scalar(select(ArtifactPublication).where(ArtifactPublication.artifact_id==str(aid)))
        return publication_payload(p) if p else {'status':'NOT_PUBLISHED','cid':None}
    @app.post('/artifacts/{aid}/publish')
    async def publish_artifact(aid:uuid.UUID,consent:PublicationConsent,response:Response,
                               uid=Depends(current_user),db=Depends(db_session)):
        a=artifact_owned(db,aid,uid,lock=True)
        if a.visibility!=Visibility.PUBLIC: raise HTTPException(403,'Only explicitly PUBLIC artifacts may be published')
        publisher=getattr(app.state,'publisher',None) or configured_publisher()
        if publisher is None: raise HTTPException(503,'Content-addressed publication is disabled')
        p=db.scalar(select(ArtifactPublication).where(ArtifactPublication.artifact_id==a.id))
        if p and p.status in ('PUBLISHED','PUBLISHING'):
            response.status_code=202 if p.status=='PUBLISHING' else 200
            return publication_payload(p)
        if not p:
            p=ArtifactPublication(artifact_id=a.id,artifact_hash=a.sha256);db.add(p)
        p.status='PUBLISHING';p.provider=publisher.identifier;p.error_code=None
        reference=a.storage_reference;original_hash=a.sha256;artifact_id=a.id
        db.commit()
        try:
            raw=await run_in_threadpool(storage_backend().get,reference,original_hash)
            if hashlib.sha256(raw).hexdigest()!=original_hash: raise ValueError('Artifact integrity failure')
            cid=await run_in_threadpool(publisher.publish,raw,original_hash)
            if not valid_cid(cid): raise ValueError('Invalid CID receipt')
            db.refresh(a)
            if a.sha256!=original_hash or a.visibility!=Visibility.PUBLIC: raise ValueError('Artifact policy changed')
            p.status='PUBLISHED';p.cid=cid;p.published_at=now()
        except Exception:
            p.status='FAILED';p.error_code='PUBLICATION_FAILED'
            log.warning('publication_failed',extra={'artifact_id':artifact_id})
        db.commit()
        response.status_code=200 if p.status=='PUBLISHED' else 502
        return publication_payload(p)
    @app.post('/versions/{vid}/verify')
    def start_run(vid:uuid.UUID,response:Response,uid=Depends(current_user),db=Depends(db_session)):
        v=version_owned(db,vid,uid,lock=True)
        run=db.scalar(select(VerificationRun).where(VerificationRun.research_version_id==v.id))
        if not run:
            types=set(db.scalars(select(ResearchArtifact.artifact_type).where(ResearchArtifact.research_version_id==v.id)))
            if not {ArtifactType.MANUSCRIPT,ArtifactType.DATASET}<=types: raise HTTPException(422,'Manuscript and dataset required')
            run=VerificationRun(research_version_id=v.id);v.state=VersionState.SEALED;db.add(run)
            try: db.commit()
            except IntegrityError: db.rollback();raise HTTPException(409,'Concurrent verification request; retry')
        else: db.commit()
        if run.job_status==RunState.QUEUED:
            if mode=='inline': execute_run(run.id,sessions,storage_backend())
            elif mode=='celery':
                from apps.api.tasks import enqueue
                try: enqueue(run.id)
                except Exception: log.warning('broker_dispatch_failed; queued run retained',extra={'run_id':run.id})
        db.expire_all();run=db.get(VerificationRun,run.id)
        response.status_code=200 if run.job_status==RunState.COMPLETED else 202
        return current_report_payload(db,run)
    @app.get('/runs/{rid}')
    def report(rid:uuid.UUID,uid=Depends(current_user),db=Depends(db_session)):
        run=db.get(VerificationRun,str(rid))
        if not run: raise HTTPException(404,'Not found')
        version_owned(db,run.research_version_id,uid)
        return current_report_payload(db,run)
    def attestation_payload(a):
        return {key:getattr(a,key) for key in ('status','chain_id','contract_address','transaction_hash',
            'block_number','block_hash','provenance_hash','confirmations_required','error_code')} | {
                'attested_at':a.attested_at.isoformat() if a.attested_at else None}
    def attestation_owned(db,rid,uid,lock=False):
        query=select(VerificationRun).where(VerificationRun.id==str(rid))
        run=db.scalar(query.with_for_update() if lock else query)
        if not run: raise HTTPException(404,'Not found')
        version_owned(db,run.research_version_id,uid)
        if run.job_status!=RunState.COMPLETED: raise HTTPException(409,'Completed scientific report required')
        provenance=db.scalar(select(ProvenanceRecord).where(ProvenanceRecord.run_id==run.id))
        a=db.scalar(select(BlockchainAttestation).where(BlockchainAttestation.provenance_id==provenance.id))
        return run,a
    @app.get('/runs/{rid}/attestation')
    def attestation(rid:uuid.UUID,uid=Depends(current_user),db=Depends(db_session)):
        _,a=attestation_owned(db,rid,uid)
        return attestation_payload(a)
    @app.post('/runs/{rid}/attestation')
    def request_attestation(rid:uuid.UUID,consent:AttestationConsent,response:Response,
                            uid=Depends(current_user),db=Depends(db_session)):
        provider=getattr(app.state,'attestor',None) or configured_attestor()
        run,a=attestation_owned(db,rid,uid,lock=True)
        if isinstance(provider,DisabledAttestationProvider): raise HTTPException(503,'Blockchain attestation disabled')
        if a.status in ('SUBMITTED','CONFIRMED') or (a.status=='FAILED' and a.signed_transaction): return attestation_payload(a)
        if a.signed_transaction and (a.researcher_address.lower()!=consent.researcher_address.lower() or
            a.chain_id!=provider.chain_id or a.contract_address!=provider.contract_address):
            raise HTTPException(409,'Prepared attestation configuration is immutable')
        if not a.signed_transaction:
            # Serialize nonce allocation across API processes on PostgreSQL.
            if engine.dialect.name=='postgresql': db.execute(text('SELECT pg_advisory_xact_lock(7310441)'))
            latest=db.scalar(select(func.max(BlockchainAttestation.nonce)).where(
                BlockchainAttestation.chain_id==provider.chain_id,BlockchainAttestation.signer_address==provider.signer_address))
            try: prepared=provider.prepare(run.scientific_report,consent.researcher_address,(latest+1) if latest is not None else 0)
            except Exception:
                a.status='FAILED';a.error_code='ATTESTATION_PREPARATION_FAILED';db.commit()
                response.status_code=502;return attestation_payload(a)
            a.status='PENDING';a.chain_id=provider.chain_id;a.contract_address=provider.contract_address
            a.signer_address=provider.signer_address;a.researcher_address=consent.researcher_address
            a.confirmations_required=provider.confirmations_required;a.error_code=None
            for key,value in prepared.items(): setattr(a,key,value)
            db.commit() # Persist recoverable signed bytes before broadcast.
        try:
            provider.submit(a.signed_transaction,a.transaction_hash)
            a.status='SUBMITTED';a.error_code=None
        except Exception:
            # Broadcast could have succeeded before a timeout; retain recoverable PENDING.
            a.error_code='BROADCAST_UNCERTAIN'
        db.commit();response.status_code=202
        return attestation_payload(a)
    @app.post('/runs/{rid}/attestation/refresh')
    def refresh_attestation(rid:uuid.UUID,response:Response,uid=Depends(current_user),db=Depends(db_session)):
        run,a=attestation_owned(db,rid,uid,lock=True)
        provider=getattr(app.state,'attestor',None) or configured_attestor()
        if not a.transaction_hash or isinstance(provider,DisabledAttestationProvider): return attestation_payload(a)
        if a.chain_id!=provider.chain_id or a.contract_address!=provider.contract_address: raise HTTPException(409,'Attestation provider configuration differs')
        try:
            state=provider.inspect(a.transaction_hash,run.scientific_report,a.researcher_address,a.confirmations_required)
            chain_timestamp=state.pop('chain_timestamp',None)
            for key,value in state.items(): setattr(a,key,value)
            if a.status=='CONFIRMED' and chain_timestamp is not None:
                from datetime import datetime
                a.attested_at=datetime.fromtimestamp(chain_timestamp,timezone.utc)
            elif a.status!='CONFIRMED': a.attested_at=None
            db.commit()
        except Exception:
            # A failed refresh cannot certify a formerly confirmed result as current.
            a.status='SUBMITTED' if a.status in ('SUBMITTED','CONFIRMED') else 'PENDING'
            a.block_number=None;a.block_hash=None;a.attested_at=None
            a.error_code='ATTESTATION_REFRESH_UNAVAILABLE';db.commit();response.status_code=503
        return attestation_payload(a)
    @app.get('/health/live')
    @app.get('/health')
    def health(): return {'status':'ok','sandbox':'disabled','engine_version':'0.3.0'}
    @app.get('/health/ready')
    def readiness(db=Depends(db_session)):
        try: db.execute(text('SELECT 1 FROM verification_runs LIMIT 1'))
        except Exception: raise HTTPException(503,'Database or migrations unavailable')
        if mode=='celery':
            import redis
            try:
                connection=redis.Redis.from_url(os.getenv('REDIS_URL','redis://localhost:6379/0'),socket_timeout=1,socket_connect_timeout=1)
                try: connection.ping()
                finally: connection.close()
            except Exception: raise HTTPException(503,'Queue broker unavailable; submissions remain durable')
        return {'status':'ready','verification_mode':mode}
    # Preserve legacy paths while providing the versioned public API.
    from fastapi.routing import APIRoute
    compatibility=APIRouter()
    compatibility.routes=[route for route in app.routes if isinstance(route,APIRoute)]
    app.include_router(compatibility,prefix='/api/v1')
    # Keep CORS outside request throttling: preflights do not consume auth limits,
    # and permitted browser origins can read throttled/error responses.
    app.add_middleware(CORSMiddleware,allow_origins=[origin],allow_credentials=True,allow_methods=['GET','POST'],allow_headers=['Content-Type'])
    return app

app=create_app()
