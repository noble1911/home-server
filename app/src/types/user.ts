export type UserRole = 'admin' | 'user'

export interface User {
  id: string
  name: string
  email?: string
  butlerName: string
  role: UserRole
  createdAt: string
}

export interface SoulConfig {
  personality: 'casual' | 'formal' | 'balanced'
  verbosity: 'concise' | 'moderate' | 'detailed'
  humor: 'none' | 'subtle' | 'playful'
  customInstructions?: string
}

export interface UserProfile extends User {
  soul: SoulConfig
  facts: UserFact[]
}

export interface UserFact {
  id: string
  content: string
  category: 'preference' | 'personal' | 'routine' | 'other'
  createdAt: string
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

export interface InviteCode {
  code: string
  createdBy: string | null
  usedBy: string | null
  expiresAt: string
  createdAt: string
  usedAt: string | null
  isExpired: boolean
  isUsed: boolean
}

export interface OAuthConnection {
  provider: string
  connected: boolean
  accountId?: string
  connectedAt?: string
}
