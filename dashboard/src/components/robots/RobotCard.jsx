import { useRobotsContext } from '../../context/RobotsContext'
import RobotStatusBadge from './RobotStatusBadge'
import { formatRelative } from '../../utils/time'

export function RobotCard({ robot }) {
  const { selectedRobotId, selectRobot, view } = useRobotsContext()
  const isSelected = view === 'live' && selectedRobotId === robot.robot_id
  const details = [
    robot.name !== robot.robot_id ? robot.robot_id : null,
    robot.streaming ? 'streaming' : null,
    formatRelative(robot.last_seen),
  ].filter(Boolean)

  return (
    <button
      onClick={() => selectRobot(robot.robot_id)}
      aria-current={isSelected ? 'true' : undefined}
      className={`w-full text-left p-3 rounded-card border transition ${
        isSelected ? 'bg-background border-accent' : 'bg-background border-border hover:border-text-secondary'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate">{robot.name}</span>
        <RobotStatusBadge status={robot.status} />
      </div>
      <p className="mt-1 text-xs text-text-secondary truncate">{details.join(' · ')}</p>
    </button>
  )
}

export default RobotCard
