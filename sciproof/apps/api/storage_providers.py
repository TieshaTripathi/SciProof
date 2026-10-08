"""Encrypted storage adapters; publication is a separate explicit capability."""
import hashlib
import os
import uuid
from typing import Protocol, Iterator
from cryptography.fernet import Fernet
from apps.api.storage import LocalEncryptedStorage, MAX_BYTES

class ArtifactStorage(Protocol):
    backend:str
    def put(self,reference:str,raw:bytes): ...
    def get(self,reference:str,expected_hash:str)->bytes: ...
    def delete(self,reference:str): ...
    def exists(self,reference:str)->bool: ...
    def metadata(self,reference:str)->dict: ...
    def stream(self,reference:str,expected_hash:str)->Iterator[bytes]: ...

class S3CompatibleStorage:
    backend='s3_encrypted'
    def __init__(self,client,bucket,key,prefix='artifacts/',allow_delete=True):
        if not bucket or not key: raise ValueError('S3 bucket and encryption key required')
        self.client=client;self.bucket=bucket;self.cipher=Fernet(key);self.prefix=prefix;self.allow_delete=allow_delete
    def object_key(self,reference):
        if str(uuid.UUID(reference))!=reference: raise ValueError('Invalid storage reference')
        return self.prefix+reference
    def put(self,reference,raw):
        if len(raw)>MAX_BYTES: raise ValueError('Artifact exceeds storage limit')
        self.client.put_object(Bucket=self.bucket,Key=self.object_key(reference),Body=self.cipher.encrypt(raw),
            ContentType='application/octet-stream',IfNoneMatch='*',
            Metadata={'sha256':hashlib.sha256(raw).hexdigest(),'plaintext-size':str(len(raw)),'encryption':'fernet'})
    def get(self,reference,expected_hash):
        response=self.client.get_object(Bucket=self.bucket,Key=self.object_key(reference))
        body=response['Body']
        try:
            ciphertext=body.read(2*MAX_BYTES+1)
            if len(ciphertext)>2*MAX_BYTES: raise ValueError('Encrypted object exceeds storage limit')
            raw=self.cipher.decrypt(ciphertext)
        finally: body.close()
        if len(raw)>MAX_BYTES or hashlib.sha256(raw).hexdigest()!=expected_hash: raise ValueError('Artifact hash/size mismatch')
        return raw
    def delete(self,reference):
        if not self.allow_delete: raise PermissionError('Storage deletion policy forbids deletion')
        self.client.delete_object(Bucket=self.bucket,Key=self.object_key(reference))
    def exists(self,reference):
        try: self.metadata(reference);return True
        except Exception as error:
            if getattr(error,'response',{}).get('Error',{}).get('Code') in ('404','NoSuchKey','NotFound'): return False
            raise
    def metadata(self,reference):
        response=self.client.head_object(Bucket=self.bucket,Key=self.object_key(reference))
        return {'backend':self.backend,'encrypted_size':response['ContentLength'],'metadata':response.get('Metadata',{})}
    def stream(self,reference,expected_hash):
        # Fernet must authenticate the complete object before releasing any plaintext.
        raw=self.get(reference,expected_hash)
        for offset in range(0,len(raw),65536): yield raw[offset:offset+65536]

def configured_storage():
    backend=os.getenv('STORAGE_BACKEND','local_encrypted')
    if backend=='local_encrypted': return LocalEncryptedStorage()
    if backend!='s3_encrypted': raise ValueError('Unknown STORAGE_BACKEND')
    import boto3
    from botocore.config import Config
    client=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,
        region_name=os.getenv('S3_REGION','us-east-1'),config=Config(connect_timeout=5,read_timeout=15,retries={'max_attempts':1}))
    return S3CompatibleStorage(client,os.getenv('S3_BUCKET',''),os.getenv('STORAGE_ENCRYPTION_KEY',''))
