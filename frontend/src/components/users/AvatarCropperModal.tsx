import { useState, useRef, useEffect, useCallback } from 'react'
import { Modal, Button } from '@/components/ui'
import { ZoomIn, ZoomOut, RotateCcw, Move } from 'lucide-react'

interface AvatarCropperModalProps {
  isOpen: boolean
  imageSrc: string | null
  onClose: () => void
  onCropComplete: (blob: Blob) => Promise<void>
}

export function AvatarCropperModal({
  isOpen,
  imageSrc,
  onClose,
  onCropComplete,
}: AvatarCropperModalProps) {
  const [zoom, setZoom] = useState(1.0)
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [imageLoaded, setImageLoaded] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const imageRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Reset state when a new image is loaded or opened
  useEffect(() => {
    if (isOpen) {
      setZoom(1.0)
      setPan({ x: 0, y: 0 })
      setImageLoaded(false)
      setIsSaving(false)
    }
  }, [isOpen, imageSrc])

  // Generate live circular preview
  const generatePreview = useCallback(() => {
    if (!imageRef.current || !imageLoaded) return

    const canvas = document.createElement('canvas')
    const size = 200
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const img = imageRef.current
    const naturalWidth = img.naturalWidth || img.width
    const naturalHeight = img.naturalHeight || img.height

    ctx.clearRect(0, 0, size, size)

    // Clip to circle
    ctx.save()
    ctx.beginPath()
    ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()

    // Calculate crop parameters
    // Viewport box is 280x280
    const viewportSize = 280

    const drawWidth = naturalWidth * (size / viewportSize) * zoom
    const drawHeight = naturalHeight * (size / viewportSize) * zoom
    const drawX = size / 2 - drawWidth / 2 + pan.x * (size / viewportSize)
    const drawY = size / 2 - drawHeight / 2 + pan.y * (size / viewportSize)

    ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight)
    ctx.restore()

    canvas.toBlob((blob) => {
      if (blob) {
        const url = URL.createObjectURL(blob)
        setPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
      }
    }, 'image/png')
  }, [imageLoaded, pan, zoom])

  useEffect(() => {
    generatePreview()
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [generatePreview])

  // Mouse pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    })
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  // Touch pan handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      setIsDragging(true)
      setDragStart({
        x: e.touches[0].clientX - pan.x,
        y: e.touches[0].clientY - pan.y,
      })
    }
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDragging || e.touches.length !== 1) return
    setPan({
      x: e.touches[0].clientX - dragStart.x,
      y: e.touches[0].clientY - dragStart.y,
    })
  }

  const handleTouchEnd = () => {
    setIsDragging(false)
  }

  const handleApplyCrop = async () => {
    if (!imageRef.current) return
    setIsSaving(true)

    try {
      const img = imageRef.current
      const naturalWidth = img.naturalWidth || img.width
      const naturalHeight = img.naturalHeight || img.height

      // Output size: 512x512
      const outputSize = 512
      const canvas = document.createElement('canvas')
      canvas.width = outputSize
      canvas.height = outputSize
      const ctx = canvas.getContext('2d')

      if (!ctx) throw new Error('Canvas context unavailable')

      // Fill background
      ctx.clearRect(0, 0, outputSize, outputSize)

      // Circular clip mask
      ctx.beginPath()
      ctx.arc(outputSize / 2, outputSize / 2, outputSize / 2, 0, Math.PI * 2)
      ctx.closePath()
      ctx.clip()

      // Calculate placement relative to the 280px viewport
      const viewportSize = 280
      const scaleRatio = outputSize / viewportSize

      const baseScale = Math.min(viewportSize / naturalWidth, viewportSize / naturalHeight)
      const currentWidth = naturalWidth * baseScale * zoom
      const currentHeight = naturalHeight * baseScale * zoom

      const drawWidth = currentWidth * scaleRatio
      const drawHeight = currentHeight * scaleRatio
      const drawX = outputSize / 2 - drawWidth / 2 + pan.x * scaleRatio
      const drawY = outputSize / 2 - drawHeight / 2 + pan.y * scaleRatio

      ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight)

      // Convert to blob (PNG format)
      canvas.toBlob(
        async (blob) => {
          if (!blob) {
            setIsSaving(false)
            return
          }
          await onCropComplete(blob)
          setIsSaving(false)
          onClose()
        },
        'image/png',
        0.95
      )
    } catch (err) {
      console.error('Failed to crop avatar:', err)
      setIsSaving(false)
    }
  }

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Adjust Profile Picture"
      size="lg"
    >
      <div className="space-y-6">
        <p className="text-sm text-text-secondary">
          Drag the image to reposition it, and use the zoom slider to adjust the circular framing.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
          {/* Main Cropping Viewport */}
          <div className="md:col-span-2 flex flex-col items-center">
            <div
              ref={containerRef}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
              className="relative h-[280px] w-[280px] overflow-hidden rounded-xl border border-border-strong bg-black/80 select-none cursor-grab active:cursor-grabbing shadow-inner flex items-center justify-center"
            >
              {/* Image element */}
              {imageSrc && (
                <img
                  ref={imageRef}
                  src={imageSrc}
                  alt="Crop target"
                  onLoad={() => setImageLoaded(true)}
                  draggable={false}
                  style={{
                    transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                    transformOrigin: 'center center',
                    transition: isDragging ? 'none' : 'transform 0.05s ease-out',
                    maxWidth: '100%',
                    maxHeight: '100%',
                    objectFit: 'contain',
                  }}
                  className="pointer-events-none"
                />
              )}

              {/* Circular viewport cut-out overlay */}
              <div className="pointer-events-none absolute inset-0 rounded-full border-2 border-accent shadow-[0_0_0_9999px_rgba(0,0,0,0.6)]" />

              {/* Center crosshair / guide */}
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-30">
                <Move className="h-6 w-6 text-white" />
              </div>
            </div>

            {/* Zoom Controls Bar */}
            <div className="mt-4 flex w-full max-w-[280px] items-center gap-3">
              <button
                type="button"
                onClick={() => setZoom((z) => Math.max(1.0, z - 0.1))}
                aria-label="Zoom out"
                className="rounded-btn p-1.5 text-text-muted hover:bg-bg-raised hover:text-text-primary transition-colors"
              >
                <ZoomOut className="h-4 w-4" />
              </button>

              <input
                type="range"
                min="1.0"
                max="3.0"
                step="0.05"
                value={zoom}
                onChange={(e) => setZoom(parseFloat(e.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-border-strong accent-accent"
              />

              <button
                type="button"
                onClick={() => setZoom((z) => Math.min(3.0, z + 0.1))}
                aria-label="Zoom in"
                className="rounded-btn p-1.5 text-text-muted hover:bg-bg-raised hover:text-text-primary transition-colors"
              >
                <ZoomIn className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={() => {
                  setZoom(1.0)
                  setPan({ x: 0, y: 0 })
                }}
                title="Reset crop"
                aria-label="Reset zoom and position"
                className="rounded-btn p-1.5 text-text-muted hover:bg-bg-raised hover:text-text-primary transition-colors"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Live Circular Preview Column */}
          <div className="flex flex-col items-center justify-center border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-6 space-y-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Preview
            </span>

            {/* TopBar sized preview */}
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 overflow-hidden rounded-full border-2 border-accent/40 bg-bg-raised shadow-md flex items-center justify-center">
                {previewUrl ? (
                  <img
                    src={previewUrl}
                    alt="Live preview"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <span className="text-xs text-text-muted">…</span>
                )}
              </div>
              <span className="text-[11px] text-text-secondary">Header Avatar</span>
            </div>

            {/* Small icon preview */}
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 overflow-hidden rounded-full border border-border bg-bg-raised flex items-center justify-center">
                {previewUrl && (
                  <img
                    src={previewUrl}
                    alt="Small preview"
                    className="h-full w-full object-cover"
                  />
                )}
              </div>
              <span className="text-[11px] text-text-muted">32px icon</span>
            </div>
          </div>
        </div>

        {/* Modal Actions */}
        <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
          <Button variant="ghost" onClick={onClose} disabled={isSaving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleApplyCrop}
            loading={isSaving}
            disabled={!imageLoaded}
          >
            Apply & Save
          </Button>
        </div>
      </div>
    </Modal>
  )
}
