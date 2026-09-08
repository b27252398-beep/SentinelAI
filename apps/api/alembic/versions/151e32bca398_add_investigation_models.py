"""add_investigation_models

Revision ID: 151e32bca398
Revises: 1673be5fe651
Create Date: 2026-09-09 00:39:40.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '151e32bca398'
down_revision = '1673be5fe651'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. investigations
    op.create_table(
        'investigations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('incident_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('prompt_version', sa.String(length=100), nullable=True),
        sa.Column('model_identifier', sa.String(length=100), nullable=True),
        sa.Column('rca_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('rca_reviewed_by', sa.Uuid(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rca_reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_investigations_id'), 'investigations', ['id'], unique=False)
    op.create_index(op.f('ix_investigations_incident_id'), 'investigations', ['incident_id'], unique=False)
    op.create_index(op.f('ix_investigations_status'), 'investigations', ['status'], unique=False)

    # 2. investigation_evidence
    op.create_table(
        'investigation_evidence',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('investigation_id', sa.Uuid(), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('source_identifier', sa.String(length=128), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('service_id', sa.Uuid(), nullable=True),
        # Using JSON instead of JSONB for wide compat, since we don't strictly require jsonb operators here
        # but the model says JSONB().with_variant(JSON, "sqlite"). For Alembic cross-db compat, we do this:
        sa.Column('deep_copied_payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_investigation_evidence_id'), 'investigation_evidence', ['id'], unique=False)
    op.create_index(op.f('ix_investigation_evidence_investigation_id'), 'investigation_evidence', ['investigation_id'], unique=False)
    op.create_index('ix_inv_evidence_inv_source', 'investigation_evidence', ['investigation_id', 'source_identifier'], unique=False)

    # 3. hypotheses
    op.create_table(
        'hypotheses',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('investigation_id', sa.Uuid(), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('is_probable_root_cause', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('supporting_evidence_ids', sa.JSON(), nullable=False),
        sa.Column('contradicting_evidence_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_hypotheses_id'), 'hypotheses', ['id'], unique=False)
    op.create_index(op.f('ix_hypotheses_investigation_id'), 'hypotheses', ['investigation_id'], unique=False)

    # 4. recommendations
    op.create_table(
        'recommendations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('investigation_id', sa.Uuid(), nullable=False),
        sa.Column('hypothesis_id', sa.Uuid(), nullable=False),
        sa.Column('action_description', sa.Text(), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', sa.Uuid(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['hypothesis_id'], ['hypotheses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendations_id'), 'recommendations', ['id'], unique=False)
    op.create_index(op.f('ix_recommendations_investigation_id'), 'recommendations', ['investigation_id'], unique=False)
    op.create_index(op.f('ix_recommendations_hypothesis_id'), 'recommendations', ['hypothesis_id'], unique=False)


def downgrade() -> None:
    op.drop_table('recommendations')
    op.drop_table('hypotheses')
    op.drop_table('investigation_evidence')
    op.drop_table('investigations')
