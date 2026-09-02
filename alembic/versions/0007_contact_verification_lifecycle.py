"""contact verification lifecycle + outreach approval trail

P0 hardening (senior production review):
  • Contact: email_status / email_source / email_confidence / email_verified_at
    — replaces the single `verified` boolean with a real lifecycle so the
    OutreachPolicy gate can refuse to send to an AI-inferred address that a
    human has not promoted to "verified".
  • Outreach: approved_by / approved_at — HITL audit trail.

Existing rows default to email_status="unknown" (not "unverified") so the
policy gate doesn't retroactively reclassify contacts that were already
manually entered and trusted before this migration; only NEW AI-guessed
contacts get created with email_status="inferred" going forward.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("contacts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_status", sa.String(length=20), nullable=False,
                                       server_default="unknown"))
        batch_op.add_column(sa.Column("email_source", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("email_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_contacts_email_status", ["email_status"], unique=False)

    # Backfill: a contact already marked verified=True keeps that meaning.
    op.execute("UPDATE contacts SET email_status = 'verified' WHERE verified = 1")

    with op.batch_alter_table("outreach", schema=None) as batch_op:
        batch_op.add_column(sa.Column("approved_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_outreach_approved_by", "users", ["approved_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("outreach", schema=None) as batch_op:
        batch_op.drop_constraint("fk_outreach_approved_by", type_="foreignkey")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")

    with op.batch_alter_table("contacts", schema=None) as batch_op:
        batch_op.drop_index("ix_contacts_email_status")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_confidence")
        batch_op.drop_column("email_source")
        batch_op.drop_column("email_status")
