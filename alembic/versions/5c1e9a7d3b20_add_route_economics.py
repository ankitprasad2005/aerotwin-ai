"""add route economics (seats, fare, operating cost)

Revision ID: 5c1e9a7d3b20
Revises: ace374c086cc
Create Date: 2026-09-15 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1e9a7d3b20'
down_revision: Union[str, Sequence[str], None] = 'ace374c086cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Economics for the routes app/seed/seed.py creates. Seeding no-ops once airports exist, so an
# already-seeded database only gets these values through this backfill. Kept as literals rather
# than imported from app.seed.data so this migration stays fixed if the seed data changes later.
_SEEDED_ROUTE_ECONOMICS = [
    # (origin, destination, seats_per_flight, average_fare_usd, operating_cost_per_flight_usd)
    ("BOM", "DEL", 180, 95.0, 9000.0),
    ("DEL", "BOM", 180, 95.0, 9000.0),
    ("BOM", "BLR", 180, 70.0, 7000.0),
    ("BLR", "HYD", 180, 50.0, 4800.0),
    ("MAA", "CCU", 180, 85.0, 10500.0),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('routes', sa.Column('seats_per_flight', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('average_fare_usd', sa.Float(), nullable=True))
    op.add_column('routes', sa.Column('operating_cost_per_flight_usd', sa.Float(), nullable=True))

    for origin, destination, seats, fare, cost in _SEEDED_ROUTE_ECONOMICS:
        op.execute(
            sa.text(
                "UPDATE routes SET seats_per_flight = :seats, average_fare_usd = :fare, "
                "operating_cost_per_flight_usd = :cost "
                "FROM airports AS origin, airports AS destination "
                "WHERE routes.origin_id = origin.id AND routes.destination_id = destination.id "
                "AND origin.code = :origin AND destination.code = :destination"
            ).bindparams(seats=seats, fare=fare, cost=cost, origin=origin, destination=destination)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('routes', 'operating_cost_per_flight_usd')
    op.drop_column('routes', 'average_fare_usd')
    op.drop_column('routes', 'seats_per_flight')
