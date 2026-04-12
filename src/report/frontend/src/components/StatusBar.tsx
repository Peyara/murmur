/** Minimal status overlay — light mode. */

import { TIER_COLORS } from '../lib/colors'
import type { PulseResponse } from '../api/types'

interface Props {
  data: PulseResponse
}

export default function StatusBar({ data }: Props) {
  const color = TIER_COLORS[data.status]
  const total = Object.values(data.tier_counts).reduce((a, b) => a + b, 0)

  return (
    <div className="absolute bottom-6 right-6 text-right opacity-80 hover:opacity-100 transition-opacity">
      {/* Status badge */}
      <div className="flex items-center justify-end gap-2 mb-1">
        <div
          className="w-2 h-2 rounded-full animate-pulse"
          style={{ backgroundColor: color }}
        />
        <span className="text-sm font-semibold" style={{ color }}>
          {data.status}
        </span>
      </div>

      {/* Metrics */}
      <div className="text-xs space-y-0.5" style={{ color: '#64748b' }}>
        <div>
          sigma <span style={{ color: '#1a1a2e' }}>{data.sigma_coarse.toFixed(2)}</span>
          {' | '}
          risk <span style={{ color: '#1a1a2e' }}>{data.max_residual.toFixed(3)}</span>
          {' | '}
          <span style={{ color: '#1a1a2e' }}>{total}</span> actors
        </div>

        {/* Tier breakdown */}
        {((data.tier_counts['HIGH'] ?? 0) > 0 || (data.tier_counts['MEDIUM'] ?? 0) > 0) && (
          <div>
            {(data.tier_counts['HIGH'] ?? 0) > 0 && (
              <span className="text-murmur-coral">{data.tier_counts['HIGH']} HIGH </span>
            )}
            {(data.tier_counts['MEDIUM'] ?? 0) > 0 && (
              <span className="text-murmur-copper">{data.tier_counts['MEDIUM']} MED </span>
            )}
            {(data.tier_counts['WATCH'] ?? 0) > 0 && (
              <span className="text-murmur-amber">{data.tier_counts['WATCH']} WATCH</span>
            )}
          </div>
        )}

        {/* Timestamp */}
        <div style={{ color: '#94a3b8' }}>
          {data.window_start
            ? new Date(data.window_start).toLocaleString()
            : 'No data'}
        </div>
      </div>
    </div>
  )
}
