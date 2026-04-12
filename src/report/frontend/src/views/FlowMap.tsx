import { useState, useCallback } from 'react'
import { useZones } from '../hooks/usePolling'
import { riskToColor, COLORS } from '../lib/colors'
import { ZONE_POSITIONS, type ZoneName } from '../lib/constants'
import ZoneDetail from '../components/ZoneDetail'
import ConnectionDetail from '../components/ConnectionDetail'
import type { ZoneConnection } from '../api/types'

interface Props {
  selectedWindow?: string
}

export default function FlowMap({ selectedWindow }: Props) {
  const { data, isLoading, error } = useZones(selectedWindow)
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [selectedConn, setSelectedConn] = useState<ZoneConnection | null>(null)

  const closePanel = useCallback(() => {
    setSelectedZone(null)
    setSelectedConn(null)
  }, [])

  if (isLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center text-murmur-slate">
        Loading...
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="w-full h-full flex items-center justify-center text-murmur-coral">
        {error instanceof Error ? error.message : 'Failed to load zone data'}
      </div>
    )
  }

  const W = 800
  const H = 600

  // Max flux for width normalization
  const maxFlux = Math.max(1, ...data.connections.map((c) => c.flux))

  return (
    <div className="w-full h-full flex items-center justify-center relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full max-w-4xl">
        <defs>
          {/* Glow filter for elevated zones */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="4" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Connections */}
        {data.connections.map((conn, i) => {
          const src = ZONE_POSITIONS[conn.source as ZoneName]
          const tgt = ZONE_POSITIONS[conn.target as ZoneName]
          if (!src || !tgt) return null

          const isSelected = selectedConn === conn
          const color = conn.has_new_edge ? COLORS.coral : riskToColor(conn.flux / maxFlux * 0.5)
          const width = Math.max(1, Math.min(8, (conn.flux / maxFlux) * 8))
          // Ghost if no new edges and low flux (likely provenance-explained)
          const opacity = conn.has_new_edge ? 0.8 : 0.15 + (conn.flux / maxFlux) * 0.4

          // Bezier control point
          const mx = (src.x + tgt.x) / 2 * W
          const my = (src.y + tgt.y) / 2 * H
          const dx = tgt.x * W - src.x * W
          const dy = tgt.y * H - src.y * H
          const cx = mx - dy * 0.2
          const cy = my + dx * 0.2

          return (
            <g key={i}>
              <path
                d={`M ${src.x * W} ${src.y * H} Q ${cx} ${cy} ${tgt.x * W} ${tgt.y * H}`}
                fill="none"
                stroke={color}
                strokeWidth={isSelected ? width + 2 : width}
                strokeOpacity={isSelected ? 1 : opacity}
                strokeDasharray={`${width * 3} ${width * 2}`}
                className="cursor-pointer"
                onClick={() => { setSelectedConn(conn); setSelectedZone(null) }}
              >
                {/* Animated directional flow */}
                <animate
                  attributeName="stroke-dashoffset"
                  from={`${width * 5}`}
                  to="0"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </path>

              {/* Novel edge marker */}
              {conn.has_new_edge && (
                <circle
                  cx={cx} cy={cy} r={4}
                  fill={COLORS.coral}
                  fillOpacity={0.8}
                >
                  <animate
                    attributeName="r"
                    values="3;5;3"
                    dur="1.5s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
            </g>
          )
        })}

        {/* Zone nodes */}
        {data.nodes.map((node) => {
          const pos = ZONE_POSITIONS[node.id as ZoneName]
          if (!pos) return null
          const r = Math.max(28, Math.min(50, 24 + node.event_count * 1.5))
          const color = riskToColor(node.max_residual)
          const isSelected = selectedZone === node.id
          const isElevated = node.max_residual >= 0.3

          return (
            <g
              key={node.id}
              className="cursor-pointer"
              onClick={() => { setSelectedZone(node.id); setSelectedConn(null) }}
            >
              {/* Outer glow for elevated zones */}
              {isElevated && (
                <circle
                  cx={pos.x * W} cy={pos.y * H} r={r + 6}
                  fill="none"
                  stroke={color}
                  strokeWidth={1}
                  strokeOpacity={0.3}
                  filter="url(#glow)"
                />
              )}

              {/* Main circle */}
              <circle
                cx={pos.x * W} cy={pos.y * H} r={r}
                fill="white"
                stroke={isSelected ? COLORS.teal : color}
                strokeWidth={isSelected ? 2.5 : 1.5}
              />

              {/* Zone label */}
              <text
                x={pos.x * W} y={pos.y * H - 4}
                textAnchor="middle"
                fill={isElevated ? color : '#334155'}
                fontSize={11}
                fontWeight={500}
                fontFamily="Inter, sans-serif"
              >
                {node.id.replace('_', ' ')}
              </text>

              {/* Event count */}
              <text
                x={pos.x * W} y={pos.y * H + 12}
                textAnchor="middle"
                fill="#64748b"
                fontSize={10}
                fontFamily="Inter, sans-serif"
              >
                {node.event_count} events
              </text>
            </g>
          )
        })}
      </svg>

      {/* Detail panels */}
      {selectedZone && (
        <ZoneDetail
          zone={selectedZone}
          window={data.window_start ?? undefined}
          onClose={closePanel}
        />
      )}
      {selectedConn && (
        <ConnectionDetail
          connection={selectedConn}
          onClose={closePanel}
        />
      )}
    </div>
  )
}
