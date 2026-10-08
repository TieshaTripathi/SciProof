import copy
import httpx
import pandas as pd
import pytest
from packages.ai.semantic import augment, HttpSemanticProvider, DisabledAIProvider, DeterministicFallbackProvider
from packages.verification.engine import verify
from tests.test_api import sign_in, version
from tests.test_runs import upload_evidence

CLAIMS=[dict(claim_id='claim-1',metric='mean',columns=['x'],reported_value=2,tolerance=.001)]
def mapping(**changes):
    return {'claim_id':'claim-1','metric':'mean','candidate_columns':['x'],
            'mapping_confidence':.95,'reason':'Exact field','status':'PROPOSED',**changes}
def provider(handler): return HttpSemanticProvider('https://semantic.example/augment','secret','configured-model',transport=httpx.MockTransport(handler))

@pytest.mark.parametrize('case,expected',[
    ('timeout','PROVIDER_TIMEOUT'),('invalid-json','INVALID_PROVIDER_OUTPUT'),
    ('schema','INVALID_PROVIDER_OUTPUT'),('rate','PROVIDER_RATE_LIMIT'),
    ('unavailable','PROVIDER_UNAVAILABLE'),('empty','INVALID_PROVIDER_OUTPUT')])
def test_failure_safe(case,expected):
    def respond(request):
        if case=='timeout': raise httpx.ReadTimeout('private timeout details',request=request)
        if case=='unavailable': raise httpx.ConnectError('private endpoint',request=request)
        return httpx.Response(429 if case=='rate' else 200,content={
            'invalid-json':b'not-json','schema':b'{"unexpected":true}','empty':b''}.get(case,b'{}'))
    original=copy.deepcopy(CLAIMS)
    report=verify(pd.DataFrame({'x':[1,2,3]}),CLAIMS)
    audit=augment(CLAIMS,['x'],['PUBLIC'],provider(respond))
    assert audit['status']=='FAILED' and audit['failure_reason']==expected
    assert audit['response_timestamp'] and audit['retry_count']==0
    assert CLAIMS==original
    assert report['checks'][0]['outcome']=='SUPPORTED'
    assert 'secret' not in str(audit) and 'private timeout' not in str(audit)

@pytest.mark.parametrize('changes,state',[
    ({},'ACCEPTED_BY_RULES'),({'candidate_columns':['hallucinated']},'REJECTED'),
    ({'metric':'regression'},'REJECTED'),({'mapping_confidence':.1},'UNRESOLVED'),
    ({'candidate_columns':['y']},'UNRESOLVED'),({'claim_id':'invented'},'REJECTED')])
def test_proposals(changes,state):
    audit=augment(CLAIMS,['x','y'],['PUBLIC'],provider(lambda r:httpx.Response(200,json={'mappings':[mapping(**changes)]})))
    assert audit['result'][0]['status']==state

def test_disabled_and_private_policy():
    assert augment(CLAIMS,['x'],['PRIVATE'],DisabledAIProvider())['status']=='NOT_RUN'
    def unexpected(request): raise AssertionError('Private metadata must not leave the application')
    assert augment(CLAIMS,['x'],['PRIVATE'],provider(unexpected))['failure_reason']=='PRIVATE_PROCESSING_NOT_ENABLED'
    assert augment(CLAIMS,['x'],['PRIVATE'],DeterministicFallbackProvider())['status']=='COMPLETED'

def test_ai_failure_preserves_persisted_science(client,monkeypatch):
    def timeout(request): raise httpx.ReadTimeout('timeout',request=request)
    monkeypatch.setattr('packages.ai.semantic.configured_provider',lambda:provider(timeout))
    monkeypatch.setenv('AI_ALLOW_PRIVATE','true')
    sign_in(client);vid=version(client);upload_evidence(client,vid)
    report=client.post(f'/versions/{vid}/verify').json()
    assert report['job_status']=='COMPLETED' and report['checks'][0]['outcome']=='SUPPORTED'
    assert report['ai']['semantic']['failure_reason']=='PROVIDER_TIMEOUT'
    assert report['provenance']['provenance_hash']
    assert client.get('/runs/'+report['id']).json()['ai']['semantic']==report['ai']['semantic']

def test_gateway_request_is_minimal():
    import json
    def respond(request):
        body=json.loads(request.content)
        assert body['operation']=='map_claim_to_dataset'
        assert body['input']['claims']==[{'claim_id':'claim-1','metric':'mean','columns':['x']}]
        assert 'reported_value' not in request.content.decode()
        return httpx.Response(200,json={'mappings':[]})
    assert augment(CLAIMS,['x'],['PUBLIC'],provider(respond))['status']=='COMPLETED'
