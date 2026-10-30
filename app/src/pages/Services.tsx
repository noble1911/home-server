import { useState, useEffect, useCallback } from 'react'
import ServiceCard from '../components/services/ServiceCard'
import ServiceDetail from '../components/services/ServiceDetail'
import type { Service } from '../types/services'
import type { ServiceCategory } from '../types/services'
import type { ServiceCredential } from '../types/user'
import { getSystemHealth, api, type ServiceStatus } from '../services/api'
import { servicesFor, categoryLabels, applyHealthStatus } from '../config/services'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'

const REFRESH_INTERVAL = 60_000

export default function Services() {
  const isAdmin = useAuthStore(s => s.role === 'admin')
  const permissions = useUserStore(s => s.profile?.permissions) ?? []
  const [healthData, setHealthData] = useState<ServiceStatus[] | null>(null)
  const [lanHost, setLanHost] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [selectedService, setSelectedService] = useState<Service | null>(null)
  const [credentials, setCredentials] = useState<ServiceCredential[]>([])

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getSystemHealth()
      setHealthData(data.services)
      setLanHost(data.lanHost || null)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch service status')
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const id = setInterval(fetchStatus, REFRESH_INTERVAL)
    return () => clearInterval(id)
  }, [fetchStatus])

  useEffect(() => {
    api.get<{ credentials: ServiceCredential[] }>('/user/service-credentials')
      .then(data => setCredentials(data.credentials))
      .catch(() => setCredentials([]))
  }, [])

  const available = servicesFor(isAdmin, permissions, lanHost)
  const services = healthData
    ? applyHealthStatus(available, healthData)
    : available

  const categories = [...new Set(services.map(s => s.category))] as ServiceCategory[]

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Services</h1>
        <p className="text-sm text-butler-400">Tap a service to learn how to connect, or use the link icon to open it directly</p>
      </div>

      {error && (
        <div className="text-sm text-red-400/70 bg-red-500/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {categories.map(category => (
        <div key={category}>
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
            {categoryLabels[category]}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {services
              .filter(s => s.category === category)
              .map(service => (
                <ServiceCard
                  key={service.id}
                  service={service}
                  onSelect={setSelectedService}
                />
              ))}
          </div>
        </div>
      ))}

      {selectedService && (
        <ServiceDetail
          service={selectedService}
          credentials={credentials}
          onClose={() => setSelectedService(null)}
        />
      )}
    </div>
  )
}
