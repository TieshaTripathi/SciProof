"""Honest optional attestation lifecycle and signed transaction recovery.
"""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None
FIELDS={'contract_address':sa.String(42),'signer_address':sa.String(42),'researcher_address':sa.String(42),
        'provenance_hash':sa.String(64),'block_number':sa.Integer(),'block_hash':sa.String(66),
        'confirmations_required':sa.Integer(),'attested_at':sa.DateTime(timezone=True),
        'nonce':sa.Integer(),'signed_transaction':sa.Text(),'error_code':sa.String(100)}
def replace_constraint(old,new,name):
    connection=op.get_bind()
    constraints=sa.inspect(connection).get_check_constraints('blockchain_attestations')
    previous=next(c['name'] for c in constraints if 'status' in c['sqltext'] and ('PENDING_CONFIGURATION' in c['sqltext'] or 'NOT_REQUESTED' in c['sqltext']))
    with op.batch_alter_table('blockchain_attestations',naming_convention={'ck':'ck_%(table_name)s_%(column_0_name)s'}) as batch:
        batch.drop_constraint(previous or 'ck_blockchain_attestations_',type_='check')
    connection.execute(sa.text('UPDATE blockchain_attestations SET status=:new WHERE status=:old'),{'new':new,'old':old})
    with op.batch_alter_table('blockchain_attestations') as batch:
        values="'NOT_REQUESTED','PENDING','SUBMITTED','CONFIRMED','FAILED'" if new=='NOT_REQUESTED' else "'PENDING_CONFIGURATION','SUBMITTED','CONFIRMED','FAILED'"
        batch.create_check_constraint(name,'status IN ('+values+')')
def upgrade():
    replace_constraint('PENDING_CONFIGURATION','NOT_REQUESTED','attestation_state')
    for name,kind in FIELDS.items(): op.add_column('blockchain_attestations',sa.Column(name,kind,nullable=True))
def downgrade():
    op.execute("UPDATE blockchain_attestations SET status='NOT_REQUESTED' WHERE status='PENDING'")
    replace_constraint('NOT_REQUESTED','PENDING_CONFIGURATION','legacy_attestation_state')
    with op.batch_alter_table('blockchain_attestations') as batch:
        for name in reversed(FIELDS): batch.drop_column(name)
