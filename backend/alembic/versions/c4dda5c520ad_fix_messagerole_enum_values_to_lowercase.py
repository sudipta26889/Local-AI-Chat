"""Fix MessageRole enum values to lowercase

Revision ID: c4dda5c520ad
Revises: 7daf5881de02
Create Date: 2025-07-04 14:50:04.058513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4dda5c520ad'
down_revision: Union[str, None] = '7daf5881de02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First convert column to VARCHAR to update values
    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE VARCHAR(20)")
    
    # Update existing data to lowercase
    op.execute("UPDATE messages SET role = 'user' WHERE role = 'USER'")
    op.execute("UPDATE messages SET role = 'assistant' WHERE role = 'ASSISTANT'")
    op.execute("UPDATE messages SET role = 'system' WHERE role = 'SYSTEM'")
    
    # Drop the existing enum type and recreate with lowercase values
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("CREATE TYPE messagerole AS ENUM ('user', 'assistant', 'system')")
    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE messagerole USING role::messagerole")


def downgrade() -> None:
    # Revert to uppercase enum values
    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE VARCHAR(20)")
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("CREATE TYPE messagerole AS ENUM ('USER', 'ASSISTANT', 'SYSTEM')")
    op.execute("UPDATE messages SET role = UPPER(role)")
    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE messagerole USING role::messagerole")