import { useEffect, useRef } from 'react'

export function DetectionOverlay({ detections, imageWidth, imageHeight }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !detections) return

    const rect = canvas.parentElement.getBoundingClientRect()
    const containerWidth = rect.width
    const containerHeight = rect.height

    canvas.width = containerWidth
    canvas.height = containerHeight

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scaleX = containerWidth / imageWidth
    const scaleY = containerHeight / imageHeight

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const boxes = detections.boxes || []
    const scores = detections.scores || []
    const labels = detections.labels || []

    boxes.forEach((box, idx) => {
      const [x1, y1, x2, y2] = box
      const score = scores[idx] || 0
      const label = labels[idx] || 'unknown'

      const drawX1 = x1 * scaleX
      const drawY1 = y1 * scaleY
      const drawX2 = x2 * scaleX
      const drawY2 = y2 * scaleY
      const drawWidth = drawX2 - drawX1
      const drawHeight = drawY2 - drawY1

      const color = score > 0.7 ? '#22c55e' : '#eab308'

      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.strokeRect(drawX1, drawY1, drawWidth, drawHeight)

      const text = `${label} ${(score * 100).toFixed(0)}%`
      ctx.fillStyle = color
      ctx.font = '12px Inter, sans-serif'
      ctx.fillText(text, drawX1, Math.max(drawY1 - 4, 12))
    })
  }, [detections, imageWidth, imageHeight])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 cursor-default"
    />
  )
}

export default DetectionOverlay
