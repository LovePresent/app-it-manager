"""add shared purchase ledger

Revision ID: 20260805_purchase_ledger
Revises: 20260803_maintenance_requester
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_purchase_ledger"
down_revision = "20260803_maintenance_requester"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_number", sa.String(), nullable=False),
        sa.Column("item_type", sa.String(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=False),
        sa.Column("vendor_name", sa.String(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="registered"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_number"),
    )
    for column in ("id", "purchase_number", "item_type", "item_name", "vendor_name", "purchase_date", "status"):
        op.create_index(f"ix_purchases_{column}", "purchases", [column], unique=column == "purchase_number")

    op.create_table(
        "purchase_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purchase_id",
            "resource_type",
            "resource_id",
            name="uq_purchase_allocations_resource",
        ),
    )
    for column in ("id", "purchase_id", "resource_type", "resource_id"):
        op.create_index(f"ix_purchase_allocations_{column}", "purchase_allocations", [column], unique=False)


def downgrade():
    op.drop_table("purchase_allocations")
    op.drop_table("purchases")
