"""add airworthiness directive and taf tables

Revision ID: c7e2a9d4b6f8
Revises: b7e2c4d6f8a0
Create Date: 2026-10-16 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7e2a9d4b6f8'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4d6f8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('airworthiness_directives',
    sa.Column('document_number', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('publication_date', sa.Date(), nullable=False),
    sa.Column('html_url', sa.String(), nullable=False),
    sa.Column('abstract', sa.Text(), nullable=True),
    sa.Column('aircraft_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_airworthiness_directives_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_airworthiness_directives')),
    sa.UniqueConstraint('document_number', name=op.f('uq_airworthiness_directives_document_number'))
    )
    op.create_index(op.f('ix_airworthiness_directives_publication_date'), 'airworthiness_directives', ['publication_date'], unique=False)
    op.create_table('weather_tafs',
    sa.Column('airport', sa.String(length=4), nullable=False),
    sa.Column('icao', sa.String(length=4), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=False),
    sa.Column('worst_flight_category_24h', sa.String(), nullable=False),
    sa.Column('thunderstorm_24h', sa.Boolean(), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_weather_tafs_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_weather_tafs')),
    sa.UniqueConstraint('airport', 'issued_at', name='uq_weather_tafs_airport_issued_at')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('weather_tafs')
    op.drop_index(op.f('ix_airworthiness_directives_publication_date'), table_name='airworthiness_directives')
    op.drop_table('airworthiness_directives')
