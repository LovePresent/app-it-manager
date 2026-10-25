"""Add bounded automatic enrollment tickets and durable idempotent claims.

Revision ID: 20261025_auto_enrollment
Revises: 20261025_device_agents
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_auto_enrollment"
down_revision = "20261025_device_agents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("device_agents", sa.Column("hardware_key", sa.String(80), nullable=True))
    op.create_index("ix_device_agents_hardware_key", "device_agents", ["hardware_key"], unique=True)
    op.create_table(
        "auto_enrollment_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("issued_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("max_uses >= 1 AND max_uses <= 1000", name="ck_auto_ticket_max_uses"),
        sa.CheckConstraint("used_count >= 0 AND used_count <= max_uses", name="ck_auto_ticket_used_count"),
    )
    op.create_index("ix_auto_enrollment_tickets_expires_at", "auto_enrollment_tickets", ["expires_at"])
    op.create_index("ix_auto_enrollment_tickets_issued_by_id", "auto_enrollment_tickets", ["issued_by_id"])
    op.create_table(
        "auto_enrollment_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("auto_enrollment_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("hardware_key", sa.String(80), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("device_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_device", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("ticket_id", "nonce_hash", name="uq_auto_claim_ticket_nonce"),
    )
    for column in ("ticket_id", "hardware_key", "agent_id"):
        op.create_index(f"ix_auto_enrollment_claims_{column}", "auto_enrollment_claims", [column])


def downgrade():
    op.drop_table("auto_enrollment_claims")
    op.drop_table("auto_enrollment_tickets")
    op.drop_index("ix_device_agents_hardware_key", table_name="device_agents")
    with op.batch_alter_table("device_agents") as table:
        table.drop_column("hardware_key")
