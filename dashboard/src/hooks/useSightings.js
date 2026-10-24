import { useCallback, useEffect, useRef, useState } from 'react'
import APIClient from '../api/client'

/**
 * Loads detection history, newest first, for the given filters
 * ({ robot_id, label, since }). Refreshes every `refreshMs` and supports "load more".
 * Returns: { sightings, hasMore, isLoading, error, loadMore, refresh }
 */
export function useSightings(filters, { pageSize = 24, refreshMs = 15000 } = {}) {
  const [sightings, setSightings] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const filterKey = JSON.stringify(filters)
  const loadedCountRef = useRef(pageSize)
  // Ignore responses that arrive after the filters changed.
  const requestIdRef = useRef(0)

  const refresh = useCallback(async () => {
    const requestId = ++requestIdRef.current
    try {
      // Reload everything currently shown, so a refresh does not undo "load more".
      const limit = Math.min(200, Math.max(pageSize, loadedCountRef.current))
      const page = await APIClient.getSightings({ ...JSON.parse(filterKey), limit })
      if (requestId !== requestIdRef.current) return
      setSightings(page)
      setHasMore(page.length === limit)
      setError(null)
    } catch (err) {
      if (requestId === requestIdRef.current) setError(err.message)
    } finally {
      if (requestId === requestIdRef.current) setIsLoading(false)
    }
  }, [filterKey, pageSize])

  const loadMore = useCallback(async () => {
    const last = sightings[sightings.length - 1]
    if (!last) return
    const requestId = ++requestIdRef.current
    try {
      const page = await APIClient.getSightings({ ...JSON.parse(filterKey), limit: pageSize, before_id: last.id })
      if (requestId !== requestIdRef.current) return
      setSightings((current) => {
        const next = [...current, ...page]
        loadedCountRef.current = next.length
        return next
      })
      setHasMore(page.length === pageSize)
    } catch (err) {
      if (requestId === requestIdRef.current) setError(err.message)
    }
  }, [filterKey, pageSize, sightings])

  useEffect(() => {
    loadedCountRef.current = pageSize
    setIsLoading(true)
    setSightings([])
    void refresh()
    const interval = setInterval(() => void refresh(), refreshMs)
    return () => clearInterval(interval)
  }, [refresh, refreshMs, pageSize])

  return { sightings, hasMore, isLoading, error, loadMore, refresh }
}

export default useSightings
