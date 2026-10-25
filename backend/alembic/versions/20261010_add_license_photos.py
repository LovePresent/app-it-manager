"""add license evidence photos

Revision ID: 20261010_license_photos
Revises: 20261008_maintenance_received
Create Date: 2026-10-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20261010_license_photos"
down_revision = "20261008_maintenance_received"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "software_license_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_name", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["license_id"], ["software_licenses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_name"),
    )
    op.create_index("ix_software_license_photos_id", "software_license_photos", ["id"])
    op.create_index("ix_software_license_photos_license_id", "software_license_photos", ["license_id"])


def downgrade():
    op.drop_table("software_license_photos")
