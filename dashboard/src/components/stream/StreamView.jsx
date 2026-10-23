import { useRef, useState } from 'react'
import { Play, Square } from 'lucide-react'
import DetectionOverlay from './DetectionOverlay'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'

export function StreamView({ robotId, stream, isOnline, isStreaming }) {
  const { frameUrl, detections, fps } = stream
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const imgRef = useRef(null)
  const [imgDimensions, setImgDimensions] = useState({ width: 640, height: 640 })
  const { refreshRobots } = useRobotsContext()

  const handleStartStream = async () => {
    try {
      setIsLoading(true)
      setError(null)
      await APIClient.sendCommand(robotId, 'start_stream')
      await refreshRobots?.()
    } catch (err) {
      setError(err.message)
      console.error('Failed to start stream:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStopStream = async () => {
    try {
      setIsLoading(true)
      setError(null)
      await APIClient.sendCommand(robotId, 'stop_stream')
      await refreshRobots?.()
    } catch (err) {
      setError(err.message)
      console.error('Failed to stop stream:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleImageLoad = () => {
    const img = imgRef.current
    if (img && (img.naturalWidth !== imgDimensions.width || img.naturalHeight !== imgDimensions.height)) {
      setImgDimensions({ width: img.naturalWidth, height: img.naturalHeight })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="relative bg-background border border-border rounded-card overflow-hidden flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
        {frameUrl ? (
          <>
            <img
              ref={imgRef}
              src={frameUrl}
              onLoad={handleImageLoad}
              alt="Robot stream"
              className="w-full h-full object-contain"
            />
            {detections && (
              <DetectionOverlay
                detections={detections}
                imageWidth={imgDimensions.width}
                imageHeight={imgDimensions.height}
              />
            )}
            <div className="absolute top-4 right-4 bg-background/80 px-3 py-1 rounded-button text-sm font-medium">
              {fps} FPS
            </div>
          </>
        ) : (
          <div className="text-center text-text-secondary">
            <p className="text-lg font-medium mb-2">No Signal</p>
            <p className="text-sm">Waiting for stream...</p>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        {!isStreaming ? (
          <button
            onClick={handleStartStream}
            disabled={isLoading || !isOnline}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-accent text-background font-medium rounded-button hover:opacity-90 disabled:opacity-50 transition"
          >
            <Play size={18} />
            <span>Start Stream</span>
          </button>
        ) : (
          <button
            onClick={handleStopStream}
            disabled={isLoading || !isOnline}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-danger text-background font-medium rounded-button hover:opacity-90 disabled:opacity-50 transition"
          >
            <Square size={18} />
            <span>Stop Stream</span>
          </button>
        )}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  )
}

export default StreamView
