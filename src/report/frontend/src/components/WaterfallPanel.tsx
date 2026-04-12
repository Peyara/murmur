/** WaterfallPanel — slide-in temporal view showing actor swim lanes with event chains.
 *
 * Each actor gets a horizontal lane. Events are dots. Authorized events have
 * a solid backward chain to their trigger. Unauthorized events are orphans —
 * dots with no chain. The broken chain IS the murmur.
 */

import { useEffect, useCallback } from 'react'
import { riskToColor, COLORS } from '../lib/colors'
import type { WaterfallResponse, WaterfallLane, ZoneConnection } from '../api/types'

interface Props {
  data: WaterfallResponse
  selectedZone: string | null
  selectedConnection: ZoneConnection | null
  onClose: () => void
}

function shortActor(id: string): string {
  return id.split('@')[0] ?? id
}

const ZONE_COLORS: Record<string, string> = {
  CONTROL: '#6366f1',
  IDENTITY: '#0d9488',
  SECRET: '#dc2626',
  DATA: '#3b82f6',
  COMPUTE: '#d97706',
  EXFIL_RISK: '#991b1b',
}

export default function WaterfallPanel({ data, selectedZone, selectedConnection, onClose }: Props) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const title = selectedZone
    ? selectedZone.replace('_', ' ')
    : selectedConnection
      ? `${selectedConnection.source} → ${selectedConnection.target}`
      : 'Events'

  return (
    <div
      className="absolute right-0 top-0 h-full overflow-y-auto border-l shadow-xl"
      style={{ width: 360, backgroundColor: 'white', borderColor: '#e5e7eb' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#f0f0f0' }}>
        <div>
          <h3 className="text-sm font-semibold" style={{ color: '#334155' }}>{title}</h3>
          <p className="text-[10px] mt-0.5" style={{ color: '#94a3b8' }}>
            {data.lanes.length} actors | {data.lanes.reduce((s, l) => s + l.events.length, 0)} events
          </p>
        </div>
        <button onClick={onClose} className="text-xs px-2 py-1 rounded" style={{ color: '#94a3b8' }}>
          ESC
        </button>
      </div>

      {/* Actor lanes */}
      <div className="divide-y" style={{ borderColor: '#f8f8f8' }}>
        {data.lanes.map((lane) => (
          <LaneRow key={lane.actor_id} lane={lane} />
        ))}
      </div>

      {data.lanes.length === 0 && (
        <div className="p-5 text-xs" style={{ color: '#94a3b8' }}>
          No events for this selection
        </div>
      )}
    </div>
  )
}

function LaneRow({ lane }: { lane: WaterfallLane }) {
  const isAuthorized = lane.provenance_level !== 'NONE'
  const riskColor = riskToColor(lane.residual_risk)

  return (
    <div className="px-5 py-3">
      {/* Actor header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {/* Authorization indicator */}
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: isAuthorized ? '#94a3b8' : riskColor,
              boxShadow: isAuthorized ? 'none' : `0 0 4px ${riskColor}`,
            }}
          />
          <span className="text-xs font-medium" style={{ color: '#334155' }}>
            {shortActor(lane.actor_id)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Provenance badge */}
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: isAuthorized ? '#f0fdf4' : '#fef2f2',
              color: isAuthorized ? '#15803d' : '#dc2626',
            }}
          >
            {lane.provenance_level}
          </span>
          {/* Risk */}
          <span className="text-[10px]" style={{ color: riskColor }}>
            {lane.residual_risk.toFixed(3)}
          </span>
        </div>
      </div>

      {/* Fired invariants */}
      {lane.fired_invariants.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {lane.fired_invariants.map((inv) => (
            <span
              key={inv}
              className="text-[9px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: '#fef2f2', color: '#dc2626' }}
            >
              {inv}
            </span>
          ))}
        </div>
      )}

      {/* Event chain */}
      <div className="space-y-1">
        {lane.events.map((event, i) => {
          const hasChain = event.trigger_ref !== null
          const zoneColor = ZONE_COLORS[event.target_zone] ?? '#94a3b8'

          return (
            <div key={event.event_id} className="flex items-center gap-2">
              {/* Chain connector */}
              <div className="w-4 flex justify-center">
                {i > 0 && (
                  <div
                    className="w-px h-3 -mt-1"
                    style={{
                      backgroundColor: hasChain ? '#d1d5db' : 'transparent',
                      borderLeft: hasChain ? 'none' : '1px dashed #fca5a5',
                    }}
                  />
                )}
              </div>

              {/* Event dot */}
              <div
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{
                  backgroundColor: hasChain ? zoneColor : COLORS.coral,
                  outline: hasChain ? 'none' : `2px solid ${COLORS.coral}33`,
                }}
              />

              {/* Event info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium" style={{ color: '#334155' }}>
                    {event.action_type.replace(/_/g, ' ')}
                  </span>
                  <span
                    className="text-[9px] px-1 rounded"
                    style={{ backgroundColor: zoneColor + '15', color: zoneColor }}
                  >
                    {event.target_zone}
                  </span>
                </div>
                <div className="text-[9px] truncate" style={{ color: '#94a3b8' }}>
                  {event.target_id.split('/').pop()}
                  {!hasChain && (
                    <span style={{ color: COLORS.coral }}> — no trigger chain</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
