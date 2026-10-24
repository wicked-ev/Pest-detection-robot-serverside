import { useState } from 'react'
import { useRobotsContext } from '../../context/RobotsContext'
import useSightings from '../../hooks/useSightings'
import Panel from '../common/Panel'
import SightingCard from './SightingCard'
import SightingModal from './SightingModal'

// The latest few sightings of one robot, shown next to its live stream.
export function RecentSightings({ robotId, robotName }) {
  const { openHistory } = useRobotsContext()
  const [opened, setOpened] = useState(null)
  const { sightings, isLoading, error } = useSightings({ robot_id: robotId }, { pageSize: 4, refreshMs: 10000 })

  return (
    <Panel
      title="Recent sightings"
      action={
        <button onClick={() => openHistory(robotId)} className="text-sm text-accent hover:underline">
          View all
        </button>
      }
    >
      {error && <p className="text-sm text-danger">{error}</p>}
      {!isLoading && !error && sightings.length === 0 && (
        <p className="text-sm text-text-secondary">No pests found yet.</p>
      )}
      <div className="grid grid-cols-2 gap-2">
        {sightings.map((sighting) => (
          <SightingCard key={sighting.id} sighting={sighting} onOpen={setOpened} compact />
        ))}
      </div>
      {opened && <SightingModal sighting={opened} robotName={robotName} onClose={() => setOpened(null)} />}
    </Panel>
  )
}

export default RecentSightings
