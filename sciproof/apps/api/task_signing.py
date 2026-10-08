"""Domain-separated HMAC envelope; JSON serialization is not authentication."""
import hashlib
import hmac
import os
from pathlib import Path
import uuid

def signing_key():
    explicit=os.getenv('TASK_SIGNING_KEY')
    if explicit:
        if len(explicit)<32: raise ValueError('TASK_SIGNING_KEY must have at least 32 characters')
        return explicit.encode()
    encryption=os.getenv('STORAGE_ENCRYPTION_KEY')
    if not encryption:
        from apps.api.storage_providers import configured_storage
        storage=configured_storage()
        encryption=(storage.root/'.key').read_bytes()
    if isinstance(encryption,str): encryption=encryption.encode()
    return hashlib.sha256(b'sciproof-task-key-v1\0'+encryption).digest()

def sign_task(run_id):
    if str(uuid.UUID(run_id))!=run_id: raise ValueError('Invalid task run identifier')
    return hmac.new(signing_key(),b'sciproof.verify.v1\0'+run_id.encode(),hashlib.sha256).hexdigest()
def valid_task(run_id,signature):
    try: return isinstance(signature,str) and len(signature)==64 and hmac.compare_digest(sign_task(run_id),signature)
    except (ValueError,TypeError): return False
