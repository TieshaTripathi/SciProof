"""Isolate upload parsing with a wall-clock deadline and Linux resource limits."""
import json
import os
import subprocess
import sys
from apps.api.storage import MAX_BYTES

def isolated_validate(filename,kind,raw):
    if len(raw)>MAX_BYTES: raise ValueError('Artifact exceeds upload limit')
    header=json.dumps({'filename':filename,'kind':kind}).encode()
    if len(header)>4096: raise ValueError('Invalid upload metadata')
    environment=os.environ.copy()
    environment.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    # Parser children need neither signing credentials nor optional-provider credentials.
    for name in ('BLOCKCHAIN_PRIVATE_KEY','AI_API_TOKEN','PINATA_JWT','AWS_ACCESS_KEY_ID',
                 'AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','STORAGE_ENCRYPTION_KEY','TASK_SIGNING_KEY',
                 'DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD','REDIS_PASSWORD'):
        environment.pop(name,None)
    result=subprocess.run([sys.executable,'-m','apps.api.artifact_validator'],
        input=len(header).to_bytes(4,'big')+header+raw,capture_output=True,timeout=25,env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode!=0 or len(result.stdout)>8192: raise ValueError('Artifact parser rejected input')
    return json.loads(result.stdout)
