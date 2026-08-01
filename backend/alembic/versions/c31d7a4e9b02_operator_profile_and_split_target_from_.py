"""operator profile, and split target from selectivity

Revision ID: c31d7a4e9b02
Revises: 8f4fa0b9cc52
Create Date: 2026-07-30 15:12:04.883901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c31d7a4e9b02'
down_revision: Union[str, Sequence[str], None] = '8f4fa0b9cc52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Somewhere to persist what the operator is looking for. -------------
    op.create_table(
        "operator_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "preferred_locations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("open_to_remote", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "sponsorship", sa.String(length=30), server_default="us_authorized", nullable=False
        ),
        sa.Column("weekly_study_hours", sa.Integer(), server_default="10", nullable=False),
        sa.Column(
            "target_cycles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_operator_profiles_user_id", "operator_profiles", ["user_id"], unique=False
    )

    # --- "I want to work here" is not "this is easy to get into". -----------
    # ``companies.tier`` was carrying both meanings. Marking a target wrote
    # tier='target', which maps to mid selectivity, so flagging Jane Street as
    # somewhere you want to work silently demoted it from Reach to Target.
    #
    # The two facts are orthogonal, and they are not even the same *kind* of
    # fact: selectivity describes the world and is identical for everyone, while
    # wanting a company is personal. So the want moves to its own personal table
    # keyed by user_id rather than becoming a second column on the shared
    # ``companies`` row -- otherwise one operator's targets would be everyone's.
    op.create_table(
        "operator_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "company_id", name="uq_operator_targets_user_company"),
    )
    op.create_index("ix_operator_targets_user_id", "operator_targets", ["user_id"])

    # Backfill: rows that only ever said "target" carried no selectivity
    # information, so the tier is cleared and they fall back to the seed table
    # or the honest mid default.
    # The singleton operator id, matching core.config.DEFAULT_OPERATOR_ID.
    op.execute(
        """
        INSERT INTO operator_targets (id, user_id, company_id)
        SELECT gen_random_uuid(), '00000000-0000-4000-8000-000000000001'::uuid, id
        FROM companies WHERE tier = 'target'
        """
    )
    op.execute("UPDATE companies SET tier = NULL WHERE tier = 'target'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE companies SET tier = 'target'
        WHERE tier IS NULL AND id IN (SELECT company_id FROM operator_targets)
        """
    )
    op.drop_index("ix_operator_targets_user_id", table_name="operator_targets")
    op.drop_table("operator_targets")
    op.drop_index("ix_operator_profiles_user_id", table_name="operator_profiles")
    op.drop_table("operator_profiles")
