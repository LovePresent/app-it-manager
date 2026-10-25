"""add license assignments

Revision ID: 20260728_license_assignments
Revises: 20260429_ip_change_history
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_license_assignments"
down_revision = "20260429_ip_change_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "license_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["license_id"], ["software_licenses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_id", "device_id", name="uq_license_assignments_license_device"),
    )
    op.create_index("ix_license_assignments_id", "license_assignments", ["id"])
    op.create_index("ix_license_assignments_license_id", "license_assignments", ["license_id"])
    op.create_index("ix_license_assignments_device_id", "license_assignments", ["device_id"])


def downgrade():
    op.drop_index("ix_license_assignments_device_id", table_name="license_assignments")
    op.drop_index("ix_license_assignments_license_id", table_name="license_assignments")
    op.drop_index("ix_license_assignments_id", table_name="license_assignments")
    op.drop_table("license_assignments")
