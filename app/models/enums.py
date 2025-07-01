from __future__ import annotations
import enum
from enum import Enum


class ContactVisibility(str, enum.Enum):
    PRIVATE = "private"
    CONNECTIONS = "connections"
    PUBLIC = "public"


class UserRole(str, Enum):
    SYS_ADMIN = "SYS_ADMIN"
    CORP_ADMIN = "CORP_ADMIN"
    CORP_EMPLOYEE = "CORP_EMPLOYEE"
    STARTUP_ADMIN = "STARTUP_ADMIN"
    STARTUP_MEMBER = "STARTUP_MEMBER"
    FREELANCER = "FREELANCER"


class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    WAITLISTED = "WAITLISTED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BANNED = "BANNED"


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    BLOCKED = "blocked"


class NotificationType(str, enum.Enum):
    # General
    CONNECTION_REQUEST = "connection_request"
    CONNECTION_ACCEPTED = "connection_accepted"
    NEW_MESSAGE = "new_message"
    new_message = "new_message"
    ADDED_TO_SPACE = "added_to_space"
    REMOVED_FROM_SPACE = "removed_from_space"
    INVITATION_REQUEST = "invitation_request"

    # Member Requests (for Corp Admin via Startup Admin action)
    # The following are deprecated in favor of an invite-only system
    # MEMBER_REQUEST = "member_request"
    # MEMBER_REQUEST_APPROVED = "member_request_approved"
    # MEMBER_REQUEST_DENIED = "member_request_denied"
    # MEMBER_REQUEST_COMPLETED = "member_request_completed"

    # Startup Admin inviting members directly
    INVITATION_RECEIVED = "invitation_received"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_REVOKED = "invitation_revoked"

    # Agent related (placeholder)
    agent_invitation = "agent_invitation"

    # Workstation Notifications
    WORKSTATION_ASSIGNED = "WORKSTATION_ASSIGNED"
    WORKSTATION_UNASSIGNED = "WORKSTATION_UNASSIGNED"
    WORKSTATION_STATUS_UPDATED = "WORKSTATION_STATUS_UPDATED"
    WORKSTATION_DETAILS_CHANGED = "WORKSTATION_DETAILS_CHANGED"
    SLOT_ALLOCATION_UPDATED = "SLOT_ALLOCATION_UPDATED"

    # Admin actions / System Notifications
    admin_user_suspended = "admin_user_suspended"
    admin_user_reactivated = "admin_user_reactivated"
    admin_space_created = "admin_space_created"
    admin_corp_onboarded = "admin_corp_onboarded"

    INTEREST_EXPRESSED = "interest_expressed"


class WorkstationStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    MAINTENANCE = "MAINTENANCE"


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    BLOCKED = "blocked"
    REVOKED = "revoked"


class ChatMessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"


class TeamSize(str, Enum):
    ONE = "1"
    TWO_TO_FIVE = "2-5"
    EXTRA_SMALL = "1-10"
    SMALL = "11-50"
    MEDIUM = "51-200"
    LARGE = "201-1000"
    EXTRA_LARGE = "1001+"


class StartupStage(str, enum.Enum):
    """Enum for startup stages."""
    IDEA = "Idea"
    PRE_SEED = "Pre-Seed"
    SEED = "Seed"
    SERIES_A = "Series A"
    SERIES_B = "Series B"
    SERIES_C = "Series C"
    GROWTH = "Growth"


class CommunityBadge(str, Enum):
    NEW_MEMBER = "NEW_MEMBER"
    OG_MEMBER = "OG_MEMBER"
    CONNECTOR = "CONNECTOR"
    MENTOR = "MENTOR"
