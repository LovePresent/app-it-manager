"""prevent SQLite project ID reuse in audit history

Revision ID: 20261007_project_history
Revises: 20261007_projects
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20261007_project_history"
down_revision = "20261007_projects"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL sequences already prevent reuse. SQLite needs AUTOINCREMENT.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("projects", recreate="always", table_kwargs={"sqlite_autoincrement": True}):
            pass
        # Include IDs retained only in audit history, even if the table is empty.
        bind = op.get_bind()
        maximum = bind.execute(sa.text(
            "SELECT COALESCE(MAX(entity_id), 0) FROM audit_logs WHERE entity_type = 'project'"
        )).scalar_one()
        result = bind.execute(sa.text("SELECT seq FROM sqlite_sequence WHERE name = 'projects'")).scalar_one_or_none()
        if result is None:
            bind.execute(sa.text("INSERT INTO sqlite_sequence (name, seq) VALUES ('projects', :seq)"), {"seq": maximum})
        elif maximum > result:
            bind.execute(sa.text("UPDATE sqlite_sequence SET seq = :seq WHERE name = 'projects'"), {"seq": maximum})


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("projects", recreate="always", table_kwargs={"sqlite_autoincrement": False}):
            pass
