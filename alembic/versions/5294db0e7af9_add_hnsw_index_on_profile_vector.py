"""Add hnsw index on profile_vector

Revision ID: 5294db0e7af9
Revises: c92880be338c
Create Date: 2025-04-28 04:53:48.538629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# Add pgvector import if needed for types, though op.execute uses raw SQL
# from pgvector.sqlalchemy import Vector 


# revision identifiers, used by Alembic.
revision: str = '5294db0e7af9'
down_revision: Union[str, None] = 'c92880be338c' # Corrected previous migration ID
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("CREATE INDEX ix_user_profiles_profile_vector_hnsw ON user_profiles USING hnsw (profile_vector vector_cosine_ops)")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("DROP INDEX ix_user_profiles_profile_vector_hnsw")
    # ### end Alembic commands ###
