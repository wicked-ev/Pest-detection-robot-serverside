/**
 * Draws detection boxes over an image.
 *
 * Place it inside a `relative` wrapper together with an <img> sized `w-full h-auto`.
 * The SVG uses the photo's own pixel coordinates (viewBox), so boxes line up at any
 * display size without scaling maths.
 */
export function BoxOverlay({ width, height, boxes = [], labels = [], scores = [] }) {
  if (!width || !height || boxes.length === 0) return null
  const stroke = Math.max(2, width / 250)
  const fontSize = Math.max(12, width / 40)

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden="true"
    >
      {boxes.map(([x1, y1, x2, y2], i) => {
        const score = scores[i]
        const color = score === undefined || score > 0.7 ? '#22c55e' : '#eab308'
        const text = [labels[i], score !== undefined ? `${Math.round(score * 100)}%` : null]
          .filter(Boolean)
          .join(' ')
        return (
          <g key={i}>
            <rect
              x={x1}
              y={y1}
              width={x2 - x1}
              height={y2 - y1}
              fill="none"
              stroke={color}
              strokeWidth={stroke}
            />
            {text && (
              <text
                x={x1}
                y={Math.max(y1 - stroke * 2, fontSize)}
                fill={color}
                fontSize={fontSize}
                fontFamily="Inter, sans-serif"
                paintOrder="stroke"
                stroke="#0a0a0a"
                strokeWidth={fontSize / 6}
              >
                {text}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export default BoxOverlay
