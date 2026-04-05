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
    <div className="absolute right-0 top-0 h-full w-72 bg-murmur-navy/95 border-l border-murmur-steel overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-murmur-steel">
        <h3 className="text-sm font-medium">
          <span className="text-murmur-teal">{connection.source}</span>
          <span className="text-murmur-slate mx-1">&rarr;</span>
          <span className="text-murmur-teal">{connection.target}</span>
        </h3>
        <button onClick={onClose} className="text-murmur-slate hover:text-white text-xs">
          ESC
        </button>
      </div>

      {/* Summary */}
      <div className="px-4 py-3 border-b border-murmur-steel/50 text-xs text-murmur-slate">
        <span>flux: <span className="text-white">{connection.flux.toFixed(1)}</span></span>
        {connection.has_new_edge && (
          <span className="ml-3 text-murmur-coral">novel edge</span>
        )}
      </div>

      {/* Actor list */}
      <div className="p-4 space-y-2">
        {connection.actors.map((actorId) => (
          <div
            key={actorId}
            className="flex items-center gap-2 bg-murmur-steel/30 rounded px-3 py-2"
          >
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: COLORS.teal }}
            />
            <span className="text-xs text-white truncate">
              {shortActor(actorId)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
