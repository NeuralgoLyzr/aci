"""Change org_id from UUID to String

Revision ID: 0001_change_org_id_to_string
Revises: 48bf142a794c
Create Date: 2025-09-17 00:01:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_change_org_id_to_string'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use explicit SQL to cast UUID to text safely for Postgres
    conn = op.get_bind()

    # projects.org_id
    op.alter_column('projects', 'org_id',
                    existing_type=postgresql.UUID(),
                    type_=sa.String(length=255),
                    existing_nullable=False,
                    postgresql_using='org_id::text')

    # subscriptions.org_id
    op.alter_column('subscriptions', 'org_id',
                    existing_type=postgresql.UUID(),
                    type_=sa.String(length=255),
                    existing_nullable=False,
                    postgresql_using='org_id::text')


def downgrade() -> None:
    # Convert text back to UUID (assumes valid UUID strings)
    op.alter_column('projects', 'org_id',
                    existing_type=sa.String(length=255),
                    type_=postgresql.UUID(),
                    existing_nullable=False,
                    postgresql_using='org_id::uuid')

    op.alter_column('subscriptions', 'org_id',
                    existing_type=sa.String(length=255),
                    type_=postgresql.UUID(),
                    existing_nullable=False,
                    postgresql_using='org_id::uuid')
