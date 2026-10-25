"""add project manager

Revision ID: 20261007_projects
Revises: 20260805_purchase_ledger
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20261007_projects"
down_revision = "20260805_purchase_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manager_name", sa.String(100), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_projects_progress"),
        sa.CheckConstraint("start_date IS NULL OR due_date IS NULL OR start_date <= due_date", name="ck_projects_dates"),
        sa.CheckConstraint("status IN ('planned', 'in_progress', 'on_hold', 'completed', 'cancelled')", name="ck_projects_status"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_projects_priority"),
    )
    for column in ("name", "manager_name", "status", "due_date"):
        op.create_index(f"ix_projects_{column}", "projects", [column])


def downgrade():
    op.drop_table("projects")
