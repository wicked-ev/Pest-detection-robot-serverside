import { useState } from 'react'
import { Hand, RotateCcw, Power } from 'lucide-react'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'

// Stream start/stop lives in StreamView. "halt" only stops the motors;
// "reboot" restarts and "shutdown" stops the robot's program (not the Pi itself),
// so both ask for confirmation.
const COMMANDS = [
  { label: 'Stop Motors', command: 'halt', icon: Hand },
  {
    label: 'Reboot',
    command: 'reboot',
    icon: RotateCcw,
    confirm: 'Restart the robot software? It will be offline for a few seconds.',
  },
  {
    label: 'Shutdown',
    command: 'shutdown',
    icon: Power,
    danger: true,
    confirm: 'Stop the robot software? It stays stopped until it is started again on the robot.',
  },
]

export function CommandPanel({ robotId, robotStatus }) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const { refreshRobots } = useRobotsContext()
  const isOnline = robotStatus === 'online'

  const sendCommand = async ({ command, confirm }) => {
    if (confirm && !window.confirm(confirm)) return
    try {
      setIsLoading(true)
      setError(null)
      await APIClient.sendCommand(robotId, command)
      await refreshRobots?.()
    } catch (err) {
      setError(err.message)
      console.error(`Failed to send command '${command}':`, err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {COMMANDS.map((entry) => {
          const { label, command, icon: Icon, danger } = entry
          return (
            <button
              key={command}
              onClick={() => sendCommand(entry)}
              disabled={!isOnline || isLoading}
              className={`flex items-center justify-center gap-2 px-3 py-2 bg-surface border font-medium rounded-button hover:bg-[#1a1a1a] disabled:opacity-50 disabled:cursor-not-allowed transition ${
                danger ? 'border-danger text-danger' : 'border-border text-text-primary'
              }`}
            >
              <Icon size={16} />
              <span className="text-sm">{label}</span>
            </button>
          )
        })}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  )
}

export default CommandPanel
