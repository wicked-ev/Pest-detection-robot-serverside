import { useRobotsContext } from '../../context/RobotsContext'
import RobotStatusBadge from './RobotStatusBadge'

export function RobotCard({ robot }) {
  const { selectedRobotId, selectRobot } = useRobotsContext()
  const isSelected = selectedRobotId === robot.robot_id

  const lastSeenText = robot.last_seen
    ? `${new Date(robot.last_seen).toLocaleTimeString()}`
    : 'Never'

  return (
    <div
      onClick={() => selectRobot(robot.robot_id)}
      className={`p-4 rounded-card border cursor-pointer transition ${
        isSelected
          ? 'bg-surface border-accent'
          : 'bg-background border-border hover:bg-[#1a1a1a]'
      }`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium truncate">{robot.name}</h3>
          <p className="text-xs text-text-secondary truncate">{robot.robot_id}</p>
        </div>
        <RobotStatusBadge status={robot.status} />
      </div>
      <p className="text-xs text-text-secondary">Last seen: {lastSeenText}</p>
    </div>
  )
}

export default RobotCard
