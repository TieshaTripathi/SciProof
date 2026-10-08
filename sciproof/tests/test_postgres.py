import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from apps.api.main import create_app
from apps.api.models import *
from apps.api.storage import LocalEncryptedStorage
from tests.test_api import sign_in, pdf

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'),reason='Dedicated PostgreSQL test database required')
def test_postgres_migrations_workflow_and_concurrent_versions(tmp_path,monkeypatch):
    url=os.environ['TEST_POSTGRES_URL'];monkeypatch.setenv('DATABASE_URL',url)
    cfg=Config(str(Path(__file__).parents[1]/'alembic.ini'))
    command.upgrade(cfg,'head');command.check(cfg)
    app=create_app(url,LocalEncryptedStorage(tmp_path/'artifacts'),'inline')
    with TestClient(app) as c:
        sign_in(c)
        p=c.post('/projects',json={'title':'PostgreSQL validation'}).json()
        def new_version(_):
            with TestClient(app) as concurrent:
                concurrent.cookies.update(c.cookies)
                return concurrent.post(f"/projects/{p['id']}/versions")
        with ThreadPoolExecutor(max_workers=4) as pool: responses=list(pool.map(new_version,range(4)))
        assert all(r.status_code==200 for r in responses)
        assert sorted(r.json()['version_number'] for r in responses)==[1,2,3,4]
        vid=responses[0].json()['id']
        for kind,name,raw in [('manuscript','paper.pdf',pdf('mean of x = 2')),('dataset','data.csv',b'x\n1\n2\n3')]:
            assert c.post(f'/versions/{vid}/artifacts/{kind}',files={'file':(name,raw)}).status_code==200
        result=c.post(f'/versions/{vid}/verify')
        assert result.status_code==200,result.text
        assert result.json()['checks'][0]['outcome']=='SUPPORTED'
        with app.state.sessions() as db:
            assert db.scalar(select(func.count()).select_from(ClaimEvidenceLink))==1
    app.state.engine.dispose()
    command.downgrade(cfg,'base');command.upgrade(cfg,'head');command.check(cfg)
