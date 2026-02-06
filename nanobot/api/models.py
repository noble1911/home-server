"""Pydantic request/response models matching PWA TypeScript types.

Field names use camelCase to match the PWA's TypeScript interfaces directly.
See: app/src/types/user.ts, app/src/types/conversation.ts
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class UserFact(BaseModel):
    id: str
    content: str
    category: str
    createdAt: str


class UserProfile(BaseModel):
    id: str
    name: str
    email: str | None = None
    butlerName: str = "Butler"
    role: str = "user"
    permissions: list[str] = Field(default_factory=lambda: ["media", "home"])
    createdAt: str
    soul: SoulConfig = Field(default_factory=SoulConfig)
    facts: list[UserFact] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class UpdateButlerNameRequest(BaseModel):
    butlerName: str


class OnboardingRequest(BaseModel):
    name: str
    butlerName: str
    soul: SoulConfig


class AddFactRequest(BaseModel):
    content: str
    category: str


# --- Chat ---


class ChatRequest(BaseModel):
    message: str
    type: str = "text"


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
