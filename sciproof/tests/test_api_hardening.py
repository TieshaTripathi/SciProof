import uuid
import pytest
from apps.api.configuration import validate_configuration
from apps.api.storage import bounded_json, read_dataset
from apps.api.task_signing import sign_task, valid_task
from apps.api.rate_limit import RequestLimiter
from tests.test_api import sign_in

def test_versioned_api_pagination_and_safe_errors(client):
    sign_in(client)
    for title in ('one','two','three'): assert client.post('/api/v1/projects',json={'title':title}).status_code==200
    assert len(client.get('/api/v1/projects?limit=2').json())==2
    assert len(client.get('/projects?offset=2&limit=2').json())==1
    assert client.get('/api/v1/projects?limit=1000').status_code==422
    response=client.post('/api/v1/auth/login',json={'email':'x','password':'do-not-echo-secret'})
    assert response.status_code==422 and 'do-not-echo-secret' not in response.text
    assert response.json()['error']['code']=='REQUEST_VALIDATION_FAILED'
    assert response.headers['x-request-id'] and response.headers['cache-control']=='no-store'
    assert client.get('/api/v1/health/live').status_code==200

def test_auth_rate_limit_and_origin(client):
    origin={'Origin':'http://localhost:3000'}
    for _ in range(31):
        response=client.options('/auth/login',headers={**origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
        assert response.status_code==200
    statuses=[]
    for _ in range(31):
        response=client.post('/auth/login',headers=origin,json={'email':'none@example.org','password':'wrong-long-password'})
        statuses.append(response.status_code)
    assert statuses[0]==401
    assert statuses[-1]==429
    assert response.headers['access-control-allow-origin']==origin['Origin']
    assert client.post('/auth/login',headers={'Origin':'https://evil.example'},json={}).status_code in (403,429)

@pytest.mark.parametrize('variable,value',[
    ('WEB_ORIGIN','*'),('VERIFICATION_MODE','magic'),('REDIS_URL','http://queue'),
    ('AI_ENABLED','yes'),('STORAGE_BACKEND','unknown'),('STORAGE_ENCRYPTION_KEY','invalid')])
def test_bad_configuration_fails_early(monkeypatch,variable,value):
    monkeypatch.setenv(variable,value)
    with pytest.raises(ValueError): validate_configuration()

def test_production_does_not_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(ValueError,match='PostgreSQL'): validate_configuration('sqlite:///test.sqlite')

def test_task_authentication(monkeypatch):
    monkeypatch.setenv('TASK_SIGNING_KEY','a'*32)
    rid=str(uuid.uuid4());signature=sign_task(rid)
    assert valid_task(rid,signature)
    assert not valid_task(str(uuid.uuid4()),signature)
    assert not valid_task(rid,'0'*64)
    monkeypatch.setenv('TASK_SIGNING_KEY','b'*32)
    assert not valid_task(rid,signature)

def test_forged_task_does_not_access_database(monkeypatch):
    from apps.api.tasks import verify_task
    monkeypatch.setenv('TASK_SIGNING_KEY','a'*32)
    monkeypatch.setattr('apps.api.tasks.make_database',lambda:pytest.fail('Forged task accessed database'))
    with pytest.raises(ValueError,match='envelope'): verify_task.apply(args=[str(uuid.uuid4()),'0'*64],throw=True)

def test_parser_bounds_before_conversion():
    with pytest.raises(ValueError,match='nesting'): bounded_json(b'['*65+b'0'+b']'*65)
    assert bounded_json(b'{"quoted":"[[[[["}')=={'quoted':'[[[[['}
    with pytest.raises(ValueError,match='Unique'): read_dataset(b'x,x\n1,2','.csv')
    with pytest.raises(ValueError): read_dataset(b'x\n1','.unknown')

def test_limiter_memory_bound():
    limiter=RequestLimiter()
    for index in range(6000): assert limiter.allow(str(index),'read',10)
    assert len(limiter.buckets)==5000

def test_chunked_request_body_limit(client):
    # No Content-Length: the receive boundary must enforce the actual bytes.
    response=client.post('/api/v1/auth/login',headers={'Content-Type':'application/json'},
                         content=(b' '*1024*1024 for _ in range(22)))
    assert response.status_code==413
    assert response.json()['error']['code']=='HTTP_413'

def test_parser_runs_in_child_and_rejects_malformed_input():
    from apps.api.parser_boundary import isolated_validate
    metadata=isolated_validate('data.csv','DATASET',b'x\n1\n2')
    assert metadata['mime_type']=='text/csv' and metadata['size']==5
    import hashlib
    assert metadata['sha256']==hashlib.sha256(b'x\n1\n2').hexdigest()
    with pytest.raises(ValueError,match='rejected'):
        isolated_validate('paper.pdf','MANUSCRIPT',b'not a PDF')

def test_parser_child_secrets_and_timeout(monkeypatch):
    import subprocess
    from apps.api.parser_boundary import isolated_validate
    monkeypatch.setenv('STORAGE_ENCRYPTION_KEY','never-forward-this-secret')
    monkeypatch.setenv('DATABASE_URL','never-forward-this-credential')
    def timeout(*args,**kwargs):
        assert 'STORAGE_ENCRYPTION_KEY' not in kwargs['env']
        assert 'DATABASE_URL' not in kwargs['env']
        assert kwargs['timeout']==25
        raise subprocess.TimeoutExpired(args[0],25)
    monkeypatch.setattr('apps.api.parser_boundary.subprocess.run',timeout)
    with pytest.raises(subprocess.TimeoutExpired): isolated_validate('data.csv','DATASET',b'x\n1')
