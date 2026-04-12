import { useState, useCallback } from 'react'
import MeshView from './views/MeshView'
import WindowScrubber from './components/WindowScrubber'

export default function App() {
  const [selectedWindow, setSelectedWindow] = useState<string | undefined>(undefined)

  const handleWindowChange = useCallback((w: string | undefined) => {
    setSelectedWindow(w)
  }, [])

  return (
    <div className="w-full h-full flex flex-col" style={{ backgroundColor: '#f8f9fb' }}>
      {/* Light nav bar */}
      <nav
        className="flex items-center px-8 py-4 border-b"
        style={{ borderColor: '#e5e7eb' }}
      >
        <span className="text-sm font-semibold tracking-widest" style={{ color: '#94a3b8' }}>
          MURMUR
        </span>
      </nav>

      {/* Mesh visualization */}
      <main className="flex-1 relative overflow-hidden">
        <MeshView selectedWindow={selectedWindow} />
      </main>

      {/* Window scrubber */}
      <div className="px-6 pb-3 pt-2 border-t" style={{ borderColor: '#e5e7eb' }}>
        <WindowScrubber
          selectedWindow={selectedWindow}
          onWindowChange={handleWindowChange}
        />
      </div>
    </div>
  )
}
