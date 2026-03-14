"""add engine_llm and chat_llm fields to tenant_settings

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-09 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.add_column(sa.Column("engine_llm_provider", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("engine_llm_model", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("engine_llm_api_key_enc", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("chat_llm_provider", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("chat_llm_model", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("chat_llm_api_key_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.drop_column("engine_llm_provider")
        batch_op.drop_column("engine_llm_model")
        batch_op.drop_column("engine_llm_api_key_enc")
        batch_op.drop_column("chat_llm_provider")
        batch_op.drop_column("chat_llm_model")
        batch_op.drop_column("chat_llm_api_key_enc")
