import { useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export function DetectionChart({ robotId, detections }) {
  const [chartData, setChartData] = useState([])

  useEffect(() => {
    if (!detections) return

    setChartData((prev) => {
      const timestamp = new Date().toLocaleTimeString()
      const avgScore =
        detections.scores.length > 0
          ? detections.scores.reduce((a, b) => a + b, 0) / detections.scores.length
          : 0

      const newData = [
        ...prev.slice(-59),
        {
          time: timestamp,
          confidence: Math.round(avgScore * 100),
        },
      ]

      return newData
    })
  }, [detections])

  return (
    <div className="space-y-3">
      <h3 className="font-medium">Detection Confidence (Last 60)</h3>
      {chartData.length === 0 ? (
        <div className="h-40 flex items-center justify-center text-text-secondary text-sm">
          No detections yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#222" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 12 }}
              stroke="#71717a"
              style={{ overflow: 'visible' }}
            />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} stroke="#71717a" />
            <Tooltip
              contentStyle={{
                backgroundColor: '#111111',
                border: '1px solid #222',
                borderRadius: '6px',
              }}
              labelStyle={{ color: '#fafafa' }}
            />
            <Area
              type="monotone"
              dataKey="confidence"
              stroke="#22c55e"
              fill="#22c55e"
              fillOpacity={0.1}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default DetectionChart
