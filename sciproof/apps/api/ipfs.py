"""Explicit provider-backed public publication, never automatic artifact storage."""
import base64
import hashlib
import json
import os
from typing import Protocol
import httpx

def valid_cid(cid):
    """Accept canonical CIDv0 or base32 CIDv1, SHA-256 dag-pb/raw only."""
    if not isinstance(cid,str) or len(cid)>120: return False
    try:
        if cid.startswith('Qm') and len(cid)==46:
            alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';number=0
            for c in cid: number=number*58+alphabet.index(c)
            decoded=number.to_bytes((number.bit_length()+7)//8,'big')
            return len(decoded)==34 and decoded[:2]==b'\x12\x20'
        if cid.startswith('b') and cid==cid.lower():
            encoded=cid[1:];raw=base64.b32decode(encoded.upper()+'='*((-len(encoded))%8))
            canonical='b'+base64.b32encode(raw).decode().lower().rstrip('=')
            return canonical==cid and len(raw)==36 and raw[0]==1 and raw[1] in (0x55,0x70) and raw[2:4]==b'\x12\x20'
    except (ValueError,TypeError): return False
    return False

class IPFSStorage(Protocol):
    identifier:str
    def publish(self,raw:bytes,sha256:str)->str: ...

class PinataStorage:
    identifier='pinata'
    def __init__(self,token,transport=None):
        if not token: raise ValueError('PINATA_JWT required')
        self.token=token;self.transport=transport
    def publish(self,raw,sha256):
        if hashlib.sha256(raw).hexdigest()!=sha256: raise ValueError('Artifact hash mismatch before publication')
        with httpx.Client(timeout=30,transport=self.transport,follow_redirects=False) as client:
            response=client.post('https://api.pinata.cloud/pinning/pinFileToIPFS',
                headers={'Authorization':'Bearer '+self.token},files={'file':('artifact',raw,'application/octet-stream')},
                data={'pinataOptions':json.dumps({'cidVersion':1})})
            response.raise_for_status()
            if len(response.content)>16384: raise ValueError('Invalid publication receipt')
            cid=response.json().get('IpfsHash')
        if not valid_cid(cid): raise ValueError('Invalid returned CID')
        return cid

def configured_publisher():
    if os.getenv('IPFS_ENABLED','false')!='true': return None
    if os.getenv('IPFS_PROVIDER','pinata')!='pinata': raise ValueError('Unsupported IPFS_PROVIDER')
    return PinataStorage(os.getenv('PINATA_JWT',''))
