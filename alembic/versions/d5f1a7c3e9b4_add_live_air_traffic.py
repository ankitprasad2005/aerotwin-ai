"""add live air traffic tables

Revision ID: d5f1a7c3e9b4
Revises: b7e2c4d6f8a1
Create Date: 2026-10-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5f1a7c3e9b4'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4d6f8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('air_traffic_snapshots',
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('aircraft_over_india', sa.Integer(), nullable=False),
    sa.Column('airborne', sa.Integer(), nullable=False),
    sa.Column('on_ground', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_air_traffic_snapshots_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_air_traffic_snapshots')),
    sa.UniqueConstraint('taken_at', name='uq_air_traffic_snapshots_taken_at')
    )
    op.create_table('airport_traffic_live',
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('airport', sa.String(length=4), nullable=False),
    sa.Column('icao', sa.String(length=4), nullable=False),
    sa.Column('aircraft_within_radius', sa.Integer(), nullable=False),
    sa.Column('on_ground_nearby', sa.Integer(), nullable=False),
    sa.Column('airborne_nearby', sa.Integer(), nullable=False),
    sa.Column('arrivals_last_24h', sa.Integer(), nullable=True),
    sa.Column('departures_last_24h', sa.Integer(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_airport_traffic_live_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_airport_traffic_live')),
    sa.UniqueConstraint('taken_at', 'airport', name='uq_airport_traffic_live_taken_at_airport')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('airport_traffic_live')
    op.drop_table('air_traffic_snapshots')
