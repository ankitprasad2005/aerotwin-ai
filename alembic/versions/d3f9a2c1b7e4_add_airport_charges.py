"""add airport charges

Revision ID: d3f9a2c1b7e4
Revises: a4d9f1c3e7b5
Create Date: 2026-10-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3f9a2c1b7e4'
down_revision: Union[str, Sequence[str], None] = 'a4d9f1c3e7b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('airport_charges',
    sa.Column('airport', sa.String(length=4), nullable=False),
    sa.Column('charge_type', sa.String(), nullable=False),
    sa.Column('basis', sa.String(), nullable=False),
    sa.Column('stand_type', sa.String(), nullable=False),
    sa.Column('aircraft_class', sa.String(), nullable=False),
    sa.Column('applies_to', sa.String(), nullable=False),
    sa.Column('slab_from_tonnes', sa.Float(), nullable=False),
    sa.Column('slab_to_tonnes', sa.Float(), nullable=True),
    sa.Column('base_inr', sa.Float(), nullable=True),
    sa.Column('rate_inr', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('hour_from', sa.Float(), nullable=False),
    sa.Column('hour_to', sa.Float(), nullable=True),
    sa.Column('rate_multiplier', sa.Float(), nullable=False),
    sa.Column('free_hours', sa.Float(), nullable=True),
    sa.Column('standard_added_hours', sa.Float(), nullable=True),
    sa.Column('mt_rounding', sa.String(), nullable=True),
    sa.Column('hour_rounding', sa.String(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('source_url', sa.String(), nullable=False),
    sa.Column('source_title', sa.String(), nullable=False),
    sa.Column('page', sa.String(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_airport_charges_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_airport_charges')),
    sa.UniqueConstraint('airport', 'charge_type', 'applies_to', 'stand_type', 'aircraft_class', 'slab_from_tonnes', 'hour_from', 'effective_from', name='uq_airport_charges_key')
    )
    op.create_index('ix_airport_charges_airport_charge_type', 'airport_charges', ['airport', 'charge_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_airport_charges_airport_charge_type', table_name='airport_charges')
    op.drop_table('airport_charges')
