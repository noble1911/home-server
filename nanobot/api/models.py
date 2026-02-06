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
