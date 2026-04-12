/** MeshView — the single visualization view.
 *
 * Combines the pixel grid mesh (spatial) with the waterfall panel (temporal).
 * The mesh is always visible. The waterfall slides in on click.
 */

import { useRef, useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useZones } from '../hooks/usePolling'
import { fetchWaterfall } from '../api/client'
import AuthMesh from '../components/AuthMesh'
import StatusBar from '../components/StatusBar'
import WaterfallPanel from '../components/WaterfallPanel'
import type { ZoneConnection } from '../api/types'
import { usePulse } from '../hooks/usePolling'

interface Props {
  selectedWindow?: string
}

export default function MeshView({ selectedWindow }: Props) {
  const { data: zonesData, isLoading: zonesLoading } = useZones(selectedWindow)
  const { data: pulseData } = usePulse(selectedWindow)
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })

  // Waterfall state
  const [waterfallZone, setWaterfallZone] = useState<string | null>(null)
  const [waterfallConn, setWaterfallConn] = useState<ZoneConnection | null>(null)
  const showWaterfall = waterfallZone !== null || waterfallConn !== null

  const waterfallWindow = zonesData?.window_start ?? undefined
  const waterfallZoneFilter = waterfallZone ?? waterfallConn?.source ?? undefined

  const { data: waterfallData } = useQuery({
    queryKey: ['waterfall', waterfallWindow, waterfallZoneFilter],
    queryFn: () => fetchWaterfall(waterfallWindow ?? undefined, waterfallZoneFilter ?? undefined),
    enabled: showWaterfall,
  })

  const closeWaterfall = useCallback(() => {
    setWaterfallZone(null)
    setWaterfallConn(null)
  }, [])

  // Resize observer
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  if (zonesLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center" style={{ color: '#94a3b8' }}>
        Loading...
      </div>
    )
  }

  if (!zonesData) {
    return (
      <div className="w-full h-full flex items-center justify-center" style={{ color: '#dc2626' }}>
        Failed to load data
      </div>
    )
  }

  return (
    <div ref={containerRef} className="w-full h-full relative">
      <AuthMesh
        data={zonesData}
        width={showWaterfall ? size.width - 360 : size.width}
        height={size.height}
        onClickZone={(zone) => { setWaterfallZone(zone); setWaterfallConn(null) }}
        onClickConnection={(conn) => { setWaterfallConn(conn); setWaterfallZone(null) }}
      />

      {/* Status overlay */}
      {pulseData && <StatusBar data={pulseData} />}

      {/* Waterfall panel */}
      {showWaterfall && waterfallData && (
        <WaterfallPanel
          data={waterfallData}
          selectedZone={waterfallZone}
          selectedConnection={waterfallConn}
          onClose={closeWaterfall}
        />
      )}
    </div>
  )
}
