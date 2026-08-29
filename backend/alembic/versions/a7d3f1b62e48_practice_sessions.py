"""practice sessions

Scoped by hand to the one new table. The drift noted in f4165aa75f37 --
nullability on operator_profiles/operator_targets, a unique constraint swapped
for a unique index, an index on postings.role_family -- is still outstanding and
is still left for its own revision rather than folded in here.

No transcript column, and that is deliberate rather than an oversight. Practice
promises the operator that nothing they say is recorded or kept; this table
stores only what a trend needs.

Revision ID: a7d3f1b62e48
Revises: f4165aa75f37
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7d3f1b62e48"
down_revision: str | Sequence[str] | None = "f4165aa75f37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("competency", sa.String(length=40), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer_mode", sa.String(length=10), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("is_measurable", sa.Boolean(), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        sa.Column(
            "structure_present",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=True,
        ),
        sa.Column("drift_count", sa.Integer(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('behavioural','technical')", name="ck_practice_session_kind"
        ),
        sa.CheckConstraint(
            "answer_mode IN ('spoken','typed')", name="ck_practice_session_answer_mode"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_practice_sessions_user_id", "practice_sessions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_practice_sessions_competency", "practice_sessions", ["competency"], unique=False
    )
    op.create_index(
        "ix_practice_sessions_occurred_at", "practice_sessions", ["occurred_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_practice_sessions_occurred_at", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_competency", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_user_id", table_name="practice_sessions")
    op.drop_table("practice_sessions")
