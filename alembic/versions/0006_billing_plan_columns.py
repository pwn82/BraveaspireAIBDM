"""billing plan + stripe idempotency

Phase 7:
  • Organization.plan (default 'free') — O(1) entitlement lookup.
  • Subscription.organization_id — subscriptions belong to orgs now.
  • Subscription.stripe_subscription_id unique + indexed.
  • stripe_events table — webhook idempotency ledger.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Organization.plan
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan", sa.String(length=20),
                                      nullable=True, server_default="free"))

    # 2. Subscription.organization_id (+ unique on stripe_subscription_id).
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_subscriptions_organization_id",
                              ["organization_id"], unique=False)
        batch_op.create_index("ix_subscriptions_stripe_customer_id",
                              ["stripe_customer_id"], unique=False)
        batch_op.create_index("uq_subscriptions_stripe_sub_id",
                              ["stripe_subscription_id"], unique=True)
        batch_op.create_foreign_key(
            "fk_subscriptions_organization_id",
            "organizations", ["organization_id"], ["id"],
        )

    # 3. stripe_events table.
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id",   sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=80),  nullable=False),
        sa.Column("status",     sa.String(length=20),  nullable=True, server_default="processed"),
        sa.Column("error",      sa.Text(), nullable=True),
        sa.Column("raw_payload",sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at",   sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stripe_events_id"),       ["id"],       unique=False)
        batch_op.create_index(batch_op.f("ix_stripe_events_event_id"), ["event_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stripe_events_event_id"))
        batch_op.drop_index(batch_op.f("ix_stripe_events_id"))
    op.drop_table("stripe_events")

    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_subscriptions_organization_id", type_="foreignkey")
        batch_op.drop_index("uq_subscriptions_stripe_sub_id")
        batch_op.drop_index("ix_subscriptions_stripe_customer_id")
        batch_op.drop_index("ix_subscriptions_organization_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("plan")
