"""Core schema: users, projects, sites, site_versions.

The ownership chain: a Firebase user owns projects; a project has sites
(usually one); a site accumulates immutable versions — every generation
or edit appends a version rather than mutating, so rollback is a pointer
move and the eval layer can score any historical version.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        # the Firebase uid IS the primary key — no separate id to join through
        sa.Column("uid", sa.Text, primary_key=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_uid", sa.Text, sa.ForeignKey("users.uid", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        # everything the interview learns about the business, as one document
        sa.Column("business_brief", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_projects_owner", "projects", ["owner_uid"])

    op.create_table(
        "sites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hosting_site_id", sa.Text, nullable=True),
        sa.Column("live_url", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("current_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sites_project", "sites", ["project_id"])

    op.create_table(
        "site_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        # the agent's structured plan for the site (pages, theme, nav)
        sa.Column("spec", JSONB, nullable=False, server_default="{}"),
        # rendered page content keyed by path
        sa.Column("pages", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Text, nullable=False, server_default="agent"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("site_id", "version", name="uq_site_version"),
    )


def downgrade() -> None:
    op.drop_table("site_versions")
    op.drop_table("sites")
    op.drop_table("projects")
    op.drop_table("users")
