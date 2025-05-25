"""update_invitationstatus_enum_and_values

Revision ID: 43b26710d32d
Revises: a0ea2f0b7b3a
Create Date: <will be filled by Alembic>

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '43b26710d32d'
down_revision = 'a0ea2f0b7b3a' # Previous migration that added declined_at/reason fields
branch_labels = None
depends_on = None

# Define enum names
table_name = 'invitations'
column_name = 'status'
enum_name = 'invitationstatus' # This is the actual name of the enum type in PostgreSQL
temp_enum_name = f'{enum_name}_old'

# Desired final lowercase values for the enum
new_enum_values = ('pending', 'accepted', 'expired', 'revoked', 'declined')

# Original uppercase values (assumed from migration a0f683693a70)
original_enum_values_uppercase = ('PENDING', 'ACCEPTED', 'EXPIRED')


def upgrade():
    # Rename the existing enum type
    op.execute(f"ALTER TYPE {enum_name} RENAME TO {temp_enum_name};")
    
    # Create the new enum type with all correct lowercase values
    new_enum_sa = sa.Enum(*new_enum_values, name=enum_name)
    new_enum_sa.create(op.get_bind(), checkfirst=False)
    
    # Alter the column to use the new enum type
    # This involves casting existing uppercase values to lowercase, then to the new enum type
    op.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {enum_name} "
        f"USING LOWER({column_name}::text)::{enum_name};"
    )
    
    # Drop the old (renamed) enum type
    op.execute(f"DROP TYPE {temp_enum_name};")


def downgrade():
    # This downgrade reverts to the state where the enum was ('PENDING', 'ACCEPTED', 'EXPIRED') - uppercase.
    # Data for 'revoked' and 'declined' statuses will be mapped to 'EXPIRED' as they didn't exist.
    
    temp_new_enum_name = f'{enum_name}_temp_new'

    # Rename the current (new) enum type
    op.execute(f"ALTER TYPE {enum_name} RENAME TO {temp_new_enum_name};")
    
    # Recreate the original enum type with uppercase values
    original_enum_sa = sa.Enum(*original_enum_values_uppercase, name=enum_name)
    original_enum_sa.create(op.get_bind(), checkfirst=False)
    
    # Alter the column back to the old enum type
    # Map current lowercase values back to old uppercase ones.
    # 'revoked' and 'declined' will be mapped to 'EXPIRED'.
    # Other values (like 'pending') will be uppercased.
    op.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {enum_name} "
        f"USING CASE "
        f"  WHEN LOWER({column_name}::text) = 'pending' THEN 'PENDING'::{enum_name} "
        f"  WHEN LOWER({column_name}::text) = 'accepted' THEN 'ACCEPTED'::{enum_name} "
        f"  WHEN LOWER({column_name}::text) = 'expired' THEN 'EXPIRED'::{enum_name} "
        f"  WHEN LOWER({column_name}::text) = 'revoked' THEN 'EXPIRED'::{enum_name} "
        f"  WHEN LOWER({column_name}::text) = 'declined' THEN 'EXPIRED'::{enum_name} "
        # Fallback for any values that might have been directly PENDING, ACCEPTED, EXPIRED (already uppercase)
        f"  WHEN {column_name}::text IN {original_enum_values_uppercase} THEN {column_name}::text::{enum_name} "
        f"  ELSE 'EXPIRED'::{enum_name} " # Default for any unexpected status
        f"END;"
    )
    
    # Drop the temporary new enum type
    op.execute(f"DROP TYPE {temp_new_enum_name};")
