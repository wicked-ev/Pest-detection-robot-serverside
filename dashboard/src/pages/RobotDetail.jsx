import { useState } from 'react'
import { useRobotsContext } from '../context/RobotsContext'
import StreamView from '../components/stream/StreamView'
import CommandPanel from '../components/controls/CommandPanel'
import DetectionChart from '../components/charts/DetectionChart'
import useRobotStream from '../hooks/useRobotStream'

export function RobotDetail({ robotId }) {
  const { robots } = useRobotsContext()
  const robot = robots[robotId]
  const { detections } = useRobotStream(robotId)

  if (!robot) {
    return <div>Robot not found</div>
  }

  const lastDetectionText = robot.last_detection
    ? (() => {
        const detection = JSON.parse(robot.last_detection)
        return `${detection.labels?.join(', ') || 'Unknown'}`
      })()
    : 'None'

  const lastSeenText = robot.last_seen
    ? new Date(robot.last_seen).toLocaleString()
    : 'Never'

  return (
    <div className="flex-1 flex gap-6 p-6 overflow-hidden">
      {/* Left column: Stream */}
      <div className="flex-1 overflow-y-auto min-w-0">
        <StreamView robotId={robotId} />
      </div>

      {/* Right column: Info and Controls */}
      <div className="w-96 overflow-y-auto space-y-6">
        {/* Robot Info */}
        <div className="bg-surface border border-border rounded-card p-4 space-y-3">
          <h3 className="font-medium">Robot Information</h3>
          <div className="space-y-2 text-sm">
            <div>
              <p className="text-text-secondary">ID</p>
              <p className="font-medium">{robot.robot_id}</p>
            </div>
            <div>
              <p className="text-text-secondary">IP Address</p>
              <p className="font-medium">{robot.ip_address || 'N/A'}</p>
            </div>
            <div>
              <p className="text-text-secondary">Last Seen</p>
              <p className="font-medium">{lastSeenText}</p>
            </div>
            <div>
              <p className="text-text-secondary">Streaming</p>
              <p className="font-medium">{robot.streaming ? 'Yes' : 'No'}</p>
            </div>
          </div>
        </div>

        {/* Commands */}
        <div className="bg-surface border border-border rounded-card p-4">
          <h3 className="font-medium mb-3">Commands</h3>
          <CommandPanel robotId={robotId} robotStatus={robot.status} />
        </div>

        {/* Detection Stats */}
        <div className="bg-surface border border-border rounded-card p-4 space-y-3">
          <h3 className="font-medium">Latest Detection</h3>
          <div className="text-sm">
            <p className="text-text-secondary">Labels</p>
            <p className="font-medium">{lastDetectionText}</p>
          </div>
        </div>

        {/* Detection Chart */}
        <div className="bg-surface border border-border rounded-card p-4">
          <DetectionChart robotId={robotId} detections={detections} />
        </div>
      </div>
    </div>
  )
}

export default RobotDetail
