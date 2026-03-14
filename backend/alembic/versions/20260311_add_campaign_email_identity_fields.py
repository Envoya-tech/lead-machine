"""add sender_name, cta_word_nl, cta_word_en to campaigns

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-11 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("sender_name", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cta_word_nl", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cta_word_en", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_column("cta_word_en")
        batch_op.drop_column("cta_word_nl")
        batch_op.drop_column("sender_name")
