"""role_family enum to string for growable taxonomy

Revision ID: 8f4fa0b9cc52
Revises: 2c9e1cb3f76f
Create Date: 2026-07-30 09:46:47.291221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '8f4fa0b9cc52'
down_revision: Union[str, Sequence[str], None] = '2c9e1cb3f76f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert the native enum column to plain text so the role taxonomy can grow
    # (finance, consulting, design, ...) without an ALTER TYPE each time.
    op.alter_column(
        "postings",
        "role_family",
        type_=sa.String(length=20),
        existing_nullable=False,
        postgresql_using="role_family::text",
    )
    op.execute("DROP TYPE IF EXISTS role_family")


def downgrade() -> None:
    role_family = sa.Enum(
        "swe", "ai_ml", "data", "hardware", "quant", "product", "security", "other",
        name="role_family",
    )
    role_family.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        "postings",
        "role_family",
        type_=role_family,
        existing_nullable=False,
        postgresql_using="role_family::role_family",
    )
