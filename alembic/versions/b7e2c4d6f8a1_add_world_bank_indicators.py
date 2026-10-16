"""add world bank indicators

Revision ID: b7e2c4d6f8a1
Revises: a1d3f5b7c9e2
Create Date: 2026-10-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2c4d6f8a1'
down_revision: Union[str, Sequence[str], None] = 'a1d3f5b7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('world_bank_indicators',
    sa.Column('indicator', sa.String(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name=op.f('fk_world_bank_indicators_snapshot_id_dataset_snapshots')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_world_bank_indicators')),
    sa.UniqueConstraint('indicator', 'year', name='uq_world_bank_indicators_indicator_year')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('world_bank_indicators')
