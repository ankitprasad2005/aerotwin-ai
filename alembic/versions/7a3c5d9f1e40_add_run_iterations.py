"""add run iterations (one per prompt in a run)

Revision ID: 7a3c5d9f1e40
Revises: 5c1e9a7d3b20
Create Date: 2026-09-16 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3c5d9f1e40'
down_revision: Union[str, Sequence[str], None] = '5c1e9a7d3b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'run_iterations',
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('objective', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['run_id'], ['orchestration_runs.id'],
            name=op.f('fk_run_iterations_run_id_orchestration_runs'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_run_iterations')),
        sa.UniqueConstraint('run_id', 'sequence', name='uq_run_iterations_run_sequence'),
    )
    op.create_index(op.f('ix_run_iterations_run_id'), 'run_iterations', ['run_id'], unique=False)

    for table in ('agent_executions', 'decisions'):
        op.add_column(table, sa.Column('iteration_id', sa.UUID(), nullable=True))
        op.create_index(op.f(f'ix_{table}_iteration_id'), table, ['iteration_id'], unique=False)
        op.create_foreign_key(
            op.f(f'fk_{table}_iteration_id_run_iterations'), table, 'run_iterations',
            ['iteration_id'], ['id'],
        )

    # Existing runs each become a single iteration carrying the run's own objective, so run history
    # from before follow-up prompts existed still groups and renders like any other run.
    op.execute(
        sa.text(
            "INSERT INTO run_iterations "
            "(id, run_id, sequence, objective, status, completed_at, created_at, updated_at) "
            "SELECT gen_random_uuid(), r.id, 1, r.objective, r.status, r.completed_at, "
            "r.created_at, r.updated_at FROM orchestration_runs r"
        )
    )
    for table in ('agent_executions', 'decisions'):
        op.execute(
            sa.text(
                f"UPDATE {table} SET iteration_id = i.id FROM run_iterations i "
                f"WHERE i.run_id = {table}.run_id AND i.sequence = 1"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('decisions', 'agent_executions'):
        op.drop_constraint(op.f(f'fk_{table}_iteration_id_run_iterations'), table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_iteration_id'), table_name=table)
        op.drop_column(table, 'iteration_id')
    op.drop_index(op.f('ix_run_iterations_run_id'), table_name='run_iterations')
    op.drop_table('run_iterations')
