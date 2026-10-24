import { ImageOff } from 'lucide-react'
import BoxOverlay from '../common/BoxOverlay'

// The sighting's best photo with its pest boxes drawn on top.
export function SightingPhoto({ sighting, showLabels = false, className = '' }) {
  if (!sighting.snapshot_url) {
    return (
      <div className={`aspect-video bg-background flex items-center justify-center text-text-secondary ${className}`}>
        <ImageOff size={20} />
      </div>
    )
  }
  const boxes = sighting.boxes || []
  return (
    <div className={`relative bg-background ${className}`}>
      {/* snapshot_url names the photo version these boxes belong to. */}
      <img
        src={sighting.snapshot_url}
        alt={`${sighting.label} sighting`}
        loading="lazy"
        className="block w-full h-auto"
      />
      <BoxOverlay
        width={sighting.image_width}
        height={sighting.image_height}
        boxes={boxes}
        labels={showLabels ? boxes.map(() => sighting.label) : []}
      />
    </div>
  )
}

export default SightingPhoto
