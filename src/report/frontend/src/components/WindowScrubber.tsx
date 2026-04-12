/** Time scrubber with playback — replay historical windows at 2s intervals. */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchWindows } from '../api/client'
import { COLORS } from '../lib/colors'

interface Props {
  onWindowChange: (window: string | undefined) => void
  selectedWindow: string | undefined
}

export default function WindowScrubber({ onWindowChange, selectedWindow }: Props) {
  const { data: windows = [] } = useQuery({
    queryKey: ['windows'],
    queryFn: fetchWindows,
    staleTime: 60_000,
  })
  const [playing, setPlaying] = useState(false)
  const [index, setIndex] = useState<number | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Playback loop
  useEffect(() => {
    if (!playing || windows.length === 0) return

    const startIdx = index ?? 0
    let current = startIdx

    intervalRef.current = setInterval(() => {
      current++
      if (current >= windows.length) {
        setPlaying(false)
        setIndex(null)
        onWindowChange(undefined) // back to latest
        return
      }
      setIndex(current)
      onWindowChange(windows[current])
    }, 2000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, windows, index, onWindowChange])

  const handleSlider = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const i = parseInt(e.target.value, 10)
    setIndex(i)
    onWindowChange(windows[i])
    setPlaying(false) // stop playback on manual scrub
  }, [windows, onWindowChange])

  const togglePlay = useCallback(() => {
    if (playing) {
      setPlaying(false)
    } else {
      // Start from current position. If at LIVE (end), start from ~80% through
      // so the user sees the interesting recent history, not ancient calm data
      const startIdx = (index !== null && index < windows.length - 1)
        ? index
        : Math.max(0, Math.floor(windows.length * 0.8))
      setIndex(startIdx)
      onWindowChange(windows[startIdx])
      setPlaying(true)
    }
  }, [playing, windows, index, onWindowChange])

  const handleLive = useCallback(() => {
    setPlaying(false)
    setIndex(null)
    onWindowChange(undefined)
  }, [onWindowChange])

  if (windows.length < 2) return null

  const currentIdx = index ?? windows.length - 1
  const currentWindow = windows[currentIdx]
  const isLive = !selectedWindow

  return (
    <div className="flex items-center gap-3 max-w-4xl mx-auto">
      {/* Play/Stop */}
      <button
        onClick={togglePlay}
        className="text-xs font-medium px-3 py-1.5 rounded-md border transition-colors"
        style={{
          borderColor: playing ? '#e85d5d44' : '#e5e7eb',
          backgroundColor: playing ? '#e85d5d11' : 'white',
          color: playing ? COLORS.coral : '#64748b',
        }}
      >
        {playing ? 'Stop' : 'Play'}
      </button>

      {/* Slider */}
      <input
        type="range"
        min={0}
        max={windows.length - 1}
        value={currentIdx}
        onChange={handleSlider}
        className="flex-1 h-1 cursor-pointer"
        style={{ accentColor: '#2a8a7a' }}
      />

      {/* Live button */}
      <button
        onClick={handleLive}
        className="text-xs font-medium px-3 py-1.5 rounded-md border transition-colors"
        style={{
          borderColor: isLive ? '#2a8a7a44' : '#e5e7eb',
          backgroundColor: isLive ? '#2a8a7a11' : 'white',
          color: isLive ? COLORS.teal : '#64748b',
        }}
      >
        Live
      </button>

      {/* Timestamp */}
      <span className="text-[11px] min-w-[150px] text-right" style={{ color: '#94a3b8' }}>
        {currentWindow
          ? new Date(currentWindow).toLocaleString()
          : 'Latest'}
      </span>
    </div>
  )
}
