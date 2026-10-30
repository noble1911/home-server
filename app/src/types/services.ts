import type { ToolPermission } from './user'

export interface MobileApp {
  name: string
  ios?: string
  android?: string
}

export interface ServiceGuide {
  whatItDoes: string
  steps: string[]
  mobileApp?: MobileApp
  recommendedApps?: MobileApp[]
  tips?: string[]
}

export interface Service {
  id: string
  name: string
  description: string
  icon: string
  url: string
  mobileUrl?: string // Deep link for mobile apps
  category: ServiceCategory
  /** Who sees it: everyone, holders of a permission, or admins only */
  access: 'everyone' | 'admin' | ToolPermission
  /** Home-network port (admin tools, linked as http://<lanHost>:<port>) */
  port?: number
  status?: 'online' | 'offline' | 'unknown'
  guide?: ServiceGuide
}

export type ServiceCategory = 'media' | 'books' | 'photos' | 'files' | 'smart-home' | 'admin'

export interface ServiceStatus {
  id: string
  status: 'online' | 'offline' | 'unknown'
  lastChecked: string
}
