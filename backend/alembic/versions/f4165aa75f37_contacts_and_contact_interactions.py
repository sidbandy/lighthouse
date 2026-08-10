"""contacts and contact interactions

Scoped by hand to the two new tables. Autogenerate also proposed tightening
nullability on operator_profiles/operator_targets, swapping a unique constraint
for a unique index, and adding an index to postings.role_family -- all real
drift between the models and this database, and none of it part of this change.
A migration that quietly alters unrelated tables is how a rollback stops being
safe, so that drift is left for its own revision.

Revision ID: f4165aa75f37
Revises: ea26efa727c8
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4165aa75f37"
down_revision: str | Sequence[str] | None = "ea26efa727c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("role_title", sa.Text(), nullable=True),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("school", sa.Text(), nullable=True),
        sa.Column("grad_year", sa.Integer(), nullable=True),
        sa.Column("strength", sa.Integer(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relationship_type IN ('cold','warm_intro','alumni','met_at_event','referred_by')",
            name="ck_contact_relationship",
        ),
        sa.CheckConstraint(
            "strength IS NULL OR (strength >= 1 AND strength <= 5)",
            name="ck_contact_strength",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contacts_company_id"), "contacts", ["company_id"])
    op.create_index("ix_contacts_user_company", "contacts", ["user_id", "company_id"])
    op.create_index(op.f("ix_contacts_user_id"), "contacts", ["user_id"])

    op.create_table(
        "contact_interactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("direction IN ('outbound','inbound')", name="ck_interaction_direction"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_contact_interactions_application_id"), "contact_interactions", ["application_id"]
    )
    op.create_index(
        op.f("ix_contact_interactions_contact_id"), "contact_interactions", ["contact_id"]
    )
    op.create_index(op.f("ix_contact_interactions_user_id"), "contact_interactions", ["user_id"])
    op.create_index(
        "ix_interactions_contact_time", "contact_interactions", ["contact_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_interactions_contact_time", table_name="contact_interactions")
    op.drop_index(op.f("ix_contact_interactions_user_id"), table_name="contact_interactions")
    op.drop_index(op.f("ix_contact_interactions_contact_id"), table_name="contact_interactions")
    op.drop_index(op.f("ix_contact_interactions_application_id"), table_name="contact_interactions")
    op.drop_table("contact_interactions")
    op.drop_index(op.f("ix_contacts_user_id"), table_name="contacts")
    op.drop_index("ix_contacts_user_company", table_name="contacts")
    op.drop_index(op.f("ix_contacts_company_id"), table_name="contacts")
    op.drop_table("contacts")
