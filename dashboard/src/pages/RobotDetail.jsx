import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import APIClient from '../api/client'
import { useRobotsContext } from '../context/RobotsContext'
import useRobotStream from '../hooks/useRobotStream'
import StreamView from '../components/stream/StreamView'
import CommandPanel from '../components/controls/CommandPanel'
import DrivePanel from '../components/controls/DrivePanel'
import SprayPanel from '../components/controls/SprayPanel'
import RecentSightings from '../components/history/RecentSightings'
import RobotStatusBadge from '../components/robots/RobotStatusBadge'
import Panel from '../components/common/Panel'
import { formatRelative } from '../utils/time'

export function RobotDetail({ robotId }) {
  const { robots, selectRobot, refreshRobots } = useRobotsContext()
  const robot = robots[robotId]
  const stream = useRobotStream(robotId)
  const [deleteError, setDeleteError] = useState(null)

  if (!robot) {
    return <div className="flex-1 flex items-center justify-center text-text-secondary">Robot not found</div>
  }

  const isOnline = robot.status === 'online'

  const handleDelete = async () => {
    if (!window.confirm(`Remove ${robot.name} from the list? Its detection history is kept.`)) return
    try {
      setDeleteError(null)
      await APIClient.deleteRobot(robotId)
      selectRobot(null)
      await refreshRobots?.()
    } catch (err) {
      setDeleteError(err.message)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      <header className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="mr-auto min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold truncate">{robot.name}</h2>
            <RobotStatusBadge status={robot.status} />
            {robot.streaming && (
              <span className="text-xs text-accent">
                ● streaming{robot.detection_mode && ` · detection on ${robot.detection_mode}`}
              </span>
            )}
          </div>
          <p className="text-sm text-text-secondary">
            {robot.name !== robot.robot_id && `${robot.robot_id} · `}
            {robot.ip_address ? `${robot.ip_address} · ` : ''}
            last heartbeat {formatRelative(robot.last_seen)}
          </p>
        </div>
        <button
          onClick={handleDelete}
          disabled={isOnline}
          title={isOnline ? 'Shut the robot down before removing it' : 'Remove robot'}
          className="flex items-center gap-2 px-3 py-2 border border-border rounded-button text-sm text-text-secondary hover:text-danger hover:border-danger disabled:opacity-40 disabled:pointer-events-none transition"
        >
          <Trash2 size={16} />
          <span>Remove</span>
        </button>
        {deleteError && <p className="basis-full text-sm text-danger">{deleteError}</p>}
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem] items-start">
        <StreamView robotId={robotId} stream={stream} isOnline={isOnline} isStreaming={robot.streaming} />
        <div className="space-y-4">
          <DrivePanel robotId={robotId} isOnline={isOnline} live={robot.live} />
          <SprayPanel robotId={robotId} isOnline={isOnline} live={robot.live} lastSpray={stream.lastSpray} />
          <Panel title="Robot">
            <CommandPanel robotId={robotId} robotStatus={robot.status} />
          </Panel>
          <RecentSightings robotId={robotId} robotName={robot.name} />
        </div>
      </div>
    </div>
  )
}

export default RobotDetail
