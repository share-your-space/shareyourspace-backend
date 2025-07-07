from typing import List, Optional, Dict, Any

from sqlalchemy import update
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload # Changed from AsyncSession for now if using Session
from sqlalchemy.ext.asyncio import AsyncSession # Keep if truly async
from sqlalchemy import func, or_, and_

from app.models.organization import Company, Startup
from app.schemas.organization import CompanyCreate, CompanyUpdate, StartupCreate, StartupUpdate
from app.models.user import User
from app.models.enums import UserStatus, NotificationType, UserRole
from app.crud.crud_notification import create_notification
from app.crud.crud_user import create_user, get_user_by_email, update_user_internal, get_admin_for_company, get_admin_for_startup
from app.schemas.user import UserCreate, UserUpdateInternal
from app.crud.crud_connection import create_accepted_connection
import logging
from app.crud import crud_space  # Local import to avoid circular dependency
from app.models.interest import Interest

logger = logging.getLogger(__name__)

# CRUD for Company
async def get_company(db: AsyncSession, company_id: int) -> Optional[Company]:
    logger.info(f"CRUD: Attempting to fetch company with ID: {company_id}")
    result = await db.execute(
        select(Company).filter(Company.id == company_id)
    )
    company = result.scalars().first()
    if company:
        logger.info(f"CRUD: Found company '{company.name}' with ID: {company.id}. Fetching admin...")
        company.admin = await get_admin_for_company(db, company_id=company.id)
        if company.admin:
            logger.info(f"CRUD: Found admin '{company.admin.email}' for company {company.id}.")
        else:
            logger.warning(f"CRUD: No admin found for company {company.id}.")
    else:
        logger.warning(f"CRUD: Company with ID {company_id} not found in database.")
    return company

async def get_company_by_name(db: AsyncSession, name: str) -> Optional[Company]:
    result = await db.execute(select(Company).filter(Company.name == name))
    return result.scalars().first()

async def get_companies(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Company]:
    result = await db.execute(select(Company).offset(skip).limit(limit))
    return result.scalars().all()

async def create_company(db: AsyncSession, *, obj_in: CompanyCreate) -> Company:
    obj_in_data = obj_in.model_dump()
    if obj_in_data.get("website"):
        obj_in_data["website"] = str(obj_in_data["website"])
    if obj_in_data.get("social_media_links"):
        obj_in_data["social_media_links"] = {k: str(v) for k, v in obj_in_data["social_media_links"].items()}
        
    db_obj = Company(**obj_in_data)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def update_company(db: AsyncSession, *, db_obj: Company, obj_in: CompanyUpdate) -> Company:
    update_data = obj_in.model_dump(exclude_unset=True)

    # Convert HttpUrl fields to strings before saving
    if 'website' in update_data and update_data['website']:
        update_data['website'] = str(update_data['website'])
    if 'social_media_links' in update_data and update_data['social_media_links']:
        update_data['social_media_links'] = {k: str(v) for k, v in update_data['social_media_links'].items()}

    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    # Eager load admin after update
    db_obj.admin = await get_admin_for_company(db, company_id=db_obj.id)
    return db_obj

async def delete_company(db: AsyncSession, *, db_obj: Company) -> Company:
    await db.delete(db_obj)
    await db.commit()
    # After commit, the db_obj is expired. We should probably return the ID or a confirmation.
    # For now, returning the (expired) object to match other CRUD patterns.
    return db_obj

# CRUD for Startup
async def get_startup(db: AsyncSession, startup_id: int, options: Optional[List] = None) -> Optional[Startup]:
    """Fetch a single startup by its ID."""
    query = select(Startup).where(Startup.id == startup_id)
    
    # Eager load relationships for the schema
    query = query.options(
        selectinload(Startup.direct_members).selectinload(User.profile),
        selectinload(Startup.space)
    )

    if options:
        query = query.options(*options)
    
    result = await db.execute(query)
    startup = result.scalars().first()

    if startup:
        # Manually count used slots to ensure data consistency before serialization.
        # This prevents validation errors if the stored `member_slots_used` is out of sync.
        count_query = select(func.count(User.id)).where(User.startup_id == startup_id)
        count_result = await db.execute(count_query)
        startup.member_slots_used = count_result.scalar_one()

    return startup

