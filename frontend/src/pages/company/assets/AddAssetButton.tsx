import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, History, PlusCircle } from 'lucide-react'
import { Button } from '@/components/ui'
import { QuickAddAssetModal } from './QuickAddAssetModal'

/** Split entry point: fresh purchases use the six-field modal; assets the
 *  company already owned go to the opening-entry page. */
export function AddAssetButton() {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [quickAddOpen, setQuickAddOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <Button onClick={() => setMenuOpen((v) => !v)}>
        Add asset <ChevronDown className="ml-1 h-4 w-4" />
      </Button>
      {menuOpen && (
        <div className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-border bg-bg-surface py-1 shadow-lg">
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-raised"
            onClick={() => { setMenuOpen(false); setQuickAddOpen(true) }}
          >
            <PlusCircle className="h-4 w-4" /> New asset
          </button>
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-raised"
            onClick={() => { setMenuOpen(false); navigate('/app/assets/new/existing') }}
          >
            <History className="h-4 w-4" /> Existing asset
          </button>
        </div>
      )}
      <QuickAddAssetModal open={quickAddOpen} onClose={() => setQuickAddOpen(false)} />
    </div>
  )
}
