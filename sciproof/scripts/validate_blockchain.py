"""Actual ephemeral Anvil chain, preserved registry and authenticated API flow."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from web3 import Web3
from fastapi.testclient import TestClient
from apps.api.blockchain import LocalDevAttestationProvider, ABI, compact_inputs
from apps.api.main import create_app
from apps.api.database import make_database
from apps.api.models import Base
from apps.api.storage import LocalEncryptedStorage
from tests.test_api import sign_in, version
from tests.test_runs import upload_evidence

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--anvil',required=True);args=parser.parse_args()
    with socket.socket() as socket_probe:
        socket_probe.bind(('127.0.0.1',0));port=socket_probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='sciproof-chain-') as folder:
        log=Path(folder)/'anvil.log'
        with log.open('w') as output:
            process=subprocess.Popen([args.anvil,'--host','127.0.0.1','--port',str(port),'--silent'],stdout=output,stderr=output)
            try:
                w3=Web3(Web3.HTTPProvider(f'http://127.0.0.1:{port}'))
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    try:
                        if w3.is_connected(): break
                    except Exception: pass
                    time.sleep(.1)
                assert w3.is_connected()
                # Fresh random signer; fund from Anvil's unlocked ephemeral development account.
                signer=w3.eth.account.create()
                funding=w3.eth.send_transaction({'from':w3.eth.accounts[0],'to':signer.address,'value':w3.to_wei(10,'ether')})
                w3.eth.wait_for_transaction_receipt(funding)
                artifact=json.loads(Path('packages/contracts/out/SciProofRegistry.sol/SciProofRegistry.json').read_text(encoding='utf-8'))
                factory=w3.eth.contract(abi=ABI,bytecode=artifact['bytecode']['object'])
                deployed=w3.eth.wait_for_transaction_receipt(factory.constructor(signer.address).transact({'from':w3.eth.accounts[0]}))
                provider=LocalDevAttestationProvider(f'http://127.0.0.1:{port}',31337,deployed['contractAddress'],signer.key,3,web3=w3)
                url='sqlite:///'+str(Path(folder)/'test.sqlite')
                engine,_=make_database(url);Base.metadata.create_all(engine);engine.dispose()
                app=create_app(url,LocalEncryptedStorage(Path(folder)/'artifacts'),'inline');app.state.attestor=provider
                with TestClient(app) as client:
                    sign_in(client);vid=version(client);upload_evidence(client,vid)
                    report=client.post(f'/versions/{vid}/verify').json();rid=report['id']
                    assert client.get(f'/runs/{rid}/attestation').json()['status']=='NOT_REQUESTED'
                    consent={'confirm_attestation':True,'researcher_address':w3.eth.accounts[1]}
                    pre_transaction_snapshot=w3.provider.make_request('evm_snapshot',[])['result']
                    submitted=client.post(f'/runs/{rid}/attestation',json=consent)
                    assert submitted.status_code==202,submitted.text
                    transaction=submitted.json()['transaction_hash']
                    assert transaction and w3.eth.get_transaction_receipt(transaction)['status']==1
                    assert client.post(f'/runs/{rid}/attestation/refresh').json()['status']=='SUBMITTED'
                    snapshot=w3.provider.make_request('evm_snapshot',[])['result']
                    w3.provider.make_request('anvil_mine',['0x2'])
                    confirmed=client.post(f'/runs/{rid}/attestation/refresh').json()
                    assert confirmed['status']=='CONFIRMED' and confirmed['block_number'] and confirmed['block_hash'] and confirmed['attested_at']
                    # Revert confirmation depth, then refresh actual canonical state.
                    assert w3.provider.make_request('evm_revert',[snapshot])['result']
                    reverted=client.post(f'/runs/{rid}/attestation/refresh').json()
                    assert reverted['status']=='SUBMITTED' and reverted['block_number'] is None
                    assert client.get('/runs/'+rid).json()['provenance']==report['provenance']
                    assert client.post(f'/runs/{rid}/attestation',json=consent).json()['transaction_hash']==transaction
                    assert w3.provider.make_request('evm_revert',[pre_transaction_snapshot])['result']
                    assert client.post(f'/runs/{rid}/attestation/refresh').json()['status']=='PENDING'
                    rebroadcast=client.post(f'/runs/{rid}/attestation',json=consent).json()
                    assert rebroadcast['status']=='SUBMITTED' and rebroadcast['transaction_hash']==transaction
                    assert w3.eth.get_transaction_receipt(transaction)['status']==1
                app.state.engine.dispose()
                result={'runtime':'Anvil local EVM','chain_id':31337,'contract_deployed':True,
                        'actual_transaction_receipt':True,'confirmations_required':3,
                        'confirmation_depth_enforced':True,'confirmation_rollback_detected':True,
                        'scientific_report_preserved':True,'receipt_removal_detected':True,'same_signed_transaction_rebroadcast':True}
                Path('docs/blockchain-validation-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                print(json.dumps(result))
            finally:
                process.terminate();process.wait(timeout=15)
    return 0
if __name__=='__main__': raise SystemExit(main())
