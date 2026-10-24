import { useEffect, useState } from 'react'
import { Droplets } from 'lucide-react'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'
import Panel from '../common/Panel'
import { formatRelative } from '../../utils/time'

export function SprayPanel({ robotId, isOnline, live, lastSpray }) {
  const { refreshRobots } = useRobotsContext()
  const [pendingAuto, setPendingAuto] = useState(null) // shown until the robot confirms
  const [latest, setLatest] = useState(null)
  const [error, setError] = useState(null)

  const hasPump = live?.motors !== false
  const autoOn = pendingAuto ?? Boolean(live?.auto_spray)
  const spraying = Boolean(live?.spraying)

  // The robot reports its real setting in its live status; drop our guess once it does.
  useEffect(() => {
    if (pendingAuto !== null && live?.auto_spray === pendingAuto) setPendingAuto(null)
  }, [live?.auto_spray, pendingAuto])

  // Last spray: from history on load, then from live events while watching.
  useEffect(() => {
    let cancelled = false
    APIClient.getSprays({ robot_id: robotId, limit: 1 })
      .then((rows) => !cancelled && setLatest(rows[0] || null))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [robotId])
  useEffect(() => {
    if (lastSpray) setLatest(lastSpray)
  }, [lastSpray])

  const refreshSoon = () => setTimeout(() => refreshRobots?.(), 400)

  const toggleAuto = async () => {
    const enabled = !autoOn
    setPendingAuto(enabled)
    try {
      setError(null)
      await APIClient.sendCommand(robotId, 'set_auto_spray', { enabled })
      refreshSoon()
    } catch (err) {
      setPendingAuto(null)
      setError(err.message)
    }
  }

  const sprayNow = async () => {
    try {
      setError(null)
      await APIClient.sendCommand(robotId, 'spray', { duration: 1 })
      refreshSoon()
    } catch (err) {
      setError(err.message)
    }
  }

  const disabled = !isOnline || !hasPump

  return (
    <Panel title="Sprayer">
      <label className={`flex items-center justify-between gap-3 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
        <span className="text-sm">
          Auto-spray on detection
          <span className="block text-xs text-text-secondary">Stops, sprays a short burst, then waits before the next</span>
        </span>
        <button
          role="switch"
          aria-checked={autoOn}
          disabled={disabled}
          onClick={toggleAuto}
          className={`relative h-6 w-11 shrink-0 rounded-full transition ${autoOn ? 'bg-accent' : 'bg-border'}`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-text-primary transition-all ${autoOn ? 'left-[1.375rem]' : 'left-0.5'}`}
          />
        </button>
      </label>

      <button
        onClick={sprayNow}
        disabled={disabled || spraying}
        className="mt-3 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-button border border-border hover:border-text-secondary disabled:opacity-40 disabled:cursor-not-allowed transition"
      >
        <Droplets size={16} />
        <span className="text-sm">{spraying ? 'Spraying…' : 'Spray now (1 s)'}</span>
      </button>

      <p className="mt-2 text-xs text-text-secondary">
        {!isOnline
          ? 'Robot offline'
          : !hasPump
            ? 'Pump not connected on the robot'
            : latest
              ? `Last spray: ${latest.label || 'manual'} · ${formatRelative(latest.time)} (${latest.trigger})`
              : 'No sprays yet'}
      </p>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </Panel>
  )
}

export default SprayPanel
