// Server times are ISO 8601 strings in UTC (e.g. "2026-06-01T08:00:00Z").

export function formatRelative(iso, now = Date.now()) {
  if (!iso) return 'never'
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000)
  if (seconds < 10) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatDuration(fromIso, toIso) {
  const seconds = Math.max(0, Math.round((new Date(toIso) - new Date(fromIso)) / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} min ${seconds % 60}s`
}

// ISO time for "N hours ago", used by the history time-range filter.
export function hoursAgoIso(hours) {
  return new Date(Date.now() - hours * 3600 * 1000).toISOString()
}
