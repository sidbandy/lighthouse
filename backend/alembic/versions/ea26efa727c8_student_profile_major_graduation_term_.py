"""student profile: major, graduation term, internship count

Revision ID: ea26efa727c8
Revises: c31d7a4e9b02
Create Date: 2026-08-04 16:34:33.748430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = 'ea26efa727c8'
down_revision: Union[str, Sequence[str], None] = 'c31d7a4e9b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Lighthouse is for students and new grads, so the profile is described in
    # the terms a student actually has: a major, a graduation term, and a count
    # of internships. Deliberately not "years of experience" -- a sophomore has
    # none, and asking makes the tool feel written for somebody else.
    op.add_column("operator_profiles", sa.Column("school", sa.Text(), nullable=True))
    op.add_column("operator_profiles", sa.Column("major", sa.Text(), nullable=True))
    op.add_column(
        "operator_profiles", sa.Column("degree_level", sa.String(length=20), nullable=True)
    )
    # Reuses the existing season enum rather than creating a parallel type.
    op.add_column(
        "operator_profiles",
        sa.Column(
            "graduation_season",
            postgresql.ENUM(name="season", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("operator_profiles", sa.Column("graduation_year", sa.Integer(), nullable=True))
    op.add_column(
        "operator_profiles",
        sa.Column("internships_completed", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "operator_profiles",
        sa.Column(
            "target_role_families",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    for column in (
        "target_role_families",
        "internships_completed",
        "graduation_year",
        "graduation_season",
        "degree_level",
        "major",
        "school",
    ):
        op.drop_column("operator_profiles", column)
