"""add crew members

Revision ID: d7a1b3c5e9f2
Revises: c4d8e2f1a9b3
Create Date: 2026-10-14 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a1b3c5e9f2'
down_revision: Union[str, Sequence[str], None] = 'c4d8e2f1a9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Crew for the airports app/seed/seed.py creates. Seeding no-ops once airports exist, so an already-seeded
# database only gets these rows through this backfill; on a fresh database no airports exist yet, so nothing
# is inserted and the seed script adds them. Kept as literals rather than imported from app.seed.data so this
# migration stays fixed if the seed data changes later.
_SEEDED_CREW = [
    # (employee_code, name, role, base_airport_code, qualified_aircraft_type, status, weekly_duty_hours)
    ("CR-001", "Arjun Mehta", "CAPTAIN", "BOM", "A320", "AVAILABLE", 22.0),
    ("CR-002", "Neha Kapoor", "CAPTAIN", "BOM", "A320", "AVAILABLE", 36.0),
    ("CR-003", "Rohan Iyer", "FIRST_OFFICER", "BOM", "A320", "AVAILABLE", 18.0),
    ("CR-004", "Vikram Rao", "CAPTAIN", "DEL", "A320", "AVAILABLE", 10.0),
    ("CR-005", "Sana Khan", "FIRST_OFFICER", "DEL", "A320", "ON_LEAVE", 0.0),
    ("CR-006", "Priya Nair", "CAPTAIN", "BLR", "B737", "AVAILABLE", 15.0),
    ("CR-007", "Karthik Subramanian", "CAPTAIN", "MAA", "A321", "SICK", 0.0),
    ("CR-008", "Ishita Das", "FIRST_OFFICER", "MAA", "A321", "AVAILABLE", 40.0),
    ("CR-009", "Meera Joshi", "CABIN_CREW", "BOM", "ANY", "AVAILABLE", 12.0),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('crew_members',
    sa.Column('employee_code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('base_id', sa.UUID(), nullable=False),
    sa.Column('qualified_aircraft_type', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('weekly_duty_hours', sa.Float(), nullable=False),
    sa.Column('max_weekly_duty_hours', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['base_id'], ['airports.id'], name=op.f('fk_crew_members_base_id_airports')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crew_members')),
    sa.UniqueConstraint('employee_code', name=op.f('uq_crew_members_employee_code'))
    )
    op.create_index(op.f('ix_crew_members_base_id'), 'crew_members', ['base_id'], unique=False)

    for code, name, role, base, aircraft_type, status, duty_hours in _SEEDED_CREW:
        op.execute(
            sa.text(
                "INSERT INTO crew_members (id, employee_code, name, role, base_id, qualified_aircraft_type, "
                "status, weekly_duty_hours, max_weekly_duty_hours, created_at, updated_at) "
                "SELECT gen_random_uuid(), :code, :name, :role, airports.id, :aircraft_type, :status, "
                ":duty_hours, 40.0, now(), now() FROM airports WHERE airports.code = :base"
            ).bindparams(
                code=code, name=name, role=role, base=base, aircraft_type=aircraft_type,
                status=status, duty_hours=duty_hours,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_crew_members_base_id'), table_name='crew_members')
    op.drop_table('crew_members')
