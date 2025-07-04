"""Create MessageRole enum type

Revision ID: 7daf5881de02
Revises: 
Create Date: 2025-07-04 14:43:25.753533

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7daf5881de02'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the MessageRole enum type if it doesn't exist
    op.execute("DO $$ BEGIN CREATE TYPE messagerole AS ENUM ('user', 'assistant', 'system'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # Convert the role column from VARCHAR with CHECK constraint to enum
    op.alter_column('messages', 'role',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.Enum('user', 'assistant', 'system', name='messagerole'),
               existing_nullable=False,
               postgresql_using='role::messagerole')


def downgrade() -> None:
    # Convert the role column back to VARCHAR with CHECK constraint
    op.alter_column('messages', 'role',
               existing_type=sa.Enum('user', 'assistant', 'system', name='messagerole'),
               type_=sa.VARCHAR(length=20),
               existing_nullable=False)
    
    # Drop the MessageRole enum type
    op.execute("DROP TYPE IF EXISTS messagerole")