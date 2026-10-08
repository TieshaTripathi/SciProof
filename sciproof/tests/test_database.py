import os
from pathlib import Path
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from apps.api.database import make_database
from apps.api.models import *

def test_migrations_from_empty_database(tmp_path,monkeypatch):
    url='sqlite:///'+str(tmp_path/'migrations.sqlite')
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config(str(Path(__file__).parents[1]/'alembic.ini'))
    assert len(ScriptDirectory.from_config(config).get_heads())==1
    command.upgrade(config,'head')
    engine,_=make_database(url)
    tables=inspect(engine).get_table_names()
    assert set(Base.metadata.tables)<=set(tables)
    command.check(config)
    command.downgrade(config,'base')
    assert not set(Base.metadata.tables)&set(inspect(engine).get_table_names())
    command.upgrade(config,'head')
    engine.dispose()

def test_foreign_keys_and_version_uniqueness(tmp_path):
    engine,sessions=make_database('sqlite:///'+str(tmp_path/'constraints.sqlite'))
    Base.metadata.create_all(engine)
    with sessions.begin() as db:
        u=User(email='a@example.org',password_hash='test');db.add(u);db.flush()
        p=ResearchProject(owner_id=u.id,title='project');db.add(p);db.flush()
        pid=p.id;db.add(ResearchVersion(project_id=pid,version_number=1))
    with pytest.raises(IntegrityError):
        with sessions.begin() as db: db.add(ResearchVersion(project_id=pid,version_number=1))
    with pytest.raises(IntegrityError):
        with sessions.begin() as db: db.add(ResearchProject(owner_id=uid(),title='orphan'))
    engine.dispose()
