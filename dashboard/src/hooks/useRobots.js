import { useCallback, useEffect, useState, useRef } from 'react'
import APIClient from '../api/client'
import { useRobotsContext } from '../context/RobotsContext'

/**
 * Poll /api/robots every 5 seconds and update global context.
 */
export function useRobots() {
  const { updateRobots, registerRefreshRobots } = useRobotsContext()
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const pollTimeoutRef = useRef(null)
  const activeRequestIdRef = useRef(0)
  const abortControllerRef = useRef(null)

  const fetchRobots = useCallback(async () => {
    const requestId = activeRequestIdRef.current + 1
    activeRequestIdRef.current = requestId

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const controller = new AbortController()
    abortControllerRef.current = controller

    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }

    try {
      const data = await APIClient.getRobots({ signal: controller.signal })

      if (activeRequestIdRef.current === requestId) {
        updateRobots(data)
        setError(null)
      }
    } catch (err) {
      if (err.name !== 'AbortError' && activeRequestIdRef.current === requestId) {
        setError(err.message)
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }

      if (activeRequestIdRef.current === requestId) {
        setIsLoading(false)
        pollTimeoutRef.current = setTimeout(() => {
          void fetchRobots()
        }, 5000)
      }
    }
  }, [updateRobots])

  useEffect(() => {
    registerRefreshRobots(fetchRobots)

    const handleManualRefresh = () => {
      void fetchRobots()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void fetchRobots()
      }
    }

    void fetchRobots()

    window.addEventListener('robots:refresh', handleManualRefresh)
    window.addEventListener('focus', handleManualRefresh)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
      }
      window.removeEventListener('robots:refresh', handleManualRefresh)
      window.removeEventListener('focus', handleManualRefresh)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [fetchRobots, registerRefreshRobots])

  return { isLoading, error }
}

export default useRobots
