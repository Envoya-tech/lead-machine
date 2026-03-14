"""add gamification_data to tenant_settings

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tenant_settings') as batch_op:
        batch_op.add_column(sa.Column('gamification_data', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenant_settings') as batch_op:
        batch_op.drop_column('gamification_data')
