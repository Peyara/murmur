/** Top actors list — progressive disclosure, appears on interaction. */

import { useState } from 'react'
import { riskToColor, TIER_COLORS } from '../lib/colors'
import { TIER_THRESHOLDS } from '../lib/constants'
import type { ActorSummary, AlertTier } from '../api/types'

interface Props {
  actors: ActorSummary[]
}

function classifyTier(risk: number): AlertTier {
  if (risk >= TIER_THRESHOLDS.HIGH) return 'HIGH'
  if (risk >= TIER_THRESHOLDS.MEDIUM) return 'MEDIUM'
  if (risk >= TIER_THRESHOLDS.WATCH) return 'WATCH'
  return 'NORMAL'
}

function shortActor(id: string): string {
  // "normal-worker-sa@proj.iam.gserviceaccount.com" -> "normal-worker-sa"
  return id.split('@')[0] ?? id
}

export default function ActorList({ actors }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (actors.length === 0) return null

  return (
    <div className="absolute top-6 left-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs transition-colors"
        style={{ color: '#64748b' }}
      >
        {expanded ? 'Hide' : `${actors.length} actors`}
      </button>

      {expanded && (
        <div className="mt-2 space-y-1 max-w-xs">
          {actors.map((actor) => {
            const tier = classifyTier(actor.residual_risk)
            const color = TIER_COLORS[tier]
            return (
              <div
                key={actor.actor_id}
                className="flex items-center gap-2 text-xs rounded-lg border px-2 py-1.5 bg-white/90"
                style={{ borderColor: '#e5e7eb' }}
              >
                {/* Risk bar */}
                <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#e5e7eb' }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(100, actor.residual_risk * 100)}%`,
                      backgroundColor: riskToColor(actor.residual_risk),
                    }}
                  />
                </div>

                {/* Actor name */}
                <span className="truncate flex-1" style={{ color: '#334155' }}>
                  {shortActor(actor.actor_id)}
                </span>

                {/* Risk value */}
                <span style={{ color }}>{actor.residual_risk.toFixed(3)}</span>

                {/* Invariant count */}
                {actor.fired_invariants.length > 0 && (
                  <span className="text-murmur-coral text-[10px]">
                    {actor.fired_invariants.length} inv
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
