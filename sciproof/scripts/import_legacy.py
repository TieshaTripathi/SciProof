"""Non-destructive legacy import into an empty migrated database.

Run with python -m scripts.import_legacy SOURCE_DB SOURCE_ARTIFACTS.
Old reports are preserved as encrypted REPORT artifacts, not reclassified as
results of the new engine. Sessions are intentionally not transferred.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from cryptography.fernet import Fernet
from sqlalchemy import select, func
from apps.api.database import make_database
from apps.api.models import *
from apps.api.storage import LocalEncryptedStorage, validate

def import_legacy(source_db,source_root,sessions,target_storage,source_key=None):
    source_db=Path(source_db).resolve();source_root=Path(source_root).resolve()
    if source_root==target_storage.root: raise ValueError('Source and destination storage must differ')
    cipher=Fernet(source_key or (source_root/'.key').read_bytes())
    with sqlite3.connect(source_db.as_uri()+'?mode=ro',uri=True) as legacy:
        rows=legacy.execute('SELECT id,kind,owner,parent,payload FROM records ORDER BY rowid').fetchall()
    grouped={}
    for rid,kind,owner,parent,payload in rows:
        grouped.setdefault(kind,[]).append((rid,owner,parent,json.loads(payload)))
    written=[]
    try:
        with sessions.begin() as db:
            if db.scalar(select(func.count()).select_from(User)): raise ValueError('Import requires an empty destination database')
            for rid,owner,email,payload in grouped.get('user',[]):
                db.add(User(id=rid,email=email,password_hash=payload['password_hash']))
            db.flush()
            for rid,owner,parent,payload in grouped.get('project',[]):
                db.add(ResearchProject(id=rid,owner_id=owner,title=payload['title']))
            db.flush()
            counts={}
            for rid,owner,parent,payload in sorted(grouped.get('version',[]),key=lambda r:r[3].get('created_at','')):
                counts[parent]=counts.get(parent,0)+1
                sealed=any(r[2]==rid for r in grouped.get('run',[]))
                db.add(ResearchVersion(id=rid,project_id=parent,version_number=counts[parent],state=VersionState.SEALED if sealed else VersionState.DRAFT))
            db.flush()
            kinds={'manuscript':ArtifactType.MANUSCRIPT,'dataset':ArtifactType.DATASET,'analysis':ArtifactType.ANALYSIS_CODE}
            seen=set()
            for rid,owner,vid,payload in grouped.get('artifact',[]):
                key=(vid,payload['kind'])
                if key in seen: raise ValueError('Legacy duplicate artifact types require manual reconciliation; source unchanged')
                seen.add(key)
                raw=cipher.decrypt((source_root/str(uuid.UUID(rid))).read_bytes())
                if hashlib.sha256(raw).hexdigest()!=payload['sha256']: raise ValueError('Legacy artifact checksum mismatch')
                kind=kinds[payload['kind']];metadata=validate(payload['filename'],kind.value,raw)
                target_storage.put(rid,raw);written.append(rid)
                db.add(ResearchArtifact(id=rid,research_version_id=vid,artifact_type=kind,visibility=Visibility(payload.get('visibility','PRIVATE')),storage_reference=rid,**metadata))
                db.flush()
                subtype=Manuscript if kind==ArtifactType.MANUSCRIPT else Dataset if kind==ArtifactType.DATASET else AnalysisCode
                db.add(subtype(artifact_id=rid))
            snapshots={}
            for rid,owner,vid,payload in grouped.get('run',[]): snapshots.setdefault(vid,[]).append({'legacy_run_id':rid,**payload})
            for vid,reports in snapshots.items():
                raw=json.dumps(reports,sort_keys=True,allow_nan=False).encode();rid=uid()
                target_storage.put(rid,raw);written.append(rid)
                db.add(ResearchArtifact(id=rid,research_version_id=vid,artifact_type=ArtifactType.REPORT,visibility=Visibility.RESTRICTED,
                    filename='legacy-verification-reports.json',sanitized_filename='legacy-verification-reports.json',mime_type='application/json',
                    size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),storage_reference=rid))
        return {'users':len(grouped.get('user',[])),'projects':len(grouped.get('project',[])),
                'versions':len(grouped.get('version',[])),'encrypted_objects':len(written)}
    except Exception:
        for reference in written: target_storage.delete(reference)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_db');parser.add_argument('source_artifacts');parser.add_argument('--source-key-file')
    args=parser.parse_args();engine,sessions=make_database()
    try:
        key=Path(args.source_key_file).read_bytes() if args.source_key_file else None
        print(json.dumps(import_legacy(args.source_db,args.source_artifacts,sessions,LocalEncryptedStorage(),key)))
    finally: engine.dispose()
