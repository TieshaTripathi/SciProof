"""Optional attestation: signed bytes, actual broadcast, canonical receipts."""
import hashlib
import json
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from web3 import Web3
from web3.exceptions import TransactionNotFound
from packages.verification.engine import canonical_hash

ABI=json.loads((Path(__file__).resolve().parents[2]/'packages/contracts/registry.abi.json').read_text(encoding='utf-8'))
STATUS={'VERIFIED':0,'VERIFIED_WITH_WARNINGS':1,'NEEDS_REVIEW':2,'FAILED_VERIFICATION':3,'INSUFFICIENT_EVIDENCE':4}
def compact_inputs(report,researcher):
    manifest=report['provenance']['manifest']
    return [hashlib.sha256(manifest['research_id'].encode()).digest(),
            hashlib.sha256(manifest['version_id'].encode()).digest(),
            bytes.fromhex(report['provenance']['provenance_hash']),
            bytes.fromhex(canonical_hash([{'id':a['id'],'sha256':a['sha256']} for a in manifest['artifacts']])),
            Web3.to_checksum_address(researcher),round(report['scores']['overall_verification_confidence']*100),STATUS[report['status']]]

class BlockchainAttestationProvider(Protocol):
    chain_id:int
    contract_address:str
    confirmations_required:int
    def prepare(self,report,researcher,minimum_nonce=0): ...
    def submit(self,signed_transaction,expected_hash): ...
    def inspect(self,transaction_hash,report,researcher,confirmations_required): ...
class DisabledAttestationProvider:
    identifier='disabled'
    def prepare(self,*args,**kwargs): raise RuntimeError('Attestation disabled')
    def submit(self,*args): raise RuntimeError('Attestation disabled')
    def inspect(self,*args): return {'status':'NOT_REQUESTED'}

class EvmAttestationProvider:
    identifier='evm'
    def __init__(self,rpc,chain_id,contract_address,private_key,confirmations_required=3,web3=None):
        parsed=urlparse(rpc)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password: raise ValueError('Invalid BLOCKCHAIN_RPC_URL')
        if parsed.scheme=='http' and parsed.hostname not in ('localhost','127.0.0.1','::1'): raise ValueError('Remote RPC requires HTTPS')
        if chain_id<=0 or confirmations_required<1: raise ValueError('Invalid chain ID or confirmations')
        if not Web3.is_address(contract_address): raise ValueError('Invalid registry contract address')
        self.web3=web3 or Web3(Web3.HTTPProvider(rpc,request_kwargs={'timeout':10}))
        self.chain_id=chain_id;self.contract_address=Web3.to_checksum_address(contract_address)
        self.account=self.web3.eth.account.from_key(private_key);self.signer_address=self.account.address
        self.confirmations_required=confirmations_required
        self.contract=self.web3.eth.contract(address=self.contract_address,abi=ABI)
    def check_chain(self):
        if self.web3.eth.chain_id!=self.chain_id: raise ValueError('Unexpected RPC chain ID')
        if not self.web3.eth.get_code(self.contract_address): raise ValueError('Registry bytecode unavailable')
        if self.contract.functions.attestor().call()!=self.signer_address: raise ValueError('Signer is not registry attestor')
    def prepare(self,report,researcher,minimum_nonce=0):
        self.check_chain()
        inputs=compact_inputs(report,researcher)
        nonce=max(minimum_nonce,self.web3.eth.get_transaction_count(self.signer_address,'pending'))
        transaction=self.contract.functions.attest(*inputs).build_transaction({
            'from':self.signer_address,'nonce':nonce,'chainId':self.chain_id})
        signed=self.account.sign_transaction(transaction)
        return {'signed_transaction':Web3.to_hex(signed.raw_transaction),'transaction_hash':Web3.to_hex(signed.hash),'nonce':nonce}
    def submit(self,signed_transaction,expected_hash):
        self.check_chain()
        actual=Web3.to_hex(self.web3.eth.send_raw_transaction(bytes.fromhex(signed_transaction.removeprefix('0x'))))
        if actual!=expected_hash: raise ValueError('Unexpected broadcast hash')
        return actual
    def inspect(self,transaction_hash,report,researcher,confirmations_required):
        self.check_chain()
        try: receipt=self.web3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            try: self.web3.eth.get_transaction(transaction_hash)
            except TransactionNotFound: return {'status':'PENDING','block_number':None,'block_hash':None}
            return {'status':'SUBMITTED','block_number':None,'block_hash':None}
        if receipt['status']!=1: return {'status':'FAILED','error_code':'CHAIN_REVERTED','block_number':None,'block_hash':None}
        block=self.web3.eth.get_block(receipt['blockNumber'])
        if block['hash']!=receipt['blockHash']: return {'status':'SUBMITTED','block_number':None,'block_hash':None}
        transaction=self.web3.eth.get_transaction(transaction_hash)
        expected=compact_inputs(report,researcher)
        if transaction['to']!=self.contract_address or transaction['from']!=self.signer_address: raise ValueError('Unexpected attestation transaction')
        events=self.contract.events.Attested().process_receipt(receipt)
        if len(events)!=1 or any(events[0]['args'][key]!=value for key,value in zip(
            ('researchId','versionId','provenance','researcher'),(expected[0],expected[1],expected[2],expected[4]))):
            raise ValueError('Attestation event does not match provenance')
        key=Web3.keccak(self.web3.codec.encode(['bytes32','bytes32'],expected[:2]))
        record=self.contract.functions.records(key).call(block_identifier=receipt['blockNumber'])
        if record[0]!=expected[2] or record[1]!=expected[3] or record[2]!=expected[4] or list(record[4:])!=expected[5:]:
            raise ValueError('Registry record does not match report')
        depth=self.web3.eth.block_number-receipt['blockNumber']+1
        if depth<confirmations_required: return {'status':'SUBMITTED','block_number':None,'block_hash':None}
        return {'status':'CONFIRMED','block_number':receipt['blockNumber'],'block_hash':Web3.to_hex(receipt['blockHash']),
                'chain_timestamp':block['timestamp'],'error_code':None}

class LocalDevAttestationProvider(EvmAttestationProvider):
    identifier='local-dev'
    def check_chain(self):
        super().check_chain()
        if self.chain_id not in (31337,1337): raise ValueError('Local-dev provider requires a development chain')

def configured_attestor():
    if os.getenv('BLOCKCHAIN_ENABLED','false')!='true': return DisabledAttestationProvider()
    kind=os.getenv('BLOCKCHAIN_PROVIDER','evm')
    if kind not in ('evm','local-dev'): raise ValueError('Unknown BLOCKCHAIN_PROVIDER')
    cls=LocalDevAttestationProvider if kind=='local-dev' else EvmAttestationProvider
    return cls(os.getenv('BLOCKCHAIN_RPC_URL',''),int(os.getenv('BLOCKCHAIN_CHAIN_ID','0')),
        os.getenv('BLOCKCHAIN_CONTRACT_ADDRESS',''),os.getenv('BLOCKCHAIN_PRIVATE_KEY',''),
        int(os.getenv('BLOCKCHAIN_CONFIRMATIONS_REQUIRED','3')))
