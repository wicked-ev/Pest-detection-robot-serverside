import { useState } from 'react'
import { Play, Square, VideoOff } from 'lucide-react'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'
import BoxOverlay from '../common/BoxOverlay'

export function StreamView({ robotId, stream, isOnline, isStreaming }) {
  const { frameUrl, detections, fps } = stream
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [frameSize, setFrameSize] = useState(null)
  const { refreshRobots } = useRobotsContext()

  const sendStreamCommand = async (command) => {
    try {
      setIsLoading(true)
      setError(null)
      await APIClient.sendCommand(robotId, command)
      await refreshRobots?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Detections carry the size of the frame they were computed on; fall back to the image's own size.
  const [width, height] = detections?.image_size || frameSize || []

  return (
    <div className="space-y-3">
      <div className="relative bg-background border border-border rounded-card overflow-hidden">
        {frameUrl ? (
          <>
            <img
              src={frameUrl}
              alt="Live camera feed"
              className="block w-full h-auto"
              onLoad={(e) => setFrameSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}
            />
            {detections && (
              <BoxOverlay
                width={width}
                height={height}
                boxes={detections.boxes}
                labels={detections.labels}
                scores={detections.scores}
              />
            )}
            <span className="absolute top-3 right-3 bg-background/80 px-2 py-1 rounded-button text-xs font-medium">
              {fps} FPS
            </span>
          </>
        ) : (
          <div className="aspect-video flex flex-col items-center justify-center gap-2 text-text-secondary">
            <VideoOff size={28} />
            <p className="font-medium">No video</p>
            <p className="text-sm">
              {!isOnline ? 'The robot is offline.' : isStreaming ? 'Waiting for frames…' : 'Start the stream to see the camera.'}
            </p>
          </div>
        )}
      </div>

      <button
        onClick={() => sendStreamCommand(isStreaming ? 'stop_stream' : 'start_stream')}
        disabled={isLoading || !isOnline}
        className={`w-full flex items-center justify-center gap-2 px-4 py-2 font-medium rounded-button hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition ${
          isStreaming ? 'bg-danger text-background' : 'bg-accent text-background'
        }`}
      >
        {isStreaming ? <Square size={18} /> : <Play size={18} />}
        <span>{isStreaming ? 'Stop stream' : 'Start stream'}</span>
      </button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  )
}

export default StreamView
