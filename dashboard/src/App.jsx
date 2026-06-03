import { useState } from 'react'
import { RobotsProvider } from './context/RobotsContext'
import useRobots from './hooks/useRobots'
import TopBar from './components/layout/TopBar'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import AddRobotModal from './components/robots/AddRobotModal'

function AppContent() {
  const [showAddRobotModal, setShowAddRobotModal] = useState(false)
  useRobots()

  return (
    <div className="flex h-screen bg-background text-text-primary">
      <div className="flex flex-col flex-1">
        <TopBar />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar onAddRobot={() => setShowAddRobotModal(true)} />
          <Dashboard />
        </div>
      </div>

      {showAddRobotModal && (
        <AddRobotModal onClose={() => setShowAddRobotModal(false)} />
      )}
    </div>
  )
}

export default function App() {
  return (
    <RobotsProvider>
      <AppContent />
    </RobotsProvider>
  )
}