async def get_waitlisted_startups(
    db: AsyncSession,
    *,
    search_term: Optional[str] = None,
    space_id: Optional[int] = None,
    filter_by_interest: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetches waitlisted startups with optional filtering and annotates them
    with interest information for a specific space.
    """
    # Base join condition for the outerjoin
    join_conditions = [
        Interest.startup_id == Startup.id,
        Interest.status == "PENDING",
    ]
    if space_id is not None:
        join_conditions.append(Interest.space_id == space_id)

    stmt = (
        select(
            Startup,
            Interest.id.label("interest_id"),
            (Interest.id != None).label("expressed_interest"),
        )
        .outerjoin(
            Interest,
            and_(*join_conditions),
        )
        .options(selectinload(Startup.direct_members).selectinload(User.profile))
        .where(Startup.status == UserStatus.WAITLISTED)
    )

    if filter_by_interest:
        stmt = stmt.where(Interest.id.isnot(None))

    if search_term:
        stmt = stmt.filter(
            or_(
                Startup.name.ilike(f"%{search_term}%"),
                Startup.description.ilike(f"%{search_term}%"),
            )
        )

    result = await db.execute(stmt)

    startups = []
    for row in result.all():
        startup_data = row.Startup.__dict__
        startup_data["expressed_interest"] = row.expressed_interest
        startup_data["interest_id"] = row.interest_id
        startups.append(startup_data)
        
    return startups


async def get_startup_by_name(db: AsyncSession, name: str) -> Optional[Startup]:
    result = await db.execute(select(Startup).filter(Startup.name == name))
    return result.scalars().first()

async def get_startups(
    db: AsyncSession,
    *,
    status: Optional[UserStatus] = None,
    skip: int = 0,
    limit: int = 100,
    search_term: Optional[str] = None,
    include_ids: Optional[List[int]] = None,
) -> List[Startup]:
    """
    Fetches startups with optional filtering by status, search term, and a specific list of IDs.
    """
    stmt = select(Startup).options(
        selectinload(Startup.direct_members).selectinload(User.profile)
    )

    if status:
        stmt = stmt.filter(Startup.status == status)

    if include_ids is not None:
        if not include_ids:
            return []  # If a filter list is provided and it's empty, return no results.
        stmt = stmt.filter(Startup.id.in_(include_ids))

    if search_term:
        stmt = stmt.filter(
            or_(
                Startup.name.ilike(f"%{search_term}%"),
                Startup.description.ilike(f"%{search_term}%"),
            )
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_startup(db: AsyncSession, *, obj_in: StartupCreate, admin_user: User) -> Startup:
    obj_in_data = obj_in.model_dump()
    if obj_in_data.get("website"):
        obj_in_data["website"] = str(obj_in_data["website"])
    if obj_in_data.get("pitch_deck_url"):
        obj_in_data["pitch_deck_url"] = str(obj_in_data["pitch_deck_url"])
    if obj_in_data.get("social_media_links"):
        obj_in_data["social_media_links"] = {k: str(v) for k, v in obj_in_data["social_media_links"].items()}

    db_obj = Startup(**obj_in_data)
    db_obj.direct_members.append(admin_user)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def update_startup(db: AsyncSession, *, db_obj: Startup, obj_in: StartupUpdate) -> Startup:
    update_data = obj_in.model_dump(exclude_unset=True)

    # Convert HttpUrl fields to strings before saving
    if 'website' in update_data and update_data['website']:
        update_data['website'] = str(update_data['website'])
    if 'pitch_deck_url' in update_data and update_data['pitch_deck_url']:
        update_data['pitch_deck_url'] = str(update_data['pitch_deck_url'])
    if 'social_media_links' in update_data and update_data['social_media_links']:
        update_data['social_media_links'] = {k: str(v) for k, v in update_data['social_media_links'].items()}
        
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    # Eager load admin after update
    db_obj.admin = await get_admin_for_startup(db, startup_id=db_obj.id)
    return db_obj

async def delete_startup(db: AsyncSession, *, db_obj: Startup) -> Startup:
    await db.delete(db_obj)
    await db.commit()
    return db_obj

# Placeholder for get_company_by_admin_user - will require linking users to companies
# async def get_company_by_admin_user(db: AsyncSession, user_id: int) -> Optional[Company]:
#     # This needs the Company model to have a direct FK to the admin user, 
#     # or a join through an association table/role.
#     # result = await db.execute(
#     #     select(Company).join(User).filter(Company.admin_id == user_id)
#     # )
#     # return result.scalars().first()
#     pass

async def get_startups_by_space_id(db: AsyncSession, space_id: int) -> list[Startup]:
    """Fetches all startups associated with a given space_id."""
    result = await db.execute(
        select(Startup)
        .filter(Startup.space_id == space_id)
        .order_by(Startup.name) # Optional: order by name
    )
    return result.scalars().all()

async def remove_startup_member(db: AsyncSession, *, member_to_remove: "User", removing_admin: "User") -> "User":
    """
    Removes a member from a startup.
    - Verifies that the remover is an admin of the same startup as the member.
    - Sets the member's startup_id and space_id to None.
    - Unassigns the member from any workstation in that space.
    """
    if not removing_admin.startup_id or removing_admin.startup_id != member_to_remove.startup_id:
        raise ValueError("Admin can only remove members from their own startup.")

    if removing_admin.id == member_to_remove.id:
        raise ValueError("Admins cannot remove themselves.")

    startup = await get_startup(db, startup_id=removing_admin.startup_id)
    if not startup:
        # This case should ideally not be reached if the foreign key constraints are sound
        raise ValueError("Startup not found for the removing admin.")

    # Decrement the used member slots count
    if startup.member_slots_used > 0:
        startup.member_slots_used -= 1
        db.add(startup)

    space_id_to_clear = member_to_remove.space_id
    member_id = member_to_remove.id
    startup_name = startup.name
    
    member_to_remove.startup_id = None
    member_to_remove.space_id = None
    member_to_remove.status = UserStatus.ACTIVE
    
    db.add(member_to_remove)

    # If the user was in a space, unassign them from workstations in that space
    if space_id_to_clear:
        from app.crud.crud_space import unassign_user_from_all_workstations_in_space
        await unassign_user_from_all_workstations_in_space(db=db, user_id=member_id, space_id=space_id_to_clear)

    await create_notification(
        db=db,
        user_id=member_id,
        type=NotificationType.REMOVED_FROM_SPACE,
        message=f"You have been removed from startup '{startup_name}' and your status has been updated to active.",
        reference=f"startup_id:{removing_admin.startup_id}",
        link="/dashboard"
    )

    await db.commit()
    
    from app.crud import crud_user
    refreshed_user = await crud_user.get_user_by_id(db, user_id=member_id, options=[
        selectinload(User.profile),
        selectinload(User.space),
        selectinload(User.managed_space),
        selectinload(User.company),
        selectinload(User.startup),
    ])

    if refreshed_user is None:
        raise Exception("Could not retrieve user details after update.")

    return refreshed_user

# Add create_startup, update_startup later if needed

# Potentially add get_company_by_admin_user, get_startup_by_admin_user later 

async def get_startup_member_count(db: AsyncSession, *, startup_id: int) -> int:
    """Get the number of members in a startup."""
    stmt = select(func.count(User.id)).where(User.startup_id == startup_id)
    result = await db.execute(stmt)
    return result.scalar_one()

async def add_startup_to_space(db: AsyncSession, *, startup_id: int, space_id: int) -> Startup:
    """
    Adds a startup and all its members to a space.
    Updates the status of the startup and its members to ACTIVE.
    This function does NOT commit the transaction.
    """
    startup = await get_startup(db, startup_id=startup_id, options=[selectinload(Startup.direct_members)])
    if not startup:
        raise ValueError(f"Startup with id {startup_id} not found.")

    space = await crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise ValueError(f"Space with id {space_id} not found.")

    # Update the startup's space_id and status
    startup.space_id = space_id
    startup.status = UserStatus.ACTIVE
    db.add(startup)

    # Update all members of the startup
    if startup.direct_members:
        for member in startup.direct_members:
            member.space_id = space_id
            member.status = UserStatus.ACTIVE
            db.add(member)
            
            if space.corporate_admin_id and space.corporate_admin_id != member.id:
                try:
                    # Note: This connection creation will be part of the parent transaction
                    await create_accepted_connection(
                        db=db,
                        user_one_id=member.id,
                        user_two_id=space.corporate_admin_id
                    )
                    logger.info(f"Staged automatic connection between startup member {member.id} and corporate admin {space.corporate_admin_id}")
                except Exception as e:
                    logger.error(f"Failed to stage automatic connection for startup member {member.id} with admin {space.corporate_admin_id}: {e}")
    
    # No commit here - will be handled by the calling service.
    return startup

async def add_user_to_startup(
    db: AsyncSession,
    *,
    email: str,
    full_name: Optional[str],
    startup: Startup,
    space_id: int,
    adding_admin: User,
) -> User:
    """
    Adds a new or existing user to a startup and space, and activates them.
    """
    user = await get_user_by_email(db, email=email)
    if not user:
        # Create a user without a password, they will set it via an email link
        user_in = UserCreate(email=email, password="DUMMY_PASSWORD_NEVER_USED", full_name=full_name)
        user = await create_user(db, obj_in=user_in, role=UserRole.STARTUP_MEMBER, status=UserStatus.PENDING_VERIFICATION)

    # Activate user and assign to startup and space
    update_data = UserUpdateInternal(
        is_active=True,
        status=UserStatus.ACTIVE,
        startup_id=startup.id,
        space_id=space_id,
        role=UserRole.STARTUP_MEMBER
    )
    updated_user = await update_user_internal(db=db, db_obj=user, obj_in=update_data)

    # Increment the used member slots count
    if startup.member_slots_used < startup.member_slots_allocated:
        startup.member_slots_used += 1
        db.add(startup)

    await db.commit()
    await db.refresh(updated_user)
    return updated_user 

async def bulk_update_startup_space(db: AsyncSession, *, startup_ids: List[int], space_id: Optional[int]):
    """
    Bulk updates the space_id for a list of startups.
    """
    if not startup_ids:
        return
    stmt = (
        update(Startup)
        .where(Startup.id.in_(startup_ids))
        .values(space_id=space_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)

# Placeholder for get_company_by_admin_user - will require linking users to companies
# async def get_company_by_admin_user(db: AsyncSession, user_id: int) -> Optional[Company]:
#     # This needs the Company model to have a direct FK to the admin user, 
#     # or a join through an association table/role.
#     # result = await db.execute(
#     #     select(Company).join(User).filter(Company.admin_id == user_id)
#     # )
#     # return result.scalars().first()
#     pass 