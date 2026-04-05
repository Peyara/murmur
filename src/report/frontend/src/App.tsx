import { useState, useCallback } from 'react'
import Pulse from './views/Pulse'
import FlowMap from './views/FlowMap'
import WindowScrubber from './components/WindowScrubber'

type View = 'pulse' | 'flowmap'

export default function App() {
  const [view, setView] = useState<View>('pulse')
  const [selectedWindow, setSelectedWindow] = useState<string | undefined>(undefined)

  const handleWindowChange = useCallback((w: string | undefined) => {
    setSelectedWindow(w)
  }, [])

  return (
    <div className="w-full h-full flex flex-col bg-murmur-bg">
      {/* Minimal nav */}
      <nav className="flex gap-4 px-6 py-3 opacity-70 hover:opacity-100 transition-opacity z-10">
        <button
          onClick={() => setView('pulse')}
          className={`text-sm font-medium tracking-wide ${
            view === 'pulse' ? 'text-murmur-teal' : 'text-murmur-slate'
          }`}
        >
          PULSE
        </button>
        <button
          onClick={() => setView('flowmap')}
          className={`text-sm font-medium tracking-wide ${
            view === 'flowmap' ? 'text-murmur-teal' : 'text-murmur-slate'
          }`}
        >
          FLOW MAP
        </button>
      </nav>

      {/* View */}
      <main className="flex-1 relative pb-12">
        {view === 'pulse'
          ? <Pulse selectedWindow={selectedWindow} />
          : <FlowMap selectedWindow={selectedWindow} />
        }
      </main>

      {/* Window scrubber */}
      <WindowScrubber
        selectedWindow={selectedWindow}
        onWindowChange={handleWindowChange}
      />
    </div>
  )
}
