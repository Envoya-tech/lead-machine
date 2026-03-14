"""add role_bucket_cache_json to tenant_settings

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-11 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.add_column(sa.Column("role_bucket_cache_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.drop_column("role_bucket_cache_json")
