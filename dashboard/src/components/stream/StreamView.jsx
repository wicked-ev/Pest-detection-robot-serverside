import { useEffect, useRef, useState } from 'react'
import { Play, Square } from 'lucide-react'
import useRobotStream from '../../hooks/useRobotStream'
import DetectionOverlay from './DetectionOverlay'
import APIClient from '../../api/client'

export function StreamView({ robotId, modelName = 'onnx' }) {
  const { frameUrl, detections, fps, isConnected } = useRobotStream(robotId, modelName)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const imgRef = useRef(null)
  const [imgDimensions, setImgDimensions] = useState({ width: 640, height: 640 })

  const handleStartStream = async () => {
    try {
      setIsLoading(true)
      await APIClient.sendCommand(robotId, 'start_stream')
      setIsStreaming(true)
    } catch (err) {
      console.error('Failed to start stream:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStopStream = async () => {
    try {
      setIsLoading(true)
      await APIClient.sendCommand(robotId, 'stop_stream')
      setIsStreaming(false)
    } catch (err) {
      console.error('Failed to stop stream:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    const handleImageLoad = () => {
      if (imgRef.current) {
        setImgDimensions({
          width: imgRef.current.naturalWidth,
          height: imgRef.current.naturalHeight,
        })
      }
    }

    const img = imgRef.current
    if (img) {
      img.addEventListener('load', handleImageLoad)
      return () => img.removeEventListener('load', handleImageLoad)
    }
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div className="relative bg-background border border-border rounded-card overflow-hidden flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
        {frameUrl ? (
          <>
            <img
              ref={imgRef}
              src={frameUrl}
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
            disabled={isLoading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-accent text-background font-medium rounded-button hover:opacity-90 disabled:opacity-50 transition"
          >
            <Play size={18} />
            <span>Start Stream</span>
          </button>
        ) : (
          <button
            onClick={handleStopStream}
            disabled={isLoading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-danger text-background font-medium rounded-button hover:opacity-90 disabled:opacity-50 transition"
          >
            <Square size={18} />
            <span>Stop Stream</span>
          </button>
        )}
      </div>
    </div>
  )
}

export default StreamView
