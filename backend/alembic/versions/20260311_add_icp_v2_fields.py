"""add ICP v2 fields to leads and campaigns

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-11 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Leads — ICP v2 fields
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("seniority", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("company_revenue_range", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("company_country", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("company_city", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("company_icp_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("personal_icp_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("icp_hard_pass", sa.Boolean(), nullable=True))

    # Campaigns — ICP v2 config
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("icp_config_v2", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_column("icp_hard_pass")
        batch_op.drop_column("personal_icp_score")
        batch_op.drop_column("company_icp_score")
        batch_op.drop_column("company_city")
        batch_op.drop_column("company_country")
        batch_op.drop_column("company_revenue_range")
        batch_op.drop_column("seniority")

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_column("icp_config_v2")
