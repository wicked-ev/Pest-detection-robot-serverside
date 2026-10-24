import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Square } from 'lucide-react'
import APIClient from '../../api/client'
import Panel from '../common/Panel'

// Hold-to-drive: while a button or key is held, "move" is repeated every REPEAT_MS.
// The robot stops by itself if repeats stop arriving (about 1 s), so a closed tab or
// lost connection can never leave it driving.
const REPEAT_MS = 250

const KEYS = {
  ArrowUp: 'forward', w: 'forward', W: 'forward',
  ArrowDown: 'backward', s: 'backward', S: 'backward',
  ArrowLeft: 'left', a: 'left', A: 'left',
  ArrowRight: 'right', d: 'right', D: 'right',
}

function isTyping(target) {
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName) || target?.isContentEditable
}

export function DrivePanel({ robotId, isOnline, live }) {
  const [speed, setSpeed] = useState(60)
  const [active, setActive] = useState(null)
  const [error, setError] = useState(null)
  const activeRef = useRef(null)
  const speedRef = useRef(speed)
  const timerRef = useRef(null)

  const hasMotors = live?.motors !== false
  const canDrive = isOnline && hasMotors && !live?.spraying
  speedRef.current = speed

  const send = useCallback(
    (direction) =>
      APIClient.sendCommand(robotId, 'move', { direction, speed: speedRef.current })
        .then(() => setError(null))
        .catch((err) => setError(err.message)),
    [robotId],
  )

  const release = useCallback(() => {
    if (!activeRef.current) return
    activeRef.current = null
    setActive(null)
    clearInterval(timerRef.current)
    send('stop')
  }, [send])

  const press = useCallback(
    (direction) => {
      if (!canDrive || activeRef.current === direction) return
      clearInterval(timerRef.current)
      activeRef.current = direction
      setActive(direction)
      send(direction)
      timerRef.current = setInterval(() => send(direction), REPEAT_MS)
    },
    [canDrive, send],
  )

  // Keyboard: arrows / WASD to drive, Space to stop.
  useEffect(() => {
    const onKeyDown = (event) => {
      if (isTyping(event.target)) return
      if (event.key === ' ') {
        event.preventDefault()
        release()
        send('stop')
        return
      }
      const direction = KEYS[event.key]
      if (!direction) return
      event.preventDefault() // arrows would otherwise scroll the page
      if (!event.repeat) press(direction)
    }
    const onKeyUp = (event) => {
      if (KEYS[event.key] && KEYS[event.key] === activeRef.current) release()
    }
    const onHidden = () => release()
    const onVisibility = () => document.visibilityState === 'hidden' && release()
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onHidden)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onHidden)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [press, release, send])

  // Stop when leaving the page or switching robots.
  useEffect(() => release, [robotId, release])
  // Stop if driving becomes impossible (robot offline, spraying).
  useEffect(() => {
    if (!canDrive) release()
  }, [canDrive, release])

  const button = (direction, Icon, label) => (
    <button
      aria-label={label}
      title={label}
      disabled={!canDrive}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId)
        press(direction)
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onContextMenu={(event) => event.preventDefault()}
      className={`h-12 flex items-center justify-center rounded-button border transition select-none touch-none disabled:opacity-40 disabled:cursor-not-allowed ${
        active === direction ? 'bg-accent text-background border-accent' : 'bg-background border-border hover:border-text-secondary'
      }`}
    >
      <Icon size={20} />
    </button>
  )

  const note = !isOnline
    ? 'Robot offline'
    : !hasMotors
      ? 'Motors not connected on the robot'
      : live?.spraying
        ? 'Paused while spraying'
        : 'Hold a button, or arrows / WASD. Space stops.'

  return (
    <Panel title="Drive">
      <div className="grid grid-cols-3 gap-2 max-w-[13rem] mx-auto">
        <span />
        {button('forward', ArrowUp, 'Forward')}
        <span />
        {button('left', ArrowLeft, 'Turn left')}
        <button
          aria-label="Stop"
          title="Stop"
          disabled={!isOnline}
          onClick={() => {
            release()
            send('stop')
          }}
          className="h-12 flex items-center justify-center rounded-button border border-danger text-danger hover:bg-danger hover:text-background transition disabled:opacity-40"
        >
          <Square size={18} />
        </button>
        {button('right', ArrowRight, 'Turn right')}
        <span />
        {button('backward', ArrowDown, 'Backward')}
        <span />
      </div>

      <label className="mt-4 flex items-center gap-3 text-sm">
        <span className="text-text-secondary w-12">Speed</span>
        <input
          type="range"
          min="20"
          max="100"
          step="10"
          value={speed}
          onChange={(event) => setSpeed(Number(event.target.value))}
          className="flex-1 accent-accent"
        />
        <span className="w-10 text-right tabular-nums">{speed}%</span>
      </label>

      <p className="mt-2 text-xs text-text-secondary">{note}</p>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </Panel>
  )
}

export default DrivePanel
