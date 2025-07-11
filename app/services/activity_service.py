from sqlalchemy.orm import Session
from typing import List, Tuple
from app.models import Booking, User, Space, Company, Invitation
from app.schemas.activity import Activity
from datetime import datetime, timedelta

class ActivityService:
    def __init__(self, db: Session):
        self.db = db

    def get_recent_activity(self, company_id: int, limit: int = 10) -> List[Activity]:
        """
        Fetches a combined list of recent activities for a company.
        This includes new bookings, new members, and new spaces.
        """
        activities = []
        now = datetime.utcnow()
        time_window = now - timedelta(days=30) # Look back 30 days

        # 1. New Bookings
        new_bookings = (
            self.db.query(Booking)
            .join(User, Booking.user_id == User.id)
            .filter(User.company_id == company_id, Booking.created_at >= time_window)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .all()
        )
        for booking in new_bookings:
            activities.append(Activity(
                id=f"booking-{booking.id}",
                type="New Booking",
                timestamp=booking.created_at,
                description=f"{booking.user.profile.first_name} booked workstation {booking.workstation.name}.",
                user_avatar_url=booking.user.profile.profile_image_url,
                link=f"/company/{company_id}/bookings"
            ))

        # 2. New Members (from accepted invitations)
        new_members = (
            self.db.query(User)
            .filter(User.company_id == company_id, User.created_at >= time_window) # Assuming creation time is close to joining
            .order_by(User.created_at.desc())
            .limit(limit)
            .all()
        )
        for member in new_members:
             if member.profile:
                activities.append(Activity(
                    id=f"user-{member.id}",
                    type="New Member",
                    timestamp=member.created_at,
                    description=f"{member.profile.first_name} {member.profile.last_name} joined the company.",
                    user_avatar_url=member.profile.profile_image_url,
                    link=f"/company/{company_id}/members"
                ))

        # 3. New Spaces
        new_spaces = (
            self.db.query(Space)
            .filter(Space.company_id == company_id, Space.created_at >= time_window)
            .order_by(Space.created_at.desc())
            .limit(limit)
            .all()
        )
        for space in new_spaces:
            activities.append(Activity(
                id=f"space-{space.id}",
                type="New Space",
                timestamp=space.created_at,
                description=f"A new space '{space.name}' was added.",
                user_avatar_url=None, # No specific user for this
                link=f"/company/{company_id}/space-profile"
            ))

        # Sort all activities by timestamp descending and return the top `limit`
        activities.sort(key=lambda x: x.timestamp, reverse=True)
        return activities[:limit]

activity_service = ActivityService
