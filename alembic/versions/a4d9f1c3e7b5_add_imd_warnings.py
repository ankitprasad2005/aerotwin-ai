"""add imd warnings

Revision ID: a4d9f1c3e7b5
Revises: b7e2c4d6f8a1
Create Date: 2026-10-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4d9f1c3e7b5'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4d6f8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('imd_warnings',
    sa.Column('identifier', sa.String(), nullable=False),
    sa.Column('issuer', sa.String(), nullable=False),
    sa.Column('event', sa.String(), nullable=False),
    sa.Column('severity_color', sa.String(), nullable=False),
    sa.Column('severity_level', sa.String(), nullable=True),
    sa.Column('area', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('effective_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_imd_warnings_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_imd_warnings')),
    sa.UniqueConstraint('identifier', name=op.f('uq_imd_warnings_identifier'))
    )
    op.create_index(op.f('ix_imd_warnings_effective_end'), 'imd_warnings', ['effective_end'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_imd_warnings_effective_end'), table_name='imd_warnings')
    op.drop_table('imd_warnings')
