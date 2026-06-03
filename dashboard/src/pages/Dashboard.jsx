import { useState } from 'react'
import { useRobotsContext } from '../context/RobotsContext'

import RobotDetail from './RobotDetail'
import AddRobotModal from '../components/robots/AddRobotModal'

export function Dashboard() {
  const { selectedRobotId } = useRobotsContext()
  const [showAddRobotModal, setShowAddRobotModal] = useState(false)

  return (
    <div className="flex-1 flex flex-col">
      {selectedRobotId ? (
        <RobotDetail robotId={selectedRobotId} />
      ) : (
        <div className="flex-1 flex items-center justify-center text-text-secondary">
          <div className="text-center">
            <p className="text-lg font-medium mb-2">Select a robot to monitor</p>
            <p className="text-sm">Choose a robot from the sidebar or add a new one</p>
          </div>
        </div>
      )}

      {showAddRobotModal && (
        <AddRobotModal onClose={() => setShowAddRobotModal(false)} />
      )}
    </div>
  )
}

export default Dashboard
