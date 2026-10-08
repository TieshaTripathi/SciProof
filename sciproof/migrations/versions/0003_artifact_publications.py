"""Explicit public publication audit.
"""
from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('artifact_publications',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('artifact_id',sa.Uuid(as_uuid=False),sa.ForeignKey('research_artifacts.id'),nullable=False,unique=True),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('provider',sa.String(50)),
        sa.Column('cid',sa.String(120)),sa.Column('artifact_hash',sa.String(64),nullable=False),
        sa.Column('published_at',sa.DateTime(timezone=True)),sa.Column('error_code',sa.String(100)),
        sa.CheckConstraint("status IN ('NOT_PUBLISHED','PUBLISHING','PUBLISHED','FAILED')"))
def downgrade(): op.drop_table('artifact_publications')
