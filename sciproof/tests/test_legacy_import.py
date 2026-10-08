import hashlib
import json
import sqlite3
import uuid
from cryptography.fernet import Fernet
from sqlalchemy import select
from apps.api.database import make_database
from apps.api.models import Base,User,ResearchArtifact,ResearchVersion,VersionState
from apps.api.storage import LocalEncryptedStorage
from scripts.import_legacy import import_legacy

def test_legacy_import_preserves_identity_hashes_and_snapshots(tmp_path):
    ids=[str(uuid.uuid4()) for _ in range(5)];u,p,v,a,r=ids
    source=tmp_path/'source';source.mkdir();key=Fernet.generate_key();(source/'.key').write_bytes(key)
    raw=b'x\n1\n2';(source/a).write_bytes(Fernet(key).encrypt(raw));sha=hashlib.sha256(raw).hexdigest()
    dbpath=tmp_path/'legacy.db'
    rows=[(u,'user','','r@example.org',{'password_hash':'retained-hash'}),
          (p,'project',u,None,{'title':'Original research'}),(v,'version',u,p,{'created_at':'2026-01-01'}),
          (a,'artifact',u,v,{'kind':'dataset','filename':'data.csv','sha256':sha,'visibility':'PRIVATE'}),
          (r,'run',u,v,{'status':'INSUFFICIENT_EVIDENCE','provenance':{'provenance_hash':'original'}})]
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE records(id TEXT,kind TEXT,owner TEXT,parent TEXT,payload TEXT)')
        db.executemany('INSERT INTO records VALUES(?,?,?,?,?)',[(i,k,o,pa,json.dumps(data)) for i,k,o,pa,data in rows])
    original=dbpath.read_bytes()
    engine,sessions=make_database('sqlite:///'+str(tmp_path/'new.sqlite'));Base.metadata.create_all(engine)
    target=LocalEncryptedStorage(tmp_path/'target')
    assert import_legacy(dbpath,source,sessions,target)['encrypted_objects']==2
    assert dbpath.read_bytes()==original
    with sessions() as db:
        assert db.get(User,u).password_hash=='retained-hash'
        assert db.get(ResearchVersion,v).state==VersionState.SEALED
        assert target.get(db.get(ResearchArtifact,a).storage_reference,sha)==raw
        reports=[x for x in db.scalars(select(ResearchArtifact)) if x.id!=a]
        snapshot=json.loads(target.get(reports[0].storage_reference,reports[0].sha256))
        assert snapshot[0]['legacy_run_id']==r and snapshot[0]['provenance']['provenance_hash']=='original'
    engine.dispose()
