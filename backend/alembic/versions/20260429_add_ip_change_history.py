"""add ip change history

Revision ID: 20260429_ip_change_history
Revises:
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_ip_change_history"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ip_change_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("ip_address_id", sa.Integer(), nullable=True),
        sa.Column("old_serial_number", sa.String(), nullable=True),
        sa.Column("new_serial_number", sa.String(), nullable=True),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("employee_number", sa.String(), nullable=True),
        sa.Column("asset_tag", sa.String(), nullable=True),
        sa.Column("asset_name", sa.String(), nullable=True),
        sa.Column("old_ip_address", sa.String(), nullable=True),
        sa.Column("new_ip_address", sa.String(), nullable=True),
        sa.Column("old_mac_address", sa.String(), nullable=True),
        sa.Column("new_mac_address", sa.String(), nullable=True),
        sa.Column("old_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=True),
        sa.Column("change_reason", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "id",
        "source_type",
        "source_id",
        "device_id",
        "ip_address_id",
        "old_serial_number",
        "new_serial_number",
        "user_name",
        "employee_number",
        "asset_tag",
        "asset_name",
        "old_ip_address",
        "new_ip_address",
        "old_mac_address",
        "new_mac_address",
        "change_reason",
        "created_at",
    ):
        op.create_index(f"ix_ip_change_history_{column}", "ip_change_history", [column])


def downgrade():
    op.drop_table("ip_change_history")
