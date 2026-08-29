"""ingest_runs

A run-level record. source_health is per source, so a run killed by the CI
timeout leaves ninety healthy sources and nothing saying the run never
finished -- which is the exact failure the 30-minute workflow timeout was
producing.

The row is committed when the run starts, in its own transaction, so a
SIGKILL still leaves evidence. A null finished_at with a null error is a run
that died without getting to say why.

Scoped by hand to the one new table. The drift noted in f4165aa75f37 and
carried forward since -- nullability on operator_profiles/operator_targets, a
unique constraint swapped for a unique index, an index on postings.role_family
-- is still outstanding and still left for its own revision.

Revision ID: c93a1d47be60
Revises: b2e8c5019f4a
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c93a1d47be60"
down_revision: str | Sequence[str] | None = "b2e8c5019f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_tier", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("raw_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("merged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_not_applyable", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collapsed_in_batch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_started_at", "ingest_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_ingest_runs_started_at", table_name="ingest_runs")
    op.drop_table("ingest_runs")
