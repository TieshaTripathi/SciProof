"""Persist numerical comparison and rule execution context.

Historical reports retain their original policy; new columns are nullable.
"""
from alembic import op
import sqlalchemy as sa

revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

FIELDS={'absolute_difference':sa.Float(),'relative_difference':sa.Float(),
        'relative_tolerance':sa.Float(),'comparison_method':sa.String(100),
        'rule_version':sa.String(50),'rule_context':sa.JSON()}
def upgrade():
    for name,kind in FIELDS.items():
        op.add_column('verification_checks',sa.Column(name,kind,nullable=True))
def downgrade():
    with op.batch_alter_table('verification_checks') as batch:
        for name in reversed(FIELDS): batch.drop_column(name)
