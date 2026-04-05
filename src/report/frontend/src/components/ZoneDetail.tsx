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
    <div className="absolute right-0 top-0 h-full w-80 bg-murmur-navy/95 border-l border-murmur-steel overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-murmur-steel">
        <h3 className="text-sm font-medium text-murmur-teal">{zone}</h3>
        <button onClick={onClose} className="text-murmur-slate hover:text-white text-xs">
          ESC
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-2">
        {isLoading && <div className="text-murmur-slate text-xs">Loading...</div>}

        {data?.actors.map((actor) => {
          const tier = classifyTier(actor.residual_risk)
          const color = TIER_COLORS[tier]
          return (
            <div key={actor.actor_id} className="bg-murmur-steel/30 rounded p-3 space-y-2">
              {/* Actor name + tier badge */}
              <div className="flex items-center justify-between">
                <span className="text-xs text-white truncate flex-1">
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
              <div className="w-full h-1 bg-murmur-steel rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, actor.residual_risk * 100)}%`,
                    backgroundColor: riskToColor(actor.residual_risk),
                  }}
                />
              </div>

              {/* Metrics */}
              <div className="flex gap-3 text-[10px] text-murmur-slate">
                <span>risk: <span className="text-white">{actor.residual_risk.toFixed(3)}</span></span>
                <span>events: <span className="text-white">{actor.event_count}</span></span>
                <span className="opacity-60">{actor.provenance_level}</span>
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
