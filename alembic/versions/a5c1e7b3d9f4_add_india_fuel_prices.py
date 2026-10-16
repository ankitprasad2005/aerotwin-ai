"""add India ATF, crude basket and FBIL reference rate tables

Revision ID: a5c1e7b3d9f4
Revises: d3f9a2c1b7e4
Create Date: 2026-10-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a5c1e7b3d9f4'
down_revision: Union[str, Sequence[str], None] = 'd3f9a2c1b7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('atf_prices_india',
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('price_month', sa.Date(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('inr_per_kl', sa.Float(), nullable=True),
    sa.Column('usd_per_kl', sa.Float(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_atf_prices_india_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_atf_prices_india')),
    sa.UniqueConstraint('city', 'price_month', 'category', name='uq_atf_prices_india_city_price_month_category')
    )
    op.create_table('indian_crude_basket',
    sa.Column('price_month', sa.Date(), nullable=False),
    sa.Column('usd_per_bbl', sa.Float(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_indian_crude_basket_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_indian_crude_basket')),
    sa.UniqueConstraint('price_month', name='uq_indian_crude_basket_price_month')
    )
    op.create_table('fx_reference_india',
    sa.Column('rate_date', sa.Date(), nullable=False),
    sa.Column('inr_per_usd', sa.Float(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_fx_reference_india_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fx_reference_india')),
    sa.UniqueConstraint('rate_date', name='uq_fx_reference_india_rate_date')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fx_reference_india')
    op.drop_table('indian_crude_basket')
    op.drop_table('atf_prices_india')
