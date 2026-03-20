"""Initial incident and audit schema.

Revision ID: 0001_initial
Revises: 
Create Date: 2026-03-19
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("incident_id"),
    )
    op.create_index("idx_incidents_updated_at", "incidents", ["updated_at"], unique=False)
    op.create_index("idx_incidents_dedupe_key", "incidents", ["dedupe_key"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_audit_events_created_at", "audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("idx_incidents_dedupe_key", table_name="incidents")
    op.drop_index("idx_incidents_updated_at", table_name="incidents")
    op.drop_table("incidents")
