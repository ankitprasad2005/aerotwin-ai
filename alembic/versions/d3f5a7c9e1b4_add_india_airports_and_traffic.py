"""add india airports, runways and monthly airport traffic

Revision ID: d3f5a7c9e1b4
Revises: d5f1a7c3e9b4
Create Date: 2026-10-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3f5a7c9e1b4'
down_revision: Union[str, Sequence[str], None] = 'd5f1a7c3e9b4'
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
    op.create_table('india_airports',
    sa.Column('ident', sa.String(), nullable=False),
    sa.Column('icao_code', sa.String(), nullable=True),
    sa.Column('iata_code', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('airport_type', sa.String(), nullable=False),
    sa.Column('municipality', sa.String(), nullable=True),
    sa.Column('latitude_deg', sa.Float(), nullable=True),
    sa.Column('longitude_deg', sa.Float(), nullable=True),
    sa.Column('elevation_ft', sa.Float(), nullable=True),
    sa.Column('scheduled_service', sa.Boolean(), nullable=False),
    sa.Column('frequency_count', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_india_airports_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_india_airports')),
    sa.UniqueConstraint('ident', name='uq_india_airports_ident')
    )
    op.create_index(op.f('ix_india_airports_icao_code'), 'india_airports', ['icao_code'], unique=False)
    op.create_index(op.f('ix_india_airports_iata_code'), 'india_airports', ['iata_code'], unique=False)
    op.create_table('india_runways',
    sa.Column('ourairports_id', sa.Integer(), nullable=False),
    sa.Column('airport_ident', sa.String(), nullable=False),
    sa.Column('length_ft', sa.Float(), nullable=True),
    sa.Column('width_ft', sa.Float(), nullable=True),
    sa.Column('surface', sa.String(), nullable=True),
    sa.Column('lighted', sa.Boolean(), nullable=False),
    sa.Column('closed', sa.Boolean(), nullable=False),
    sa.Column('le_ident', sa.String(), nullable=True),
    sa.Column('he_ident', sa.String(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_india_runways_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_india_runways')),
    sa.UniqueConstraint('ourairports_id', name='uq_india_runways_ourairports_id')
    )
    op.create_index(op.f('ix_india_runways_airport_ident'), 'india_runways', ['airport_ident'], unique=False)
    op.create_table('airport_traffic_monthly',
    sa.Column('airport_name', sa.String(), nullable=False),
    sa.Column('iata_code', sa.String(), nullable=True),
    sa.Column('icao_code', sa.String(), nullable=True),
    sa.Column('period', sa.String(), nullable=False),
    sa.Column('aircraft_movements', sa.Integer(), nullable=True),
    sa.Column('passengers', sa.Integer(), nullable=True),
    sa.Column('freight_tonnes', sa.Float(), nullable=True),
    sa.Column('movements_domestic', sa.Integer(), nullable=True),
    sa.Column('movements_international', sa.Integer(), nullable=True),
    sa.Column('passengers_domestic', sa.Integer(), nullable=True),
    sa.Column('passengers_international', sa.Integer(), nullable=True),
    sa.Column('freight_domestic_tonnes', sa.Float(), nullable=True),
    sa.Column('freight_international_tonnes', sa.Float(), nullable=True),
    sa.Column('movements_yoy_pct', sa.Float(), nullable=True),
    sa.Column('passengers_yoy_pct', sa.Float(), nullable=True),
    sa.Column('freight_yoy_pct', sa.Float(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    *_base_columns(),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_airport_traffic_monthly_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_airport_traffic_monthly')),
    sa.UniqueConstraint('airport_name', 'period', name='uq_airport_traffic_monthly_airport_name_period')
    )
    op.create_index(op.f('ix_airport_traffic_monthly_iata_code'), 'airport_traffic_monthly', ['iata_code'], unique=False)
    op.create_index(op.f('ix_airport_traffic_monthly_icao_code'), 'airport_traffic_monthly', ['icao_code'], unique=False)
    op.create_index(op.f('ix_airport_traffic_monthly_period'), 'airport_traffic_monthly', ['period'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('airport_traffic_monthly')
    op.drop_table('india_runways')
    op.drop_table('india_airports')
