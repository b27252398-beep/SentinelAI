"""add incident models

Revision ID: 1673be5fe651
Revises: bc1eee7578f3
Create Date: 2026-09-08 13:35:53.873399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1673be5fe651'
down_revision: Union[str, Sequence[str], None] = 'bc1eee7578f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create incidents, incident_anomalies, and incident_events tables."""

    # ------------------------------------------------------------------
    # incidents
    # ------------------------------------------------------------------
    op.create_table(
        'incidents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('service_id', sa.Uuid(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assigned_to', sa.Uuid(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_anomaly_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['service_id'], ['services.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['assigned_to'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_incidents_id'), 'incidents', ['id'], unique=False)
    op.create_index('ix_incidents_service_id', 'incidents', ['service_id'], unique=False)
    op.create_index('ix_incidents_status', 'incidents', ['status'], unique=False)
    op.create_index('ix_incidents_severity', 'incidents', ['severity'], unique=False)

    # Partial unique index: at most one active incident per service.
    # Active = Detected, Investigating, Identified, Mitigating
    # PostgreSQL-only — skip for SQLite test databases.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("""
            CREATE UNIQUE INDEX uq_active_incident_per_service
            ON incidents (service_id)
            WHERE status NOT IN ('Resolved', 'Closed')
        """)

    # ------------------------------------------------------------------
    # incident_anomalies
    # ------------------------------------------------------------------
    op.create_table(
        'incident_anomalies',
        sa.Column('incident_id', sa.Uuid(), nullable=False),
        sa.Column('anomaly_id', sa.Uuid(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['incident_id'], ['incidents.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['anomaly_id'], ['anomaly_events.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('incident_id', 'anomaly_id'),
        # Each anomaly belongs to at most one incident
        sa.UniqueConstraint('anomaly_id', name='uq_incident_anomaly_id'),
    )

    # At most one primary anomaly per incident (PostgreSQL partial unique index)
    if bind.dialect.name == 'postgresql':
        op.execute("""
            CREATE UNIQUE INDEX uq_incident_primary_anomaly
            ON incident_anomalies (incident_id)
            WHERE is_primary = TRUE
        """)

    # ------------------------------------------------------------------
    # incident_events
    # ------------------------------------------------------------------
    op.create_table(
        'incident_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('incident_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['incident_id'], ['incidents.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['actor_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_incident_events_id'), 'incident_events', ['id'], unique=False)
    op.create_index(
        'ix_incident_events_incident_id', 'incident_events', ['incident_id'], unique=False
    )
    op.create_index(
        'ix_incident_events_created_at', 'incident_events', ['created_at'], unique=False
    )


def downgrade() -> None:
    """Drop incident tables in reverse dependency order."""
    op.drop_index('ix_incident_events_created_at', table_name='incident_events')
    op.drop_index('ix_incident_events_incident_id', table_name='incident_events')
    op.drop_index(op.f('ix_incident_events_id'), table_name='incident_events')
    op.drop_table('incident_events')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS uq_incident_primary_anomaly')

    op.drop_table('incident_anomalies')

    if bind.dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS uq_active_incident_per_service')

    op.drop_index('ix_incidents_severity', table_name='incidents')
    op.drop_index('ix_incidents_status', table_name='incidents')
    op.drop_index('ix_incidents_service_id', table_name='incidents')
    op.drop_index(op.f('ix_incidents_id'), table_name='incidents')
    op.drop_table('incidents')
