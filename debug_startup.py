import asyncio
import os
import sys

# Add the app directory to the Python path
sys.path.append('/app')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from app.models.organization import Startup
from app.models.user import User
from app.schemas.organization import Startup as StartupSchema
import json

async def debug_startup():
    # Database connection
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/shareyourspace")
    
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Find a startup admin user first
        from sqlalchemy.future import select
        stmt = select(User).where(User.role == "STARTUP_ADMIN").limit(1)
        result = await db.execute(stmt)
        startup_admin = result.scalar_one_or_none()
        
        if not startup_admin:
            print("No startup admin found")
            return
            
        print(f"Found startup admin: {startup_admin.email} (ID: {startup_admin.id})")
        print(f"Startup ID: {startup_admin.startup_id}")
        
        if not startup_admin.startup_id:
            print("Startup admin has no startup_id")
            return
        
        # Get the startup with all relations
        stmt = (
            select(Startup)
            .where(Startup.id == startup_admin.startup_id)
            .options(selectinload(Startup.direct_members))
        )
        result = await db.execute(stmt)
        startup = result.scalar_one_or_none()
        
        if not startup:
            print("Startup not found")
            return
            
        print(f"\nStartup data:")
        print(f"ID: {startup.id}")
        print(f"Name: {startup.name}")
        print(f"Logo URL: {startup.logo_url}")
        print(f"Website: {startup.website}")
        print(f"Pitch deck URL: {startup.pitch_deck_url}")
        print(f"Social media links: {startup.social_media_links}")
        print(f"Status: {startup.status}")
        print(f"Member slots allocated: {startup.member_slots_allocated}")
        print(f"Direct members count: {len(startup.direct_members)}")
        
        # Check each direct member
        for i, member in enumerate(startup.direct_members):
            print(f"\nDirect member {i+1}:")
            print(f"  ID: {member.id}")
            print(f"  Email: {member.email}")
            print(f"  Full name: {member.full_name}")
            print(f"  Role: {member.role}")
        
        # Try to create the schema
        try:
            startup_schema = StartupSchema.model_validate(startup)
            print("\n✅ Schema validation successful!")
            print(f"Member slots used: {startup_schema.member_slots_used}")
        except Exception as e:
            print(f"\n❌ Schema validation failed: {e}")
            print(f"Error type: {type(e)}")
            
            # Try to identify which field is causing the issue
            startup_dict = {
                'id': startup.id,
                'name': startup.name,
                'logo_url': startup.logo_url,
                'industry_focus': startup.industry_focus,
                'description': startup.description,
                'website': startup.website,
                'team_size': startup.team_size,
                'looking_for': startup.looking_for,
                'social_media_links': startup.social_media_links,
                'mission': startup.mission,
                'stage': startup.stage,
                'pitch_deck_url': startup.pitch_deck_url,
                'status': startup.status,
                'created_at': startup.created_at,
                'updated_at': startup.updated_at,
                'member_slots_allocated': startup.member_slots_allocated,
                'direct_members': []
            }
            
            print("\nTrying validation without direct_members...")
            try:
                StartupSchema.model_validate(startup_dict)
                print("✅ Basic startup validation successful - issue is with direct_members")
                
                # Test each direct member individually
                for i, member in enumerate(startup.direct_members):
                    try:
                        from app.schemas.common import UserSimpleInfo
                        UserSimpleInfo.model_validate(member)
                        print(f"✅ Direct member {i+1} validation successful")
                    except Exception as member_e:
                        print(f"❌ Direct member {i+1} validation failed: {member_e}")
                        print(f"  Member data: {vars(member)}")
                        
            except Exception as basic_e:
                print(f"❌ Basic startup validation also failed: {basic_e}")

if __name__ == "__main__":
    asyncio.run(debug_startup()) 