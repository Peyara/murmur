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
      // Start from current position, or beginning if at the end
      const startIdx = (index !== null && index < windows.length - 1) ? index : 0
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
    <div className="absolute bottom-0 left-0 right-0 px-6 py-3 bg-murmur-navy/80 border-t border-murmur-steel/30">
      <div className="flex items-center gap-3 max-w-4xl mx-auto">
        {/* Play/Stop */}
        <button
          onClick={togglePlay}
          className="text-xs font-medium px-2 py-1 rounded transition-colors"
          style={{
            backgroundColor: playing ? COLORS.coral + '33' : COLORS.teal + '22',
            color: playing ? COLORS.coral : COLORS.teal,
          }}
        >
          {playing ? 'STOP' : 'PLAY'}
        </button>

        {/* Slider */}
        <input
          type="range"
          min={0}
          max={windows.length - 1}
          value={currentIdx}
          onChange={handleSlider}
          className="flex-1 h-1 accent-murmur-teal cursor-pointer"
        />

        {/* Live button */}
        <button
          onClick={handleLive}
          className={`text-xs px-2 py-1 rounded transition-colors ${
            isLive
              ? 'bg-murmur-teal/20 text-murmur-teal'
              : 'text-murmur-slate hover:text-white'
          }`}
        >
          LIVE
        </button>

        {/* Timestamp */}
        <span className="text-[10px] text-murmur-slate min-w-[140px] text-right">
          {currentWindow
            ? new Date(currentWindow).toLocaleString()
            : 'Latest'}
        </span>
      </div>
    </div>
  )
}
