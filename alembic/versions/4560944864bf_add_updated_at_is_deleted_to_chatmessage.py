"""add_updated_at_is_deleted_to_chatmessage

Revision ID: 4560944864bf
Revises: 61285376d591
Create Date: 2025-05-13 06:58:36.310140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4560944864bf'
down_revision: Union[str, None] = '61285376d591'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_messages', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('chat_messages', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'is_deleted')
    op.drop_column('chat_messages', 'updated_at')
