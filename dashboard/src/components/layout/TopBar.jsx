import { useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import APIClient from '../../api/client'

export function TopBar() {
  const [serverHealth, setServerHealth] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isOffline, setIsOffline] = useState(false)

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const health = await APIClient.getHealth()
        setServerHealth(health)
        setIsOffline(false)
        setLastUpdated(new Date().toLocaleTimeString())
      } catch (err) {
        setIsOffline(true)
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="h-16 border-b border-border bg-surface flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full ${isOffline ? 'bg-danger' : 'bg-accent'}`} />
        <h1 className="text-xl font-semibold">Pest Monitor</h1>
      </div>

      <div className="flex items-center gap-6 text-sm text-text-secondary">
        {isOffline && (
          <div className="flex items-center gap-2 text-danger">
            <AlertCircle size={16} />
            <span>Server Offline</span>
          </div>
        )}
        {!isOffline && lastUpdated && (
          <span>Last updated: {lastUpdated}</span>
        )}
      </div>
    </div>
  )
}

export default TopBar
