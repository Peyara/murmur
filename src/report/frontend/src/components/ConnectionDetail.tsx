/** Panel showing actors producing a specific zone-to-zone flow. */

import { useEffect } from 'react'
import { COLORS } from '../lib/colors'
import type { ZoneConnection } from '../api/types'

interface Props {
  connection: ZoneConnection
  onClose: () => void
}

function shortActor(id: string): string {
  return id.split('@')[0] ?? id
}

export default function ConnectionDetail({ connection, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="absolute right-0 top-0 h-full w-72 bg-white/95 border-l overflow-y-auto shadow-lg" style={{ borderColor: '#e5e7eb' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: '#e5e7eb' }}>
        <h3 className="text-sm font-semibold">
          <span style={{ color: '#0d9488' }}>{connection.source}</span>
          <span className="mx-1" style={{ color: '#94a3b8' }}>&rarr;</span>
          <span style={{ color: '#0d9488' }}>{connection.target}</span>
        </h3>
        <button onClick={onClose} className="text-xs" style={{ color: '#94a3b8' }}>
          ESC
        </button>
      </div>

      {/* Summary */}
      <div className="px-4 py-3 border-b text-xs" style={{ borderColor: '#f0f0f0', color: '#64748b' }}>
        <span>flux: <span style={{ color: '#1a1a2e' }}>{connection.flux.toFixed(1)}</span></span>
        {connection.has_new_edge && (
          <span className="ml-3" style={{ color: COLORS.coral }}>novel edge</span>
        )}
      </div>

      {/* Actor list */}
      <div className="p-4 space-y-2">
        {connection.actors.map((actorId) => (
          <div
            key={actorId}
            className="flex items-center gap-2 rounded-lg border px-3 py-2"
            style={{ borderColor: '#f0f0f0', backgroundColor: '#fafafa' }}
          >
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: COLORS.teal }}
            />
            <span className="text-xs truncate" style={{ color: '#1a1a2e' }}>
              {shortActor(actorId)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
