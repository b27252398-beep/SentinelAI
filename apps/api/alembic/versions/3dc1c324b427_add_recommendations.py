"""add_recommendations

Revision ID: 3dc1c324b427
Revises: 151e32bca398
Create Date: 2026-09-09 01:13:20.076983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3dc1c324b427'
down_revision: Union[str, Sequence[str], None] = '151e32bca398'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update existing nulls in rationale before applying NOT NULL
    op.execute("UPDATE recommendations SET rationale = 'Migrated rationale' WHERE rationale IS NULL")
    
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('incident_id', sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('title', sa.String(), server_default='Migrated', nullable=False))
        batch_op.add_column(sa.Column('description', sa.Text(), server_default='Migrated description', nullable=False))
        batch_op.add_column(sa.Column('recommendation_type', sa.String(length=50), server_default='GENERIC', nullable=False))
        batch_op.add_column(sa.Column('target_service_id', sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('expected_effect', sa.Text(), server_default='Migrated effect', nullable=False))
        batch_op.add_column(sa.Column('confidence', sa.Float(), server_default='0.5', nullable=False))
        
        # SQLite JSON needs with_variant
        batch_op.add_column(sa.Column('preconditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql').with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('validation_steps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql').with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False))
        
        batch_op.add_column(sa.Column('rollback_guidance', sa.Text(), server_default='Migrated rollback', nullable=False))
        batch_op.add_column(sa.Column('approval_status', sa.String(length=30), server_default='PENDING_VALIDATION', nullable=False))
        batch_op.add_column(sa.Column('execution_status', sa.String(length=30), server_default='PENDING', nullable=False))
        batch_op.add_column(sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('decided_by', sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))

        batch_op.alter_column('rationale', existing_type=sa.Text(), nullable=False)

        batch_op.drop_column('action_description')
        batch_op.drop_column('status')
        # reviewed_by fk will automatically be dropped in sqlite by batch mode
        batch_op.drop_column('reviewed_by')

        batch_op.create_foreign_key('fk_recommendations_incident_id', 'incidents', ['incident_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_recommendations_target_service_id', 'services', ['target_service_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_recommendations_decided_by', 'users', ['decided_by'], ['id'], ondelete='SET NULL')
        
        batch_op.create_index(batch_op.f('ix_recommendations_incident_id'), ['incident_id'], unique=False)


def downgrade() -> None:
    # Downgrade is not supported for this migration as per project policy.
    pass
