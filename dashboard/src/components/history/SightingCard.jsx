import { formatDuration, formatRelative } from '../../utils/time'
import SightingPhoto from './SightingPhoto'

export function SightingCard({ sighting, robotName, onOpen, compact = false }) {
  const confidence = Math.round(sighting.best_confidence * 100)
  return (
    <button
      onClick={() => onOpen?.(sighting)}
      className="text-left bg-background border border-border rounded-card overflow-hidden hover:border-text-secondary transition focus:outline-none focus:border-accent"
    >
      <SightingPhoto sighting={sighting} />
      <div className={compact ? 'p-2' : 'p-3 space-y-1'}>
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-medium truncate" title={sighting.label}>
            {sighting.label}
          </p>
          <span className="flex items-center gap-2 shrink-0 text-xs">
            {sighting.sprays > 0 && (
              <span className="text-accent" title={`Sprayed ${sighting.sprays} time(s)`}>
                💧{sighting.sprays > 1 ? `×${sighting.sprays}` : ''}
              </span>
            )}
            <span className={confidence > 70 ? 'text-accent' : 'text-warning'}>{confidence}%</span>
          </span>
        </div>
        <p className="text-xs text-text-secondary truncate">
          {formatRelative(sighting.first_seen)}
          {!compact && robotName && ` · ${robotName}`}
          {!compact && sighting.frames > 1 && ` · ${formatDuration(sighting.first_seen, sighting.last_seen)}`}
        </p>
      </div>
    </button>
  )
}

export default SightingCard
