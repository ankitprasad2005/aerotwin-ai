"""add cargo demand

Revision ID: e9b2c4d6f8a1
Revises: d7a1b3c5e9f2
Create Date: 2026-10-14 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9b2c4d6f8a1'
down_revision: Union[str, Sequence[str], None] = 'd7a1b3c5e9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cargo demand for the routes app/seed/seed.py creates. Seeding no-ops once airports exist, so an
# already-seeded database only gets these rows through this backfill; on a fresh database no routes exist
# yet, so nothing is inserted and the seed script adds them. Kept as literals rather than imported from
# app.seed.data so this migration stays fixed if the seed data changes later.
_SEEDED_CARGO_DEMAND = [
    # (origin, destination, period, weekly_demand_kg, capacity_kg_per_flight, rate_usd_per_kg, handling_cost_usd_per_kg)
    ("BOM", "DEL", "2026-Q3", 16000.0, 2000.0, 1.2, 0.3),
    ("DEL", "BOM", "2026-Q3", 9000.0, 2000.0, 1.2, 0.3),
    ("BOM", "BLR", "2026-Q3", 8000.0, 1800.0, 1.0, 0.2),
    ("BLR", "HYD", "2026-Q3", 2000.0, 1500.0, 0.8, 0.2),
    ("MAA", "CCU", "2026-Q3", 2600.0, 1800.0, 1.1, 0.28),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cargo_demand',
    sa.Column('route_id', sa.UUID(), nullable=False),
    sa.Column('period', sa.String(), nullable=False),
    sa.Column('weekly_demand_kg', sa.Float(), nullable=False),
    sa.Column('capacity_kg_per_flight', sa.Float(), nullable=False),
    sa.Column('rate_usd_per_kg', sa.Float(), nullable=False),
    sa.Column('handling_cost_usd_per_kg', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name=op.f('fk_cargo_demand_route_id_routes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cargo_demand')),
    sa.UniqueConstraint('route_id', 'period', name='uq_cargo_demand_route_period')
    )
    op.create_index(op.f('ix_cargo_demand_route_id'), 'cargo_demand', ['route_id'], unique=False)

    for origin, destination, period, demand_kg, capacity_kg, rate, handling in _SEEDED_CARGO_DEMAND:
        op.execute(
            sa.text(
                "INSERT INTO cargo_demand (id, route_id, period, weekly_demand_kg, capacity_kg_per_flight, "
                "rate_usd_per_kg, handling_cost_usd_per_kg, created_at, updated_at) "
                "SELECT gen_random_uuid(), routes.id, :period, :demand_kg, :capacity_kg, :rate, :handling, "
                "now(), now() FROM routes "
                "JOIN airports AS origin ON routes.origin_id = origin.id "
                "JOIN airports AS destination ON routes.destination_id = destination.id "
                "WHERE origin.code = :origin AND destination.code = :destination"
            ).bindparams(
                period=period, demand_kg=demand_kg, capacity_kg=capacity_kg, rate=rate, handling=handling,
                origin=origin, destination=destination,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_cargo_demand_route_id'), table_name='cargo_demand')
    op.drop_table('cargo_demand')
