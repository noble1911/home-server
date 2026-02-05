import StatusCard from '../components/dashboard/StatusCard'

export default function Dashboard() {
  // Mock data - will be replaced with API calls
  const connectionStatuses = [
    { id: 'livekit', name: 'LiveKit', status: 'online' as const },
    { id: 'api', name: 'Butler API', status: 'online' as const },
    { id: 'tailscale', name: 'Tailscale', status: 'online' as const },
  ]

  const systemStats = {
    cpu: 12,
    memory: 8.2,
    uptime: '14d 3h',
  }

  const storageStats = {
    media: '2.1 TB',
    photos: '450 GB',
    free: '3.5 TB',
  }

  const recentActivity = [
    { id: '1', user: 'Ron', action: 'asked about weather', time: '2m ago' },
    { id: '2', user: 'Partner', action: 'controlled lights', time: '15m ago' },
    { id: '3', user: 'Ron', action: 'played music', time: '1h ago' },
  ]

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
        <p className="text-sm text-butler-400">Server status and monitoring</p>
      </div>

      {/* Connection Status */}
      <section>
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
          Connections
        </h2>
        <div className="flex flex-wrap gap-2">
          {connectionStatuses.map(conn => (
            <StatusCard
              key={conn.id}
              name={conn.name}
              status={conn.status}
            />
          ))}
        </div>
      </section>

      {/* System & Storage */}
      <div className="grid grid-cols-2 gap-4">
        <section className="card p-4">
          <h3 className="text-sm font-medium text-butler-400 mb-3">System</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-butler-300">CPU</span>
              <span className="text-butler-100">{systemStats.cpu}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-butler-300">Memory</span>
              <span className="text-butler-100">{systemStats.memory} GB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-butler-300">Uptime</span>
              <span className="text-butler-100">{systemStats.uptime}</span>
            </div>
          </div>
        </section>

        <section className="card p-4">
          <h3 className="text-sm font-medium text-butler-400 mb-3">Storage</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-butler-300">Media</span>
              <span className="text-butler-100">{storageStats.media}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-butler-300">Photos</span>
              <span className="text-butler-100">{storageStats.photos}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-butler-300">Free</span>
              <span className="text-green-400">{storageStats.free}</span>
            </div>
          </div>
        </section>
      </div>

      {/* Recent Activity */}
      <section>
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
          Recent Activity
        </h2>
        <div className="card divide-y divide-butler-700">
          {recentActivity.map(activity => (
            <div key={activity.id} className="p-3 flex justify-between items-center">
              <div>
                <span className="text-butler-100 font-medium">{activity.user}</span>
                <span className="text-butler-400"> {activity.action}</span>
              </div>
              <span className="text-xs text-butler-500">{activity.time}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Quick Actions */}
      <section>
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-secondary text-sm">Test TTS</button>
          <button className="btn btn-secondary text-sm">Clear Cache</button>
          <button className="btn btn-secondary text-sm">View Logs</button>
        </div>
      </section>
    </div>
  )
}
