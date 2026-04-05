import { useRef, useState, useEffect } from 'react'
import { usePulse } from '../hooks/usePolling'
import PulseOrb from '../components/PulseOrb'
import StatusBar from '../components/StatusBar'
import TrendSpark from '../components/TrendSpark'
import ActorList from '../components/ActorList'

interface Props {
  selectedWindow?: string
}

export default function Pulse({ selectedWindow }: Props) {
  const { data, isLoading, error } = usePulse(selectedWindow)
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })

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
        {error instanceof Error ? error.message : 'Failed to load pulse data'}
      </div>
    )
  }

  return (
    <div ref={containerRef} className="w-full h-full relative">
      <PulseOrb data={data} width={size.width} height={size.height} />
      <StatusBar data={data} />
      <ActorList actors={data.top_actors} />

      {/* Trend sparkline */}
      <div className="absolute bottom-6 left-6 opacity-40 hover:opacity-100 transition-opacity">
        <TrendSpark trend={data.trend} maxRisk={data.max_residual} />
      </div>

      {/* Time-lapse indicator */}
      {selectedWindow && (
        <div className="absolute top-6 right-6 text-xs text-murmur-amber opacity-80">
          REPLAY MODE
        </div>
      )}
    </div>
  )
}
