"""Add api_key_id to apps and functions tables

Revision ID: add_api_key_id_001
Revises: 48bf142a794c
Create Date: 2025-07-18 00:01:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_api_key_id_001'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add api_key_id column to apps table (nullable, for user-created custom apps)
    op.add_column('apps', sa.Column('api_key_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_apps_api_key_id', 'apps', 'api_keys', ['api_key_id'], ['id'])

    # Add api_key_id column to functions table (nullable, for user-created custom functions)
    op.add_column('functions', sa.Column('api_key_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_functions_api_key_id', 'functions', 'api_keys', ['api_key_id'], ['id'])


def downgrade() -> None:
    # Drop foreign keys first
    op.drop_constraint('fk_functions_api_key_id', 'functions', type_='foreignkey')
    op.drop_column('functions', 'api_key_id')

    op.drop_constraint('fk_apps_api_key_id', 'apps', type_='foreignkey')
    op.drop_column('apps', 'api_key_id')
