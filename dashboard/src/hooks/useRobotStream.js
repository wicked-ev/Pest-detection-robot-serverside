import { useEffect, useState, useRef, useCallback } from 'react'
import RobotWebSocket from '../api/websocket'

/**
 * Manages stream WebSocket connection for a robot.
 * Receives binary JPEG frames and text JSON detections.
 * Returns: { frameUrl, detections, fps, isConnected }
 */
export function useRobotStream(robotId, modelName = 'onnx') {
  const [frameUrl, setFrameUrl] = useState(null)
  const [detections, setDetections] = useState(null)
  const [fps, setFps] = useState(0)
  const [isConnected, setIsConnected] = useState(false)

  const wsRef = useRef(null)
  const frameTimestampsRef = useRef([])
  const previousUrlRef = useRef(null)
  const detectionFadeTimerRef = useRef(null)

  const handleMessage = useCallback((event) => {
    if (typeof event.data === 'string') {
      try {
        const detection = JSON.parse(event.data)
        setDetections(detection)

        if (detectionFadeTimerRef.current) {
          clearTimeout(detectionFadeTimerRef.current)
        }
        detectionFadeTimerRef.current = setTimeout(() => {
          setDetections(null)
        }, 2000)
      } catch (err) {
        console.error('Failed to parse detection JSON:', err)
      }
    } else if (event.data instanceof Blob) {
      const blob = event.data
      const url = URL.createObjectURL(blob)

      if (previousUrlRef.current) {
        URL.revokeObjectURL(previousUrlRef.current)
      }
      previousUrlRef.current = url
      setFrameUrl(url)

      const now = Date.now()
      frameTimestampsRef.current.push(now)
      if (frameTimestampsRef.current.length > 10) {
        frameTimestampsRef.current.shift()
      }

      if (frameTimestampsRef.current.length > 1) {
        const timeDiff = frameTimestampsRef.current[frameTimestampsRef.current.length - 1] - frameTimestampsRef.current[0]
        const fpsValue = Math.round((frameTimestampsRef.current.length - 1) / (timeDiff / 1000))
        setFps(fpsValue)
      }
    }
  }, [])

  const handleStatusChange = useCallback((status) => {
    setIsConnected(status === 'connected')
  }, [])

  useEffect(() => {
    if (!robotId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${protocol}://${host}/ws/stream/${robotId}?model=${modelName}`

    wsRef.current = new RobotWebSocket(url, {
      onMessage: handleMessage,
      onStatusChange: handleStatusChange,
    })

    wsRef.current.connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect()
      }
      if (previousUrlRef.current) {
        URL.revokeObjectURL(previousUrlRef.current)
      }
      if (detectionFadeTimerRef.current) {
        clearTimeout(detectionFadeTimerRef.current)
      }
    }
  }, [robotId, modelName, handleMessage, handleStatusChange])

  return { frameUrl, detections, fps, isConnected }
}

export default useRobotStream
