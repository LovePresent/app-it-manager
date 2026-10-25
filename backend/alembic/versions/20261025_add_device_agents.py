"""Add authenticated device agents and durable control commands.

Revision ID: 20261025_device_agents
Revises: 20261010_license_photos
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_device_agents"
down_revision = "20261010_license_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64)),
        sa.Column("enrollment_hash", sa.String(64)),
        sa.Column("enrollment_expires_at", sa.DateTime()),
        sa.Column("enrollment_consumed_at", sa.DateTime()),
        sa.Column("uninstall_code_hash", sa.String(64)),
        sa.Column("uninstall_code_expires_at", sa.DateTime()),
        sa.Column("uninstall_requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("enrolled_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("hostname", sa.String(255)),
        sa.Column("os_version", sa.String(255)),
        sa.Column("boot_time", sa.DateTime()),
        sa.Column("agent_version", sa.String(32)),
        sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("observed_ip", sa.String(80)),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("network_adapters", sa.JSON(), nullable=False),
        sa.Column("network_updated_at", sa.DateTime()),
        sa.Column("wol", sa.JSON()),
        sa.Column("last_wake_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_device_agents_device_id", "device_agents", ["device_id"], unique=True)
    op.create_index("ix_device_agents_enrolled_by_id", "device_agents", ["enrolled_by_id"])
    op.create_index("ix_device_agents_uninstall_requested_by_id", "device_agents", ["uninstall_requested_by_id"])
    op.create_index("ix_device_agents_last_seen_at", "device_agents", ["last_seen_at"])
    op.create_table(
        "device_commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("executor_agent_id", sa.String(36), sa.ForeignKey("device_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("detail", sa.String(32)),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()),
        sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
    )
    for column in ("executor_agent_id", "target_device_id", "requested_by_id", "status", "expires_at"):
        op.create_index(f"ix_device_commands_{column}", "device_commands", [column])


def downgrade():
    # Explicit rollback only; normal upgrade never changes existing inventory.
    op.drop_table("device_commands")
    op.drop_table("device_agents")
