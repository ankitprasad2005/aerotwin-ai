"""add maintenance records

Revision ID: c4d8e2f1a9b3
Revises: 7a3c5d9f1e40
Create Date: 2026-10-14 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f1a9b3'
down_revision: Union[str, Sequence[str], None] = '7a3c5d9f1e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Maintenance items for the aircraft app/seed/seed.py creates. Seeding no-ops once airports exist, so
# an already-seeded database only gets these rows through this backfill; on a fresh database no aircraft
# exist yet, so nothing is inserted and the seed script adds them. Kept as literals rather than imported
# from app.seed.data so this migration stays fixed if the seed data changes later.
_SEEDED_MAINTENANCE_RECORDS = [
    # (tail_number, check_type, status, due_at_flight_hours, open_defects, notes)
    ("VT-AER1", "A_CHECK", "SCHEDULED", 4350.0, 0, "Routine A-check"),
    ("VT-AER2", "C_CHECK", "COMPLETED", 1800.0, 0, "Completed C-check"),
    ("VT-AER2", "A_CHECK", "SCHEDULED", 2600.0, 0, "Routine A-check"),
    ("VT-AER3", "C_CHECK", "IN_PROGRESS", 9050.0, 2, "Heavy check in progress, two open defects"),
    ("VT-AER4", "A_CHECK", "SCHEDULED", 1000.0, 0, "Routine A-check"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('maintenance_records',
    sa.Column('aircraft_id', sa.UUID(), nullable=False),
    sa.Column('check_type', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('due_at_flight_hours', sa.Float(), nullable=False),
    sa.Column('open_defects', sa.Integer(), nullable=False),
    sa.Column('notes', sa.String(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id'], name=op.f('fk_maintenance_records_aircraft_id_aircraft')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_maintenance_records'))
    )
    op.create_index(op.f('ix_maintenance_records_aircraft_id'), 'maintenance_records', ['aircraft_id'], unique=False)

    for tail, check_type, status, due_hours, defects, notes in _SEEDED_MAINTENANCE_RECORDS:
        op.execute(
            sa.text(
                "INSERT INTO maintenance_records (id, aircraft_id, check_type, status, due_at_flight_hours, "
                "open_defects, notes, created_at, updated_at) "
                "SELECT gen_random_uuid(), aircraft.id, :check_type, :status, :due_hours, :defects, :notes, "
                "now(), now() FROM aircraft WHERE aircraft.tail_number = :tail"
            ).bindparams(
                tail=tail, check_type=check_type, status=status, due_hours=due_hours, defects=defects, notes=notes
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_maintenance_records_aircraft_id'), table_name='maintenance_records')
    op.drop_table('maintenance_records')
