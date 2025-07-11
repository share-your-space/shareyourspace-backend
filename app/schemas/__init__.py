# flake8: noqa
from .user import (
    User, UserCreate, UserUpdate, UserDetail, UserInDB,
    UserCreateAcceptInvitation, UserAuth, UserRegister,
    PasswordResetRequest, PasswordReset, UserCreateCorporateAdmin,
    UserCreateStartupAdmin, UserCreateFreelancer, BasicUser, BasicUserInfo,
    UserUpdateInternal, SpaceUsersListResponse, SpaceUserDetail, UserStatusUpdate
)
from .token import Token, TokenPayload, TokenWithUser, OnboardingToken
from .common import UserSimple
from .space import (
    Space, SpaceTenantResponse, SpaceProfile,
    SpaceProfileUpdate, SpaceImage, AddUserToSpaceRequest, BasicSpace,
    BrowseableSpace, BrowseableSpaceListResponse, SpaceCreationResponse,
    UserWorkstationInfo, ManagedSpaceDetail, SpaceUpdate,
    SpaceConnectionStatsResponse, StartupTenantInfo, FreelancerTenantInfo,
    TenantInfo, SpaceCreationUserResponse, WorkstationTenantInfo,
    WorkstationStatus, WorkstationAssignmentRequest, WorkstationAssignmentResponse,
    WorkstationDetail, SpaceWorkstationListResponse as SpaceWSListResp,
    WorkstationUnassignRequest, WorkstationCreate as SpaceWorkstationCreate,
    WorkstationUpdate as SpaceWorkstationUpdate, WorkstationStatusUpdateRequest
)
from .organization import (
    Company, CompanyCreate, CompanyUpdate, Startup, StartupCreate,
    StartupUpdate, OrganizationBase, BasicCompany, BasicStartup,
    MemberRequestCreate, MemberRequestResponse, OrganizationSearchResult,
    InvitationRequest, UserSimpleInfo
)
from .admin import (
    UserAssignSpace, SpaceCreate,
    SimpleSpaceCreate, Space as AdminSpace, UserAdminView, PaginatedUserAdminView,
    SpaceUpdate as AdminSpaceUpdate, SpaceAssignAdmin, PlatformStats,
    AISearchRequest, PendingCorporateUser, UserActivateCorporate,
    StartupUpdateAdmin, MemberSlotUpdate, WaitlistedUser, WaitlistedStartup
)
from .analytics import AnalyticsOverview
from .booking import Booking
from .billing import SubscriptionUpdate, BillingInfo, Invoice

# Resolve forward references
SpaceProfile.model_rebuild()
OrganizationBase.model_rebuild()
Company.model_rebuild()
Startup.model_rebuild()
User.model_rebuild()
from .invitation import (
    Invitation, InvitationCreate, InvitationUpdate, InvitationWithDetails,
    AdminInviteCreate, InvitationListResponse, InvitationDecline, EmployeeInviteCreate,
    CorpAdminDirectInviteCreate
)
from .chat import (
    ConversationSchema, ConversationCreate, ChatMessageSchema,
    ChatMessageCreate, ConversationForList, MessageReactionResponse
)
from .connection import Connection, ConnectionCreate, ConnectionStatusCheck
from .interest import Interest, InterestCreate, InterestUpdate
from .matching import MatchResult
from .member_request import (
    RequestingStartupInfo, RequestedUserInfo, MemberRequestStatus,
    MemberRequestDetail, MemberRequestListResponse, MemberRequestActionResponse,
    StartupMemberRequestCreate, MemberRequestApprovalDetails
)
from .message import Message
from .notification import Notification, NotificationCreate, NotificationUpdate
from .onboarding import OnboardingData
from .password_reset_token import (
    PasswordResetTokenBase, PasswordResetTokenCreate, PasswordResetTokenRead,
    RequestPasswordResetRequest, ResetPasswordRequest
)
from .registration import (
    FreelancerCreate, StartupAdminCreate, CorporateAdminCreate
)
from .uploads import ChatAttachmentResponse
from .user_profile import UserProfile, UserProfileUpdate
from .verification_token import VerificationToken, VerificationTokenCreate
from .workstation import (
    Workstation, WorkstationCreate, WorkstationUpdate, WorkstationAssignment,
    SpaceWorkstationDetail, SpaceWorkstationListResponse
)
from .activity import Activity, ActivityCreate, ActivityUpdate, ActivityDetail

# After all models are imported, rebuild the forward references
User.model_rebuild()
UserDetail.model_rebuild()
Company.model_rebuild()
Startup.model_rebuild()
ConversationSchema.model_rebuild()
ChatMessageSchema.model_rebuild()
WaitlistedUser.model_rebuild()
WaitlistedStartup.model_rebuild()
SpaceCreationResponse.model_rebuild()
Invitation.model_rebuild()
InvitationListResponse.model_rebuild()
InvitationWithDetails.model_rebuild()
SpaceUserDetail.model_rebuild()