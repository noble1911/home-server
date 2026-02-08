"""Pydantic request/response models matching PWA TypeScript types.

Field names use camelCase to match the PWA's TypeScript interfaces directly.
See: app/src/types/user.ts, app/src/types/conversation.ts
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


# --- Auth ---


class RedeemInviteRequest(BaseModel):
    code: str


class AuthTokens(BaseModel):
    accessToken: str
    refreshToken: str
    expiresAt: int  # epoch milliseconds


class RedeemInviteResponse(BaseModel):
    tokens: AuthTokens
    hasCompletedOnboarding: bool
    role: str = "user"


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class LiveKitTokenRequest(BaseModel):
    user_id: str


class LiveKitTokenResponse(BaseModel):
    livekit_token: str
    room_name: str


# --- Admin: Invite Code Management ---


class CreateInviteCodeRequest(BaseModel):
    expiresInDays: int = 7


class InviteCodeInfo(BaseModel):
    code: str
    createdBy: str | None
    usedBy: str | None
    expiresAt: str
    createdAt: str
    usedAt: str | None
    isExpired: bool
    isUsed: bool


class InviteCodeListResponse(BaseModel):
    codes: list[InviteCodeInfo]


class CreateInviteCodeResponse(BaseModel):
    code: str
    expiresAt: str


# --- Admin: User & Permission Management ---


class AdminUserInfo(BaseModel):
    id: str
    name: str
    role: str
    permissions: list[str]


class AdminUserListResponse(BaseModel):
    users: list[AdminUserInfo]


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


# --- User (matches app/src/types/user.ts) ---


class SoulConfig(BaseModel):
    personality: str = "balanced"
    verbosity: str = "moderate"
    humor: str = "subtle"
    customInstructions: str | None = None
    voice: str | None = None


class NotificationPrefs(BaseModel):
    enabled: bool = True
    categories: list[str] = Field(
        default_factory=lambda: [
            "download", "reminder", "weather",
            "smart_home", "calendar", "general",
        ]
    )
    quietHoursStart: str | None = None  # "HH:MM" format
    quietHoursEnd: str | None = None    # "HH:MM" format


class UserFact(BaseModel):
    id: str
    content: str
    category: str
    createdAt: str


class UserProfile(BaseModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    butlerName: str = "Butler"
    role: str = "user"
    permissions: list[str] = Field(default_factory=lambda: ["media", "home"])
    createdAt: str
    soul: SoulConfig = Field(default_factory=SoulConfig)
    facts: list[UserFact] = Field(default_factory=list)
    notificationPrefs: NotificationPrefs = Field(default_factory=NotificationPrefs)


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class UpdateNotificationsRequest(BaseModel):
    phone: str | None = Field(None, pattern=r'^$|^\+[1-9]\d{1,14}$')
    notificationPrefs: NotificationPrefs | None = None


class UpdateButlerNameRequest(BaseModel):
    butlerName: str


class OnboardingRequest(BaseModel):
    name: str
    butlerName: str
    soul: SoulConfig
    serviceUsername: str | None = Field(None, pattern=r'^[a-z0-9_]{3,20}$')
    servicePassword: str | None = Field(None, min_length=6)

    @model_validator(mode='after')
    def check_credentials_pair(self):
        if bool(self.serviceUsername) != bool(self.servicePassword):
            raise ValueError('serviceUsername and servicePassword must both be provided or both omitted')
        return self


class AddFactRequest(BaseModel):
    content: str
    category: str


# --- Service Credentials (auto-provisioned app accounts) ---


class ServiceCredential(BaseModel):
    service: str
    username: str
    password: str | None = None
    status: str  # "active", "failed", "decrypt_error"
    errorMessage: str | None = None
    createdAt: str


class ServiceCredentialsResponse(BaseModel):
    credentials: list[ServiceCredential]


# --- Chat ---

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# ~5 MB raw → ~6.8 M base64 chars; round up to 7 M for headroom.
MAX_IMAGE_BASE64_LEN = 7_000_000


class ImageAttachment(BaseModel):
    """Base64-encoded image for Claude vision. No data-URI prefix."""
    data: str
    mediaType: str

    @model_validator(mode="after")
    def validate_image(self):
        if self.mediaType not in ALLOWED_IMAGE_TYPES:
            raise ValueError(
                f"Unsupported image type '{self.mediaType}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}"
            )
        if len(self.data) > MAX_IMAGE_BASE64_LEN:
            raise ValueError("Image too large (max ~5 MB)")
        return self


class ChatRequest(BaseModel):
    message: str
    type: str = "text"
    image: ImageAttachment | None = None


class ChatResponse(BaseModel):
    response: str
    message_id: str


class HistoryMessage(BaseModel):
    id: str
    role: str
    content: str
    type: str  # 'voice' | 'text'
    timestamp: str  # ISO 8601


class ChatHistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    hasMore: bool


# --- Voice ---


class VoiceProcessRequest(BaseModel):
    transcript: str
    user_id: str
    session_id: str


class VoiceProcessResponse(BaseModel):
    response: str
    should_end_turn: bool


# --- OAuth ---


class OAuthConnection(BaseModel):
    provider: str
    connected: bool
    accountId: str | None = None
    connectedAt: str | None = None


class OAuthConnectionsResponse(BaseModel):
    connections: list[OAuthConnection]


class OAuthAuthorizeResponse(BaseModel):
    authorizeUrl: str


# --- Scheduled Tasks ---


class TaskAction(BaseModel):
    type: str  # "reminder" | "automation" | "check"
    message: str | None = None
    tool: str | None = None
    params: dict | None = None
    category: str | None = None
    notifyOn: str | None = None  # "warning" | "critical" | "always"


class CreateTaskRequest(BaseModel):
    name: str
    cronExpression: str | None = None
    action: TaskAction
    enabled: bool = True


class UpdateTaskRequest(BaseModel):
    name: str | None = None
    cronExpression: str | None = None
    action: TaskAction | None = None
    enabled: bool | None = None


class ScheduledTaskResponse(BaseModel):
    id: int
    userId: str
    name: str
    cronExpression: str | None
    action: TaskAction
    enabled: bool
    lastRun: str | None  # ISO8601
    nextRun: str | None  # ISO8601
    createdAt: str  # ISO8601


# --- Push Notifications ---


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushSubscriptionInfo(BaseModel):
    id: int
    endpoint: str
    createdAt: str


# --- Tool Usage (system observability) ---


class ToolUsageEntry(BaseModel):
    id: int
    userId: str | None
    toolName: str
    parameters: dict = Field(default_factory=dict)
    resultSummary: str | None
    error: str | None
    durationMs: int
    channel: str | None
    createdAt: str


class ToolUsageSummary(BaseModel):
    totalCalls24h: int
    errorCount24h: int
    avgDurationMs: int


class ToolUsageResponse(BaseModel):
    entries: list[ToolUsageEntry]
    summary: ToolUsageSummary


# --- Webhooks (Home Assistant) ---


class HAWebhookEvent(BaseModel):
    """Incoming Home Assistant webhook payload.

    HA automations typically send ``state_changed`` events with entity details,
    or ``automation_triggered`` events with the automation name.  Custom events
    use an arbitrary ``event_type``.
    """

    event_type: str  # "state_changed", "automation_triggered", custom
    entity_id: str | None = None
    old_state: str | None = None
    new_state: str | None = None
    attributes: dict = Field(default_factory=dict)


class HAWebhookResponse(BaseModel):
    status: str  # "accepted", "ignored"
    event_id: int | None = None
    notification_sent: bool = False
