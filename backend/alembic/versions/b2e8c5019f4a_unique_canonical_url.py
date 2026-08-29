"""unique index on postings.canonical_url

The dedup key gets the constraint it always implied. ``persist()`` has treated
canonical_url as the posting's identity since the beginning -- it selects on it
to decide create-versus-update -- but nothing at the database level said so, so
two rows with one canonical URL were possible and would have quietly split a
posting's sightings across them.

It also unblocks the batched write path: ``INSERT ... ON CONFLICT
(canonical_url) DO UPDATE`` needs a unique index to name as its arbiter.

Checked against live data before writing this: 23,268 postings, zero duplicate
canonical URLs. So this records an invariant that already holds rather than
imposing a new one, and the index it replaces was non-unique on the same
column, meaning no new write cost.

The drift noted in f4165aa75f37 and a7d3f1b62e48 -- nullability on
operator_profiles/operator_targets, a unique constraint swapped for a unique
index, an index on postings.role_family -- is still outstanding and still left
for its own revision rather than folded in here.

Revision ID: b2e8c5019f4a
Revises: a7d3f1b62e48
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2e8c5019f4a"
down_revision: str | Sequence[str] | None = "a7d3f1b62e48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_postings_canonical_url", table_name="postings")
    op.create_index(
        "ix_postings_canonical_url", "postings", ["canonical_url"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_postings_canonical_url", table_name="postings")
    op.create_index(
        "ix_postings_canonical_url", "postings", ["canonical_url"], unique=False
    )
