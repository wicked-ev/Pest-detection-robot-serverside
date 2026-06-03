import { useEffect, useState, useRef } from 'react'
import APIClient from '../api/client'
import { useRobotsContext } from '../context/RobotsContext'

/**
 * Poll /api/robots every 5 seconds and update global context.
 */
export function useRobots() {
  const { updateRobots } = useRobotsContext()
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const pollIntervalRef = useRef(null)

  useEffect(() => {
    const fetchRobots = async () => {
      try {
        const data = await APIClient.getRobots()
        updateRobots(data)
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setIsLoading(false)
      }
    }

    fetchRobots()
    pollIntervalRef.current = setInterval(fetchRobots, 5000)

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [updateRobots])

  return { isLoading, error }
}

export default useRobots
