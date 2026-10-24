import { useState } from 'react'
import { RobotsProvider, useRobotsContext } from './context/RobotsContext'
import useRobots from './hooks/useRobots'
import TopBar from './components/layout/TopBar'
import Sidebar from './components/layout/Sidebar'
import AddRobotModal from './components/robots/AddRobotModal'
import RobotDetail from './pages/RobotDetail'
import History from './pages/History'

function MainView() {
  const { view, selectedRobotId } = useRobotsContext()
  if (view === 'history') return <History />
  if (selectedRobotId) return <RobotDetail robotId={selectedRobotId} />
  return (
    <div className="flex-1 flex items-center justify-center p-6 text-center text-text-secondary">
      <div>
        <p className="text-lg font-medium mb-1">Select a robot</p>
        <p className="text-sm">Pick one from the list to see its camera, or open History for past sightings.</p>
      </div>
    </div>
  )
}

function AppContent() {
  const [showAddRobotModal, setShowAddRobotModal] = useState(false)
  useRobots()

  return (
    <div className="flex flex-col h-screen bg-background text-text-primary">
      <TopBar />
      <div className="flex flex-col md:flex-row flex-1 min-h-0">
        <Sidebar onAddRobot={() => setShowAddRobotModal(true)} />
        <main className="flex flex-1 min-w-0 min-h-0">
          <MainView />
        </main>
      </div>
      {showAddRobotModal && <AddRobotModal onClose={() => setShowAddRobotModal(false)} />}
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
