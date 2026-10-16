"""add weather tables

Revision ID: a1d3f5b7c9e2
Revises: f3c5a7e9b1d2
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1d3f5b7c9e2'
down_revision: Union[str, Sequence[str], None] = 'f3c5a7e9b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('weather_observations',
    sa.Column('airport', sa.String(length=4), nullable=False),
    sa.Column('icao', sa.String(length=4), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('flight_category', sa.String(), nullable=False),
    sa.Column('wind_kt', sa.Float(), nullable=False),
    sa.Column('gust_kt', sa.Float(), nullable=True),
    sa.Column('visibility_sm', sa.Float(), nullable=True),
    sa.Column('ceiling_ft', sa.Float(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_weather_observations_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_weather_observations')),
    sa.UniqueConstraint('airport', 'observed_at', name='uq_weather_observations_airport_observed_at')
    )
    op.create_table('weather_forecasts',
    sa.Column('airport', sa.String(length=4), nullable=False),
    sa.Column('forecast_date', sa.Date(), nullable=False),
    sa.Column('precipitation_mm', sa.Float(), nullable=False),
    sa.Column('max_gust_kmh', sa.Float(), nullable=False),
    sa.Column('weather_code', sa.Integer(), nullable=False),
    sa.Column('thunderstorm', sa.Boolean(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_weather_forecasts_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_weather_forecasts')),
    sa.UniqueConstraint('airport', 'forecast_date', name='uq_weather_forecasts_airport_forecast_date')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('weather_forecasts')
    op.drop_table('weather_observations')
