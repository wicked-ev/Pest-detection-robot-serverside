import { useEffect, useState } from 'react'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'

const TABS = [
  { id: 'live', label: 'Live' },
  { id: 'history', label: 'History' },
]

export function TopBar() {
  const { view, setView } = useRobotsContext()
  const [serverUp, setServerUp] = useState(null)

  useEffect(() => {
    const checkHealth = async () => {
      try {
        await APIClient.getHealth()
        setServerUp(true)
      } catch {
        setServerUp(false)
      }
    }
    void checkHealth()
    const interval = setInterval(checkHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="h-14 shrink-0 border-b border-border bg-surface flex items-center gap-6 px-4 md:px-6">
      <h1 className="text-lg font-semibold whitespace-nowrap">Pest Monitor</h1>

      <nav className="flex gap-1" aria-label="Pages">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setView(tab.id)}
            aria-current={view === tab.id ? 'page' : undefined}
            className={`px-3 py-1.5 rounded-button text-sm font-medium transition ${
              view === tab.id ? 'bg-border text-text-primary' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div
        className="ml-auto flex items-center gap-2 text-sm"
        role="status"
        title={serverUp === false ? 'Server offline' : 'Server connected'}
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            serverUp === null ? 'bg-text-secondary' : serverUp ? 'bg-accent' : 'bg-danger'
          }`}
        />
        {/* On narrow screens only the dot is shown; the text is in the tooltip. */}
        <span className={`hidden sm:inline whitespace-nowrap ${serverUp === false ? 'text-danger' : 'text-text-secondary'}`}>
          {serverUp === false ? 'Server offline' : 'Server connected'}
        </span>
      </div>
    </header>
  )
}

export default TopBar
