export interface MobileApp {
  name: string
  ios?: string
  android?: string
}

export interface ServiceGuide {
  whatItDoes: string
  steps: string[]
  mobileApp?: MobileApp
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
  status?: 'online' | 'offline' | 'unknown'
  guide?: ServiceGuide
}

export type ServiceCategory = 'media' | 'books' | 'photos' | 'files' | 'smart-home'

export interface ServiceStatus {
  id: string
  status: 'online' | 'offline' | 'unknown'
  lastChecked: string
}
