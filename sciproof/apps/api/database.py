import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DEFAULT_URL='postgresql+psycopg://sciproof:sciproof@localhost:5432/sciproof'
def make_database(url=None):
    url=url or os.getenv('DATABASE_URL',DEFAULT_URL)
    engine=create_engine(url, pool_pre_ping=True)
    if engine.dialect.name=='sqlite':
        @event.listens_for(engine,'connect')
        def foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine,sessionmaker(engine,expire_on_commit=False)
