import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import APIClient from '../api/client'
import { useRobotsContext } from '../context/RobotsContext'
import useSightings from '../hooks/useSightings'
import SightingCard from '../components/history/SightingCard'
import SightingModal from '../components/history/SightingModal'
import { hoursAgoIso } from '../utils/time'

const RANGES = [
  { id: '24h', label: '24 hours', hours: 24 },
  { id: '7d', label: '7 days', hours: 24 * 7 },
  { id: '30d', label: '30 days', hours: 24 * 30 },
  { id: 'all', label: 'All time', hours: null },
]

const selectClass =
  'px-3 py-2 bg-background border border-border rounded-button text-sm focus:outline-none focus:border-accent'

export function History() {
  const { robots, historyRobotId, setHistoryRobotId } = useRobotsContext()
  const [label, setLabel] = useState('')
  const [rangeId, setRangeId] = useState('7d')
  // Fixed when the range is picked; recomputing it every render would refetch endlessly.
  const [since, setSince] = useState(() => hoursAgoIso(24 * 7))
  const [summary, setSummary] = useState([])
  const [opened, setOpened] = useState(null)

  const { sightings, hasMore, isLoading, error, loadMore, refresh } = useSightings({
    robot_id: historyRobotId,
    label,
    since,
  })

  useEffect(() => {
    let cancelled = false
    APIClient.getSightingSummary({ robot_id: historyRobotId, since })
      .then((rows) => !cancelled && setSummary(rows))
      .catch(() => !cancelled && setSummary([]))
    return () => {
      cancelled = true
    }
  }, [historyRobotId, since, sightings.length])

  const pickRange = (range) => {
    setRangeId(range.id)
    setSince(range.hours ? hoursAgoIso(range.hours) : '')
  }

  const robotName = (id) => robots[id]?.name || id
  const total = summary.reduce((sum, row) => sum + row.count, 0)

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold mr-auto">Detection history</h2>
        <select
          aria-label="Robot"
          value={historyRobotId}
          onChange={(e) => setHistoryRobotId(e.target.value)}
          className={selectClass}
        >
          <option value="">All robots</option>
          {Object.values(robots).map((robot) => (
            <option key={robot.robot_id} value={robot.robot_id}>
              {robot.name}
            </option>
          ))}
        </select>
        <div className="flex border border-border rounded-button overflow-hidden" role="group" aria-label="Time range">
          {RANGES.map((range) => (
            <button
              key={range.id}
              onClick={() => pickRange(range)}
              className={`px-3 py-2 text-sm transition ${
                rangeId === range.id ? 'bg-border text-text-primary' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => void refresh()}
          className="p-2 border border-border rounded-button text-text-secondary hover:text-text-primary transition"
          aria-label="Refresh"
          title="Refresh"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="Sightings per pest">
        <button
          onClick={() => setLabel('')}
          className={`px-3 py-1 rounded-full border text-sm transition ${
            label === '' ? 'border-accent text-accent' : 'border-border text-text-secondary hover:text-text-primary'
          }`}
        >
          All pests · {total}
        </button>
        {summary.map((row) => (
          <button
            key={row.label}
            onClick={() => setLabel(label === row.label ? '' : row.label)}
            className={`px-3 py-1 rounded-full border text-sm transition ${
              label === row.label ? 'border-accent text-accent' : 'border-border text-text-secondary hover:text-text-primary'
            }`}
          >
            {row.label} · {row.count}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-danger">Could not load history: {error}</p>}

      {!isLoading && sightings.length === 0 && !error && (
        <div className="py-16 text-center text-text-secondary">
          <p className="font-medium mb-1">No sightings in this period</p>
          <p className="text-sm">Pests found by a streaming robot appear here, with a photo of each.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
        {sightings.map((sighting) => (
          <SightingCard
            key={sighting.id}
            sighting={sighting}
            robotName={historyRobotId ? null : robotName(sighting.robot_id)}
            onOpen={setOpened}
          />
        ))}
      </div>

      {hasMore && (
        <div className="flex justify-center">
          <button
            onClick={() => void loadMore()}
            className="px-4 py-2 border border-border rounded-button text-sm hover:bg-border transition"
          >
            Load more
          </button>
        </div>
      )}

      {opened && (
        <SightingModal sighting={opened} robotName={robotName(opened.robot_id)} onClose={() => setOpened(null)} />
      )}
    </div>
  )
}

export default History
