import { useEffect } from 'react'
import { X } from 'lucide-react'
import { formatDateTime, formatDuration } from '../../utils/time'
import SightingPhoto from './SightingPhoto'

export function SightingModal({ sighting, robotName, onClose }) {
  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const details = [
    ['Robot', robotName || sighting.robot_id],
    ['First seen', formatDateTime(sighting.first_seen)],
    ['Last seen', formatDateTime(sighting.last_seen)],
    ['Duration', formatDuration(sighting.first_seen, sighting.last_seen)],
    ['Best confidence', `${Math.round(sighting.best_confidence * 100)}%`],
    ['Frames', sighting.frames],
    ['Sprayed', sighting.sprays ? `${sighting.sprays} time(s)` : 'No'],
  ]

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-label={`${sighting.label} sighting`}
        className="bg-surface border border-border rounded-card max-w-3xl w-full max-h-full overflow-y-auto"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold">{sighting.label}</h2>
          <button onClick={onClose} className="text-text-secondary hover:text-text-primary transition" aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <SightingPhoto sighting={sighting} showLabels />
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 p-4 text-sm">
          {details.map(([term, value]) => (
            <div key={term}>
              <dt className="text-text-secondary">{term}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

export default SightingModal
