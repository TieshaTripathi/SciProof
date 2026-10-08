import base64
import hashlib
import io
import uuid
import httpx
import pytest
from cryptography.fernet import Fernet
from botocore.exceptions import ClientError
from apps.api.storage_providers import S3CompatibleStorage
from apps.api.ipfs import PinataStorage, valid_cid
from tests.test_api import sign_in, version

CID='b'+base64.b32encode(b'\x01\x70\x12\x20'+b'a'*32).decode().lower().rstrip('=')
class MemoryS3:
    """Injected S3 request boundary; no credentials or network."""
    def __init__(self): self.objects={}
    def put_object(self,**request):
        key=request['Key']
        assert request['IfNoneMatch']=='*'
        if key in self.objects: raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
        self.objects[key]=request
    def get_object(self,**request): return {'Body':io.BytesIO(self.objects[request['Key']]['Body'])}
    def head_object(self,**request):
        if request['Key'] not in self.objects: raise ClientError({'Error':{'Code':'404'}},'HeadObject')
        obj=self.objects[request['Key']]
        return {'ContentLength':len(obj['Body']),'Metadata':obj['Metadata']}
    def delete_object(self,**request): self.objects.pop(request['Key'],None)

def test_s3_encryption_immutability_hash_and_stream():
    client=MemoryS3();storage=S3CompatibleStorage(client,'test-bucket',Fernet.generate_key())
    reference=str(uuid.uuid4());raw=b'private evidence';digest=hashlib.sha256(raw).hexdigest()
    assert not storage.exists(reference)
    storage.put(reference,raw)
    assert raw not in client.objects['artifacts/'+reference]['Body']
    assert storage.exists(reference) and storage.get(reference,digest)==raw
    assert b''.join(storage.stream(reference,digest))==raw
    assert storage.metadata(reference)['metadata']['sha256']==digest
    with pytest.raises(ClientError): storage.put(reference,b'replacement')
    with pytest.raises(ValueError): storage.get(reference,'0'*64)
    storage.allow_delete=False
    with pytest.raises(PermissionError): storage.delete(reference)
    storage.allow_delete=True;storage.delete(reference);assert not storage.exists(reference)
    with pytest.raises(ValueError): storage.object_key('../../private')

@pytest.mark.parametrize('cid',['https://gateway.example/ipfs/'+CID,'bINVALID','Qm'+'0'*44,'',None])
def test_invalid_cid(cid): assert not valid_cid(cid)

def test_pinata_request_and_receipt():
    raw=b'public bytes';digest=hashlib.sha256(raw).hexdigest()
    def respond(request):
        assert request.headers['authorization']=='Bearer token'
        assert raw in request.content
        assert 'pinFileToIPFS' in str(request.url)
        return httpx.Response(200,json={'IpfsHash':CID})
    adapter=PinataStorage('token',httpx.MockTransport(respond))
    assert valid_cid(CID) and adapter.publish(raw,digest)==CID
    with pytest.raises(ValueError): adapter.publish(raw,'0'*64)

def test_private_policy_public_action_and_persistence(client):
    class Publisher:
        identifier='injected-pinata';calls=0
        def publish(self,raw,digest):
            assert hashlib.sha256(raw).hexdigest()==digest
            self.calls+=1;return CID
    publisher=Publisher();client.app.state.publisher=publisher
    sign_in(client)
    for visibility in ('PRIVATE','RESTRICTED','PUBLIC'):
        vid=version(client)
        artifact=client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n1')},data={'visibility':visibility}).json()
        aid=artifact['id']
        assert client.get(f'/artifacts/{aid}/publication').json()['status']=='NOT_PUBLISHED'
        assert publisher.calls==0
        result=client.post(f'/artifacts/{aid}/publish',json={'confirm_publication':True})
        if visibility!='PUBLIC': assert result.status_code==403
        else:
            assert result.status_code==200 and result.json()['status']=='PUBLISHED'
            assert result.json()['artifact_hash']==artifact['sha256'] and result.json()['published_at']
            assert client.post(f'/artifacts/{aid}/publish',json={'confirm_publication':True}).json()['cid']==CID
    assert publisher.calls==1
    client.post('/auth/logout')
    sign_in(client,email='other@example.org')
    assert client.post(f'/artifacts/{aid}/publish',json={'confirm_publication':True}).status_code==404
    assert client.get(f'/artifacts/{aid}/publication').status_code==404

def test_bad_receipt_records_failure_without_changing_hash(client):
    class BadPublisher:
        identifier='bad';
        def publish(self,raw,digest): return 'fake-cid'
    client.app.state.publisher=BadPublisher();sign_in(client);vid=version(client)
    a=client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n1')},data={'visibility':'PUBLIC'}).json()
    result=client.post(f"/artifacts/{a['id']}/publish",json={'confirm_publication':True})
    assert result.status_code==502 and result.json()['status']=='FAILED'
    assert result.json()['cid'] is None and result.json()['artifact_hash']==a['sha256']
    assert client.get(f'/versions/{vid}/artifacts').json()[0]['sha256']==a['sha256']
