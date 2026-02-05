export interface Service {
  id: string
  name: string
  description: string
  icon: string
  url: string
  mobileUrl?: string // Deep link for mobile apps
  category: ServiceCategory
  status?: 'online' | 'offline' | 'unknown'
}

export type ServiceCategory = 'media' | 'books' | 'photos' | 'files' | 'smart-home'

export interface ServiceStatus {
  id: string
  status: 'online' | 'offline' | 'unknown'
  lastChecked: string
}
