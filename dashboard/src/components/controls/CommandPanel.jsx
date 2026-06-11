import { useState } from 'react'
import { Zap, RotateCcw, Power, Wifi } from 'lucide-react'
import APIClient from '../../api/client'
import WifiModal from './WifiModal'
import { useRobotsContext } from '../../context/RobotsContext'

export function CommandPanel({ robotId, robotStatus }) {
  const [isLoading, setIsLoading] = useState(false)
  const [showWifiModal, setShowWifiModal] = useState(false)
  const { refreshRobots } = useRobotsContext()
  const isOnline = robotStatus === 'online'
  const isProvisioning = robotStatus === 'provisioning'

  const sendCommand = async (command) => {
    try {
      setIsLoading(true)
      await APIClient.sendCommand(robotId, command)
      await refreshRobots?.()
    } catch (err) {
      console.error(`Failed to send command '${command}':`, err)
    } finally {
      setIsLoading(false)
    }
  }

  const commands = [
    { label: 'Start Stream', command: 'start_stream', icon: Zap },
    { label: 'Stop Stream', command: 'stop_stream', icon: Power },
    { label: 'Reboot', command: 'reboot', icon: RotateCcw },
    { label: 'Stop', command: 'stop', icon: Power },
  ]

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {commands.map(({ label, command, icon: Icon }) => (
          <button
            key={command}
            onClick={() => sendCommand(command)}
            disabled={!isOnline || isLoading}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-surface border border-border text-text-primary font-medium rounded-button hover:bg-[#1a1a1a] disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            <Icon size={16} />
            <span className="text-sm">{label}</span>
          </button>
        ))}
      </div>

      {isProvisioning && (
        <>
          <button
            onClick={() => setShowWifiModal(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent text-background font-medium rounded-button hover:opacity-90 transition"
          >
            <Wifi size={18} />
            <span>Send WiFi Credentials</span>
          </button>
          {showWifiModal && (
            <WifiModal
              robotId={robotId}
              onClose={() => setShowWifiModal(false)}
            />
          )}
        </>
      )}
    </div>
  )
}

export default CommandPanel
