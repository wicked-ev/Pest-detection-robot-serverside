import { Plus } from 'lucide-react'
import RobotCard from '../robots/RobotCard'
import { useRobotsContext } from '../../context/RobotsContext'

export function Sidebar({ onAddRobot }) {
  const { robots, robotsError } = useRobotsContext()
  const robotList = Object.values(robots).sort((a, b) => {
    // Online robots first, then by name.
    if ((a.status === 'online') !== (b.status === 'online')) return a.status === 'online' ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return (
    <aside className="md:w-72 shrink-0 border-b md:border-b-0 md:border-r border-border bg-surface flex flex-col max-h-56 md:max-h-none">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-medium text-text-secondary">
          Robots {robotList.length > 0 && `(${robotList.length})`}
        </h2>
        <button
          onClick={onAddRobot}
          className="flex items-center gap-1 text-sm text-accent hover:underline"
          title="Add a robot in advance (robots with the robot key also register themselves)"
        >
          <Plus size={16} />
          Add
        </button>
      </div>

      {robotsError && (
        <p className="mx-4 mb-2 p-2 text-xs text-danger border border-danger/40 rounded-button">
          Could not load robots: {robotsError}
        </p>
      )}

      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-2">
        {robotList.map((robot) => (
          <RobotCard key={robot.robot_id} robot={robot} />
        ))}
        {robotList.length === 0 && !robotsError && (
          <p className="text-center py-8 text-sm text-text-secondary">
            No robots yet. A robot appears here when it connects.
          </p>
        )}
      </div>
    </aside>
  )
}

export default Sidebar
