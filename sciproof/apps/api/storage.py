"""Private encrypted storage. Visibility never implies public publication."""
import csv
import hashlib
import io
import json
import os
import re
import uuid
from pathlib import Path
from cryptography.fernet import Fernet
import pandas as pd
from pypdf import PdfReader

FORMATS={
    'MANUSCRIPT':{'.pdf':'application/pdf'},
    'DATASET':{'.csv':'text/csv','.json':'application/json','.parquet':'application/vnd.apache.parquet'},
    'ANALYSIS_CODE':{'.py':'text/x-python','.ipynb':'application/x-ipynb+json'},
}
MAX_BYTES=20*1024*1024
def validate(filename,kind,raw):
    if not filename or len(filename)>200 or any(c in filename for c in ('/','\\','\x00')) or '..' in filename or ':' in filename:
        raise ValueError('Unsafe filename')
    suffix=Path(filename).suffix.lower()
    mime=FORMATS.get(kind,{}).get(suffix)
    if not mime: raise ValueError('Unsupported format')
    if not raw: raise ValueError('Empty file')
    if len(raw)>MAX_BYTES: raise ValueError('20 MB maximum')
    if suffix=='.pdf':
        if not raw.startswith(b'%PDF-'): raise ValueError('Invalid PDF signature')
        reader=PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages)>1000: raise ValueError('Encrypted or oversized PDF')
    elif suffix=='.parquet':
        if not raw.startswith(b'PAR1') or not raw.endswith(b'PAR1'): raise ValueError('Invalid Parquet signature')
        import pyarrow.parquet as pq
        metadata=pq.ParquetFile(io.BytesIO(raw)).metadata
        if metadata.num_rows>1_000_000 or metadata.num_columns>1000: raise ValueError('Expanded dataset exceeds limits')
        if sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))>200*1024*1024: raise ValueError('Expanded Parquet exceeds limit')
    elif suffix in ('.json','.ipynb'):
        data=bounded_json(raw)
        if suffix=='.ipynb' and (not isinstance(data,dict) or not isinstance(data.get('cells'),list) or data.get('nbformat')!=4): raise ValueError('Invalid notebook')
        if suffix=='.json': read_dataset(raw,suffix)
    else:
        raw.decode('utf-8')
        if b'\x00' in raw: raise ValueError('Binary content rejected')
        if suffix=='.csv': read_dataset(raw,suffix)
    sanitized=re.sub(r'[^A-Za-z0-9._-]','_',filename)
    return dict(filename=filename,sanitized_filename=sanitized,mime_type=mime,
                size=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def bounded_json(raw):
    # Bound nesting before the JSON decoder or DataFrame conversion allocates structures.
    text=raw.decode('utf-8');depth=0;quoted=False;escaped=False
    for character in text:
        if quoted:
            if escaped: escaped=False
            elif character=='\\': escaped=True
            elif character=='"': quoted=False
        elif character=='"': quoted=True
        elif character in '[{':
            depth+=1
            if depth>64: raise ValueError('JSON nesting exceeds limit')
        elif character in ']}': depth-=1
    return json.loads(text)

def read_dataset(raw,suffix):
    if len(raw)>MAX_BYTES: raise ValueError('Dataset exceeds byte limit')
    source=io.BytesIO(raw)
    if suffix=='.csv':
        header=next(csv.reader(io.StringIO(raw.decode('utf-8-sig'))),[])
        if not header or len(header)>1000 or len(set(header))!=len(header): raise ValueError('Unique bounded dataset columns required')
        df=pd.read_csv(source,nrows=1_000_001)
    elif suffix=='.json':
        decoded=bounded_json(raw)
        if not isinstance(decoded,(dict,list)): raise ValueError('Tabular JSON required')
        if isinstance(decoded,list) and len(decoded)>1_000_000: raise ValueError('JSON row limit exceeded')
        if isinstance(decoded,dict) and len(decoded)>1000: raise ValueError('JSON column limit exceeded')
        df=pd.read_json(source)
    elif suffix=='.parquet':
        import pyarrow.parquet as pq
        metadata=pq.ParquetFile(source).metadata
        if metadata.num_rows>1_000_000 or metadata.num_columns>1000 or sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))>200*1024*1024:
            raise ValueError('Expanded Parquet exceeds limit')
        source.seek(0);df=pd.read_parquet(source)
    else: raise ValueError('Unsupported dataset format')
    if len(df)>1_000_000 or len(df.columns)>1000: raise ValueError('Dataset dimensions exceed limits')
    if not len(df.columns) or not df.columns.is_unique: raise ValueError('Unique dataset columns required')
    df.columns=[str(c) for c in df.columns]
    if not df.columns.is_unique: raise ValueError('Ambiguous dataset columns')
    return df

class LocalEncryptedStorage:
    backend='local_encrypted'
    def __init__(self,root=None,key=None):
        self.root=Path(root or os.getenv('STORAGE_ROOT','private-artifacts')).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        key=key or os.getenv('STORAGE_ENCRYPTION_KEY')
        if not key:
            if os.getenv('APP_ENV','development')!='development': raise RuntimeError('STORAGE_ENCRYPTION_KEY is required outside development')
            keyfile=self.root/'.key'
            try:
                with keyfile.open('xb') as f: f.write(Fernet.generate_key())
                keyfile.chmod(0o600)
            except FileExistsError: pass
            key=keyfile.read_bytes()
        self.cipher=Fernet(key)
    def path(self,reference):
        if str(uuid.UUID(reference))!=reference: raise ValueError('Invalid storage reference')
        return self.root/reference
    def put(self,reference,raw):
        path=self.path(reference)
        created=False
        try:
            with path.open('xb') as f:
                created=True
                f.write(self.cipher.encrypt(raw))
            path.chmod(0o600)
        except Exception:
            if created: path.unlink(missing_ok=True)
            raise
    def get(self,reference,expected_hash):
        raw=self.cipher.decrypt(self.path(reference).read_bytes())
        if hashlib.sha256(raw).hexdigest()!=expected_hash: raise ValueError('Artifact hash mismatch')
        return raw
    def delete(self,reference): self.path(reference).unlink(missing_ok=True)

    def exists(self,reference): return self.path(reference).is_file()
    def metadata(self,reference):
        return {'backend':self.backend,'encrypted_size':self.path(reference).stat().st_size,'encryption':'fernet'}
    def stream(self,reference,expected_hash):
        raw=self.get(reference,expected_hash)
        for offset in range(0,len(raw),65536): yield raw[offset:offset+65536]
