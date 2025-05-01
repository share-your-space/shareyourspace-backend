"""Change connection status to Enum

Revision ID: 0581da68b2ba
Revises: 7bd0250369dc
Create Date: 2025-04-29 09:13:58.949165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0581da68b2ba'
down_revision: Union[str, None] = '7bd0250369dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the new enum type for convenience
connectionstatus_enum = sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'BLOCKED', name='connectionstatus')

def upgrade() -> None:
    """Upgrade schema using multi-step process."""
    # 1. Create the ENUM type
    connectionstatus_enum.create(op.get_bind(), checkfirst=False)
    
    # 2. Add a new temporary column with the ENUM type
    op.add_column('connections', sa.Column('status_new', connectionstatus_enum, nullable=True))
    
    # 3. Update the new column based on the old string column values
    op.execute("""
        UPDATE connections
        SET status_new = CASE status
            WHEN 'pending' THEN 'PENDING'::connectionstatus
            WHEN 'accepted' THEN 'ACCEPTED'::connectionstatus
            WHEN 'declined' THEN 'DECLINED'::connectionstatus
            WHEN 'blocked' THEN 'BLOCKED'::connectionstatus
            ELSE NULL -- Or handle unexpected values appropriately
        END
    """)
    
    # 4. Make the new column non-nullable (assuming all rows were updated)
    op.alter_column('connections', 'status_new', nullable=False)
    
    # 5. Drop the old VARCHAR status column
    op.drop_column('connections', 'status')
    
    # 6. Rename the new column to 'status'
    op.alter_column('connections', 'status_new', new_column_name='status')


def downgrade() -> None:
    """Downgrade schema using multi-step process."""
    # 1. Add back the old VARCHAR column (nullable temporarily)
    op.add_column('connections', sa.Column('status_old', sa.VARCHAR(), nullable=True))
    
    # 2. Update the old column based on the ENUM values
    op.execute("""
        UPDATE connections
        SET status_old = status::text -- Cast enum back to text
    """)
    
    # 3. Make the old column non-nullable
    op.alter_column('connections', 'status_old', nullable=False)
    
    # 4. Drop the ENUM status column
    op.drop_column('connections', 'status')
    
    # 5. Rename the old column back to 'status'
    op.alter_column('connections', 'status_old', new_column_name='status')
    
    # 6. Drop the ENUM type
    connectionstatus_enum.drop(op.get_bind(), checkfirst=False)
