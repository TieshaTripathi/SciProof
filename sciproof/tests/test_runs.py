from sqlalchemy import select, func
from apps.api.models import *
from apps.api.verification_service import execute_run
from tests.test_api import sign_in, version, pdf
from fastapi.testclient import TestClient
from apps.api.main import create_app

def upload_evidence(client,vid):
    assert client.post(f'/versions/{vid}/artifacts/manuscript',files={'file':('paper.pdf',pdf('mean of x = 2'),'application/pdf')}).status_code==200
    assert client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n1\n2\n3','text/csv')}).status_code==200

def test_relational_evidence_and_idempotency(client):
    sign_in(client);vid=version(client);upload_evidence(client,vid)
    first=client.post(f'/versions/{vid}/verify').json()
    second=client.post(f'/versions/{vid}/verify').json()
    assert first['id']==second['id']
    assert first['provenance']['manifest']['verification_run_id']==first['id']
    pid=client.get('/projects').json()[0]['id']
    history=client.get('/projects/'+pid+'/runs').json()
    assert history[0]['id']==first['id'] and history[0]['job_status']=='COMPLETED'
    sessions=client.app.state.sessions
    execute_run(first['id'],sessions,client.app.state.storage)
    with sessions() as db:
        for model in (Claim,Evidence,ClaimEvidenceLink,VerificationCheck,ProvenanceRecord,BlockchainAttestation):
            assert db.scalar(select(func.count()).select_from(model))==1
        assert db.scalar(select(func.count()).select_from(VerificationScore))==6
        check=db.scalar(select(VerificationCheck))
        assert check.absolute_difference==0 and check.relative_difference==0
        assert check.comparison_method=='absolute_plus_reported_relative_v1'
        assert check.rule_context['observations_used']==3 and check.rule_version=='1'
        assert first['checks'][0]['evidence_id']==check.evidence_id
        assert first['checks'][0]['artifact_id']==db.get(Evidence,check.evidence_id).artifact_id

def test_artifact_metadata_and_visibility(client):
    sign_in(client);vid=version(client)
    response=client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('my data.csv',b'x\n1','text/csv')},data={'visibility':'RESTRICTED'})
    a=response.json();assert response.status_code==200
    assert a['visibility']=='RESTRICTED' and a['mime_type']=='text/csv'
    assert a['sanitized_filename']=='my_data.csv' and a['encryption_status']=='ENCRYPTED'
    with client.app.state.sessions() as db:
        stored=db.get(ResearchArtifact,a['id'])
        path=client.app.state.storage.path(stored.storage_reference)
        assert path.read_bytes()!=b'x\n1'
    assert client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('different.csv',b'x\n2','text/csv')}).status_code==409

def test_explicit_version_numbers(client):
    sign_in(client);p=client.post('/projects',json={'title':'versions'}).json()
    assert client.post(f"/projects/{p['id']}/versions").json()['version_number']==1
    assert client.post(f"/projects/{p['id']}/versions").json()['version_number']==2

def test_origin_guard_applies_to_auth(client):
    assert client.post('/auth/signup',json={'email':'a@example.org','password':'a-long-test-password'},headers={'Origin':'https://evil.example'}).status_code==403

def test_failure_has_no_partial_evidence(client):
    sign_in(client);vid=version(client);upload_evidence(client,vid)
    with client.app.state.sessions() as db:
        artifact=db.scalar(select(ResearchArtifact).where(ResearchArtifact.artifact_type==ArtifactType.DATASET))
        client.app.state.storage.path(artifact.storage_reference).write_bytes(b'tampered')
    result=client.post(f'/versions/{vid}/verify').json()
    assert result['job_status']=='FAILED'
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Claim))==0
        assert db.scalar(select(func.count()).select_from(ProvenanceRecord))==0

def test_async_lifecycle_and_duplicate_delivery(client):
    app=create_app(str(client.app.state.engine.url),client.app.state.storage,'manual')
    with TestClient(app) as c:
        sign_in(c);vid=version(c);upload_evidence(c,vid)
        queued=c.post(f'/versions/{vid}/verify')
        assert queued.status_code==202 and queued.json()['job_status']=='QUEUED'
        rid=queued.json()['id']
        assert c.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n4','text/csv')}).status_code==409
        execute_run(rid,app.state.sessions,app.state.storage)
        execute_run(rid,app.state.sessions,app.state.storage)
        assert c.get('/runs/'+rid).json()['job_status']=='COMPLETED'
        with app.state.sessions() as db:
            assert db.get(VerificationRun,rid).attempts==1
    app.state.engine.dispose()

def test_broker_failure_retains_queued_run(client,monkeypatch):
    def unavailable(rid): raise ConnectionError('broker unavailable')
    monkeypatch.setattr('apps.api.tasks.enqueue',unavailable)
    app=create_app(str(client.app.state.engine.url),client.app.state.storage,'celery')
    with TestClient(app) as c:
        sign_in(c);vid=version(c);upload_evidence(c,vid)
        response=c.post(f'/versions/{vid}/verify')
        assert response.status_code==202
        rid=response.json()['id']
        with app.state.sessions() as db: assert db.get(VerificationRun,rid).job_status==RunState.QUEUED
        execute_run(rid,app.state.sessions,app.state.storage)
        assert c.get('/runs/'+rid).json()['job_status']=='COMPLETED'
    app.state.engine.dispose()

def test_celery_task_boundary(client,monkeypatch):
    from apps.api.tasks import verify_task
    app=create_app(str(client.app.state.engine.url),client.app.state.storage,'manual')
    monkeypatch.setenv('DATABASE_URL',str(app.state.engine.url))
    monkeypatch.setenv('STORAGE_ROOT',str(app.state.storage.root))
    with TestClient(app) as c:
        sign_in(c);vid=version(c);upload_evidence(c,vid)
        rid=c.post(f'/versions/{vid}/verify').json()['id']
        from apps.api.task_signing import sign_task
        task=verify_task.apply(args=[rid,sign_task(rid)],throw=True)
        assert task.successful()
        assert c.get('/runs/'+rid).json()['job_status']=='COMPLETED'
    app.state.engine.dispose()
