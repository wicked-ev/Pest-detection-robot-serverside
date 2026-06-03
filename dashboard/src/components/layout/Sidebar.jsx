import { useState } from 'react'
import { Plus } from 'lucide-react'
import RobotCard from '../robots/RobotCard'
import { useRobotsContext } from '../../context/RobotsContext'

export function Sidebar({ onAddRobot }) {
  const { robots } = useRobotsContext()

  return (
    <div className="w-80 border-r border-border bg-surface flex flex-col h-screen">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {Object.values(robots).map((robot) => (
          <RobotCard key={robot.robot_id} robot={robot} />
        ))}
        {Object.keys(robots).length === 0 && (
          <div className="text-center py-12 text-text-secondary">
            <p className="text-sm">No robots yet</p>
          </div>
        )}
      </div>

      <div className="border-t border-border p-4">
        <button
          onClick={onAddRobot}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent text-background font-medium rounded-button hover:opacity-90 transition"
        >
          <Plus size={18} />
          <span>Add Robot</span>
        </button>
      </div>
    </div>
  )
}

export default Sidebar
