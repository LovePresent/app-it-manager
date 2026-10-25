"""add license service company

Revision ID: 20260728_license_service_company
Revises: 20260728_license_assignments
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_license_service_company"
down_revision = "20260728_license_assignments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("software_licenses", sa.Column("service_company", sa.String(), nullable=True))


def downgrade():
    op.drop_column("software_licenses", "service_company")
