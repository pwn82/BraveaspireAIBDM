"""email safety layer

Phase 5:
  • suppression_list + unique(org, email)
  • bounce_events (append-only audit trail)
  • Outreach: Message-ID / In-Reply-To / provider_message_id / bounce_status /
    unsubscribed_at columns for reply threading and delivery status.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── suppression_list ────────────────────────────────────────────────────
    op.create_table(
        "suppression_list",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("notes",  sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("suppression_list", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_suppression_list_id"),              ["id"],              unique=False)
        batch_op.create_index(batch_op.f("ix_suppression_list_email"),           ["email"],           unique=False)
        batch_op.create_index(batch_op.f("ix_suppression_list_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index("uq_suppression_org_email", ["organization_id", "email"], unique=True)

    # ── bounce_events ───────────────────────────────────────────────────────
    op.create_table(
        "bounce_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("outreach_id",     sa.Integer(), nullable=True),
        sa.Column("email",           sa.String(length=320), nullable=False),
        sa.Column("bounce_type",     sa.String(length=20),  nullable=False),
        sa.Column("provider",            sa.String(length=50),  nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("diagnostic",  sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at",  sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["outreach_id"],     ["outreach.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bounce_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bounce_events_id"),                  ["id"],                  unique=False)
        batch_op.create_index(batch_op.f("ix_bounce_events_email"),               ["email"],               unique=False)
        batch_op.create_index(batch_op.f("ix_bounce_events_organization_id"),     ["organization_id"],     unique=False)
        batch_op.create_index(batch_op.f("ix_bounce_events_outreach_id"),         ["outreach_id"],         unique=False)
        batch_op.create_index(batch_op.f("ix_bounce_events_provider_message_id"), ["provider_message_id"], unique=False)

    # ── Outreach: threading + delivery-status columns ────────────────────────
    with op.batch_alter_table("outreach", schema=None) as batch_op:
        batch_op.add_column(sa.Column("message_id_header",    sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("in_reply_to",          sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("provider_message_id",  sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("bounce_status",        sa.String(length=20),  nullable=True))
        batch_op.add_column(sa.Column("unsubscribed_at",      sa.DateTime(),         nullable=True))
        batch_op.create_index(batch_op.f("ix_outreach_message_id_header"),   ["message_id_header"],   unique=False)
        batch_op.create_index(batch_op.f("ix_outreach_provider_message_id"), ["provider_message_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("outreach", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_outreach_provider_message_id"))
        batch_op.drop_index(batch_op.f("ix_outreach_message_id_header"))
        batch_op.drop_column("unsubscribed_at")
        batch_op.drop_column("bounce_status")
        batch_op.drop_column("provider_message_id")
        batch_op.drop_column("in_reply_to")
        batch_op.drop_column("message_id_header")

    with op.batch_alter_table("bounce_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bounce_events_provider_message_id"))
        batch_op.drop_index(batch_op.f("ix_bounce_events_outreach_id"))
        batch_op.drop_index(batch_op.f("ix_bounce_events_organization_id"))
        batch_op.drop_index(batch_op.f("ix_bounce_events_email"))
        batch_op.drop_index(batch_op.f("ix_bounce_events_id"))
    op.drop_table("bounce_events")

    with op.batch_alter_table("suppression_list", schema=None) as batch_op:
        batch_op.drop_index("uq_suppression_org_email")
        batch_op.drop_index(batch_op.f("ix_suppression_list_organization_id"))
        batch_op.drop_index(batch_op.f("ix_suppression_list_email"))
        batch_op.drop_index(batch_op.f("ix_suppression_list_id"))
    op.drop_table("suppression_list")
