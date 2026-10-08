from sqlalchemy import select
from apps.api.models import BlockchainAttestation, VerificationRun
from tests.test_api import sign_in, version
from tests.test_runs import upload_evidence

ADDRESS='0x'+'1'*40
def completed(client):
    sign_in(client);vid=version(client);upload_evidence(client,vid)
    return client.post(f'/versions/{vid}/verify').json()['id']
def test_disabled_independent_and_owned(client):
    rid=completed(client)
    assert client.get(f'/runs/{rid}/attestation').json()['status']=='NOT_REQUESTED'
    assert client.post(f'/runs/{rid}/attestation',json={'confirm_attestation':True,'researcher_address':ADDRESS}).status_code==503
    assert client.get('/runs/'+rid).json()['job_status']=='COMPLETED'
    client.post('/auth/logout');sign_in(client,email='other-chain@example.org')
    assert client.get(f'/runs/{rid}/attestation').status_code==404
    assert client.post(f'/runs/{rid}/attestation/refresh').status_code==404

def test_preparation_failure_is_not_chain_success(client):
    class Unavailable:
        chain_id=31337;contract_address=ADDRESS;signer_address=ADDRESS;confirmations_required=3
        def prepare(self,*args): raise ConnectionError('Secret RPC details')
    rid=completed(client);client.app.state.attestor=Unavailable()
    result=client.post(f'/runs/{rid}/attestation',json={'confirm_attestation':True,'researcher_address':ADDRESS})
    assert result.status_code==502 and result.json()['status']=='FAILED'
    assert result.json()['transaction_hash'] is None
    assert 'Secret' not in result.text
    assert client.get('/runs/'+rid).json()['checks'][0]['outcome']=='SUPPORTED'

def test_refresh_unavailable_cannot_certify_current_confirmation(client):
    class Unavailable:
        chain_id=31337;contract_address=ADDRESS
        def inspect(self,*args): raise ConnectionError('offline')
    rid=completed(client);client.app.state.attestor=Unavailable()
    with client.app.state.sessions.begin() as db:
        a=db.scalar(select(BlockchainAttestation));a.status='CONFIRMED';a.chain_id=31337
        a.contract_address=ADDRESS;a.transaction_hash='0x'+'2'*64;a.researcher_address=ADDRESS
        a.confirmations_required=3;a.block_number=10;a.block_hash='0x'+'3'*64
    result=client.post(f'/runs/{rid}/attestation/refresh')
    assert result.status_code==503 and result.json()['status']=='SUBMITTED'
    assert result.json()['block_number'] is None
    assert client.get('/runs/'+rid).json()['attestation']['status']=='SUBMITTED'
    with client.app.state.sessions() as db:
        assert db.get(VerificationRun,rid).scientific_report['attestation']['status']=='NOT_REQUESTED'
