"""add company_short_desc to leads

Revision ID: 0f1e2d3c4b5a
Revises: f6a7b8c9d0e1
Create Date: 2026-03-12 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0f1e2d3c4b5a"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("company_short_desc", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_column("company_short_desc")
