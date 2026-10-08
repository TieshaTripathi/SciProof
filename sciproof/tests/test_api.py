import io
import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    from apps.api.main import create_app
    from apps.api.models import Base
    from apps.api.storage import LocalEncryptedStorage
    app=create_app('sqlite:///'+str(tmp_path/'db.sqlite'),LocalEncryptedStorage(tmp_path/'artifacts'),execution_mode='inline')
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as c: yield c
    app.state.engine.dispose()

def sign_in(c,email='research@example.org'):
    payload={'email':email,'password':'a-long-test-password'}
    assert c.post('/auth/signup',json=payload).status_code==200
    assert c.post('/auth/login',json=payload).status_code==200

def version(c):
    p=c.post('/projects',json={'title':'Test research'}).json()
    return c.post('/projects/'+p['id']+'/versions').json()['id']

def pdf(text):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer=PdfWriter(); page=writer.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject(); stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')]=writer._add_object(stream)
    result=io.BytesIO();writer.write(result);return result.getvalue()

def test_auth_required(client):
    assert client.get('/projects').status_code==401

def test_duplicate_account(client):
    sign_in(client)
    assert client.post('/auth/signup',json={'email':'research@example.org','password':'a-long-test-password'}).status_code==409

def test_upload_rejection(client):
    sign_in(client);vid=version(client)
    assert client.post(f'/versions/{vid}/artifacts/manuscript',files={'file':('paper.pdf',b'not a pdf','application/pdf')}).status_code==400
    assert client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('../data.csv',b'x\n1','text/csv')}).status_code==400

def test_complete_verification(client):
    sign_in(client);vid=version(client)
    assert client.post(f'/versions/{vid}/artifacts/manuscript',files={'file':('paper.pdf',pdf('mean of x = 2'),'application/pdf')}).status_code==200
    assert client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n1\n2\n3','text/csv')}).status_code==200
    response=client.post(f'/versions/{vid}/verify')
    assert response.status_code==200,response.text
    report=response.json()
    assert report['checks'][0]['outcome']=='SUPPORTED'
    assert report['attestation']['transaction_hash'] is None
    assert len(report['provenance']['provenance_hash'])==64
    assert client.post(f'/versions/{vid}/artifacts/dataset',files={'file':('data.csv',b'x\n4','text/csv')}).status_code==409

def test_owner_isolation(client):
    sign_in(client);vid=version(client)
    client.cookies.clear();sign_in(client,'other@example.org')
    assert client.post(f'/versions/{vid}/verify').status_code==404
