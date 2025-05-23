"""Add last_read_at to ConversationParticipant

Revision ID: 08eced71251f
Revises: f6faaa54ca44
Create Date: 2025-05-13 05:49:17.342621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08eced71251f'
down_revision: Union[str, None] = 'f6faaa54ca44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('conversation_participants', sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    op.add_column('conversation_participants', sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint('conversation_participants_user_id_fkey', 'conversation_participants', type_='foreignkey')
    op.drop_constraint('conversation_participants_conversation_id_fkey', 'conversation_participants', type_='foreignkey')
    op.create_foreign_key(None, 'conversation_participants', 'conversations', ['conversation_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'conversation_participants', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'conversation_participants', type_='foreignkey')
    op.drop_constraint(None, 'conversation_participants', type_='foreignkey')
    op.create_foreign_key('conversation_participants_conversation_id_fkey', 'conversation_participants', 'conversations', ['conversation_id'], ['id'])
    op.create_foreign_key('conversation_participants_user_id_fkey', 'conversation_participants', 'users', ['user_id'], ['id'])
    op.drop_column('conversation_participants', 'last_read_at')
    op.drop_column('conversation_participants', 'joined_at')
    # ### end Alembic commands ###
