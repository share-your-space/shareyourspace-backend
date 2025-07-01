# Leave this file empty 
from .user import (
    User, UserCreate, UserUpdate, UserDetail, UserInDB, 
    UserCreateAcceptInvitation, UserStatusUpdate
)
from .verification_token import VerificationToken, VerificationTokenCreate # noqa
# Import specific password reset schemas needed
from .password_reset_token import PasswordResetTokenCreate, RequestPasswordResetRequest, ResetPasswordRequest # noqa
from .token import Token, TokenPayload, OnboardingToken, TokenWithUser # noqa
from .user_profile import UserProfile, UserProfileUpdate # noqa
from . import organization # noqa: Import the organization schemas
from . import chat # noqa: Import the chat schemas
from . import onboarding # noqa: Import the onboarding schemas
from .message import Message # noqa
from . import auth # noqa: Import the auth schemas
from . import workstation # noqa: Import the workstation schemas
from . import interest # noqa: Import the interest schemas
from .connection import Connection, ConnectionCreate, ConnectionStatusCheck # noqa
from .chat import ( # noqa
    ConversationSchema as Conversation, 
    ConversationCreate, 
    ChatMessageSchema as ChatMessage, 
    ChatMessageCreate, 
    ConversationForList,
    MessageReactionResponse
)
from .organization import (
    Company, Startup, BasicCompany, BasicStartup, CompanyUpdate, 
    StartupUpdate, OrganizationBase, InvitationRequest
)
from .space import (
    Space, BasicSpace, UserWorkstationInfo, SpaceUsersListResponse,
    SpaceWorkstationListResponse, WorkstationDetail, WorkstationTenantInfo,
    BrowseableSpace, BrowseableSpaceListResponse, AddUserToSpaceRequest,
    WorkstationAssignmentRequest, WorkstationUnassignRequest,
    WorkstationStatusUpdateRequest, WorkstationCreate, SpaceCreationResponse,
    SpaceCreationUserResponse
)
from .admin import ( # noqa
    PendingCorporateUser, 
    Space as SpaceResponseSchema, 
    UserActivateCorporate, 
    UserAssignSpace, 
    UserAdminView, 
    PaginatedUserAdminView,
    SpaceUpdate,
    SpaceAssignAdmin,
    UserStatusUpdate,
    AISearchRequest,
    StartupUpdateAdmin
)
from .registration import FreelancerCreate, StartupAdminCreate, CorporateAdminCreate

# Create a namespace for rebuilding models with forward references
namespace = {
    'User': User,
    'UserDetail': UserDetail,
    'Company': organization.Company,
    'Startup': organization.Startup,
    'BasicCompany': organization.BasicCompany,
    'BasicStartup': organization.BasicStartup,
    'BasicSpace': space.BasicSpace,
    'UserWorkstationInfo': space.UserWorkstationInfo,
    'UserProfile': user_profile.UserProfile,
    'organization': organization,
    'space': space,
    'user_profile': user_profile,
    'user': user
}

# After all schemas are imported, rebuild models with the correct namespace
User.model_rebuild()
UserDetail.model_rebuild()
organization.Company.model_rebuild()
organization.Startup.model_rebuild()
chat.ConversationSchema.model_rebuild()
chat.ChatMessageSchema.model_rebuild()
chat.ConversationForList.model_rebuild()
SpaceCreationResponse.model_rebuild()
SpaceCreationUserResponse.model_rebuild()

# Add other model_rebuild calls here if new forward refs are introduced