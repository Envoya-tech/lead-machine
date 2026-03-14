"""add lead_sources_config to tenant_settings

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-09 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column("lead_sources_config", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.drop_column("lead_sources_config")
