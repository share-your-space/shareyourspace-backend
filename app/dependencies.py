from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.security import get_current_active_user

def require_sys_admin(
    current_user: User = Depends(get_current_active_user)
):
    """Dependency to check if the current user has the SYS_ADMIN role."""
    if current_user.role != 'SYS_ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user 