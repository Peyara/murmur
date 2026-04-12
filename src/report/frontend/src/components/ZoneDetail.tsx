/** Slide-in panel showing actors active in a selected zone. */

import { useEffect } from 'react'
import { riskToColor, TIER_COLORS, COLORS } from '../lib/colors'
import { TIER_THRESHOLDS } from '../lib/constants'
import type { AlertTier } from '../api/types'
import { fetchActors } from '../api/client'
import { useQuery } from '@tanstack/react-query'

interface Props {
  zone: string
  window?: string
  onClose: () => void
}

function classifyTier(risk: number): AlertTier {
  if (risk >= TIER_THRESHOLDS.HIGH) return 'HIGH'
  if (risk >= TIER_THRESHOLDS.MEDIUM) return 'MEDIUM'
  if (risk >= TIER_THRESHOLDS.WATCH) return 'WATCH'
  return 'NORMAL'
}

function shortActor(id: string): string {
  return id.split('@')[0] ?? id
}

export default function ZoneDetail({ zone, window: win, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['actors', win, zone],
    queryFn: () => fetchActors(win, zone),
  })

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="absolute right-0 top-0 h-full w-80 bg-white/95 border-l overflow-y-auto shadow-lg" style={{ borderColor: '#e5e7eb' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: '#e5e7eb' }}>
        <h3 className="text-sm font-semibold" style={{ color: '#0d9488' }}>{zone}</h3>
        <button onClick={onClose} className="text-xs" style={{ color: '#94a3b8' }}>
          ESC
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-2">
        {isLoading && <div className="text-xs" style={{ color: '#94a3b8' }}>Loading...</div>}

        {data?.actors.map((actor) => {
          const tier = classifyTier(actor.residual_risk)
          const color = TIER_COLORS[tier]
          return (
            <div key={actor.actor_id} className="rounded-lg p-3 space-y-2 border" style={{ borderColor: '#f0f0f0', backgroundColor: '#fafafa' }}>
              {/* Actor name + tier badge */}
              <div className="flex items-center justify-between">
                <span className="text-xs truncate flex-1" style={{ color: '#1a1a2e' }}>
                  {shortActor(actor.actor_id)}
                </span>
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                  style={{ backgroundColor: color + '22', color }}
                >
                  {tier}
                </span>
              </div>

              {/* Risk bar */}
              <div className="w-full h-1 rounded-full overflow-hidden" style={{ backgroundColor: '#e5e7eb' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, actor.residual_risk * 100)}%`,
                    backgroundColor: riskToColor(actor.residual_risk),
                  }}
                />
              </div>

              {/* Metrics */}
              <div className="flex gap-3 text-[10px]" style={{ color: '#94a3b8' }}>
                <span>risk: <span style={{ color: '#1a1a2e' }}>{actor.residual_risk.toFixed(3)}</span></span>
                <span>events: <span style={{ color: '#1a1a2e' }}>{actor.event_count}</span></span>
                <span>{actor.provenance_level}</span>
              </div>

              {/* Fired invariants */}
              {actor.fired_invariants.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {actor.fired_invariants.map((inv) => (
                    <span
                      key={inv}
                      className="text-[9px] px-1 py-0.5 rounded bg-murmur-coral/20 text-murmur-coral"
                    >
                      {inv}
                    </span>
                  ))}
                </div>
              )}

              {/* Zone sequence */}
              <div className="flex gap-1">
                {actor.zone_sequence.map((z, i) => (
                  <span
                    key={i}
                    className="text-[9px] px-1 py-0.5 rounded"
                    style={{
                      backgroundColor: z === zone ? COLORS.teal + '33' : COLORS.steel,
                      color: z === zone ? COLORS.teal : COLORS.slate,
                    }}
                  >
                    {z}
                  </span>
                ))}
              </div>
            </div>
          )
        })}

        {data && data.actors.length === 0 && (
          <div className="text-murmur-slate text-xs">No actors in this zone</div>
        )}
      </div>
    </div>
  )
}
