import os
from alembic import context
from sqlalchemy import create_engine, pool
from apps.api.models import Base
from apps.api.database import DEFAULT_URL

url=os.getenv('DATABASE_URL', DEFAULT_URL)
if context.is_offline_mode():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True,compare_type=True)
    with context.begin_transaction(): context.run_migrations()
else:
    engine=create_engine(url,poolclass=pool.NullPool)
    with engine.connect() as connection:
        if engine.dialect.name=='sqlite': connection.exec_driver_sql('PRAGMA foreign_keys=ON'); connection.commit()
        context.configure(connection=connection,target_metadata=Base.metadata,compare_type=True,render_as_batch=engine.dialect.name=='sqlite')
        with context.begin_transaction(): context.run_migrations()
