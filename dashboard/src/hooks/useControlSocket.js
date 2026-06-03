import { useEffect, useState, useRef, useCallback } from 'react'
import RobotWebSocket from '../api/websocket'

/**
 * Manages control WebSocket connection for a robot.
 * Sends heartbeat and receives/sends commands.
 * Returns: { isConnected, status }
 */
export function useControlSocket(robotId) {
  const [isConnected, setIsConnected] = useState(false)
  const [status, setStatus] = useState(null)

  const wsRef = useRef(null)
  const heartbeatIntervalRef = useRef(null)

  const handleStatusChange = useCallback((wsStatus) => {
    setIsConnected(wsStatus === 'connected')
  }, [])

  const handleMessage = useCallback((event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'heartbeat' || message.status) {
        setStatus(message.status || 'ok')
      }
    } catch (err) {
      // Ignore parse errors
    }
  }, [])

  useEffect(() => {
    if (!robotId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${protocol}://${host}/ws/control/${robotId}`

    wsRef.current = new RobotWebSocket(url, {
      onMessage: handleMessage,
      onStatusChange: handleStatusChange,
    })

    wsRef.current.connect()

    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current && wsRef.current.isConnected()) {
        wsRef.current.send({
          type: 'heartbeat',
          status: 'ok',
        })
      }
    }, 30000)

    return () => {
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current)
      }
      if (wsRef.current) {
        wsRef.current.disconnect()
      }
    }
  }, [robotId, handleStatusChange, handleMessage])

  return { isConnected, status }
}

export default useControlSocket
