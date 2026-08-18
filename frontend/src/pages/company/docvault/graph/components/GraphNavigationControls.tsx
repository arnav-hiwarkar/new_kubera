import { Plus, Minus, Focus, Compass, Pause, Play } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { GraphControlsApi } from '../hooks/useGraphControls'

export interface GraphNavigationControlsProps {
  controls?: GraphControlsApi
  onZoomIn?: () => void
  onZoomOut?: () => void
  onResetCamera?: () => void
  onRecenter?: () => void
  onTogglePhysics?: () => void
  isPaused?: boolean
  className?: string
}

export function GraphNavigationControls({
  controls,
  onZoomIn,
  onZoomOut,
  onResetCamera,
  onRecenter,
  onTogglePhysics,
  isPaused: propIsPaused,
  className = '',
}: GraphNavigationControlsProps) {
  const handleZoomIn = onZoomIn ?? controls?.zoomIn
  const handleZoomOut = onZoomOut ?? controls?.zoomOut
  const handleResetCamera = onResetCamera ?? controls?.resetCamera
  const handleRecenter = onRecenter ?? controls?.recenter
  const handleTogglePhysics = onTogglePhysics ?? controls?.togglePhysics

  const isPaused = propIsPaused !== undefined ? propIsPaused : (controls?.isPaused ?? false)

  return (
    <div
      role="toolbar"
      aria-label="Graph Navigation Controls"
      className={cn(
        'fixed bottom-6 right-6 z-30 flex items-center gap-1 p-1.5 rounded-xl bg-slate-900/85 backdrop-blur-md border border-slate-700/60 shadow-2xl text-slate-200',
        className,
      )}
    >
      {/* Zoom In */}
      <button
        type="button"
        onClick={handleZoomIn}
        aria-label="Zoom In"
        title="Zoom In"
        data-testid="nav-zoom-in"
        className="p-2 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-slate-500"
      >
        <Plus className="w-4 h-4" />
      </button>

      {/* Zoom Out */}
      <button
        type="button"
        onClick={handleZoomOut}
        aria-label="Zoom Out"
        title="Zoom Out"
        data-testid="nav-zoom-out"
        className="p-2 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-slate-500"
      >
        <Minus className="w-4 h-4" />
      </button>

      <div className="w-[1px] h-4 bg-slate-700/80 mx-0.5" />

      {/* Reset Camera / Fit */}
      <button
        type="button"
        onClick={handleResetCamera}
        aria-label="Reset Camera"
        title="Reset Camera"
        data-testid="nav-reset-camera"
        className="p-2 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-slate-500"
      >
        <Focus className="w-4 h-4" />
      </button>

      {/* Recenter */}
      <button
        type="button"
        onClick={handleRecenter}
        aria-label="Recenter"
        title="Recenter"
        data-testid="nav-recenter"
        className="p-2 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-slate-500"
      >
        <Compass className="w-4 h-4" />
      </button>

      <div className="w-[1px] h-4 bg-slate-700/80 mx-0.5" />

      {/* Pause / Play Physics */}
      <button
        type="button"
        onClick={handleTogglePhysics}
        aria-label={isPaused ? 'Resume Physics' : 'Pause Physics'}
        title={isPaused ? 'Resume Physics' : 'Pause Physics'}
        data-testid="nav-toggle-physics"
        className={cn(
          'p-2 rounded-lg transition-colors duration-150 focus:outline-none focus:ring-1 focus:ring-slate-500',
          isPaused
            ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
            : 'hover:bg-slate-800 text-slate-300 hover:text-white',
        )}
      >
        {isPaused ? <Play className="w-4 h-4 text-emerald-400" /> : <Pause className="w-4 h-4" />}
      </button>
    </div>
  )
}
