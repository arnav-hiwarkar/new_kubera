import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Library } from 'lucide-react'
import { PageHeader, Tabs } from '@/components/ui'
import { CategoriesTab } from './CategoriesTab'
import { SuppliersTab } from './SuppliersTab'
import { LookupsTab } from './LookupsTab'
import { ItBlocksTab } from './ItBlocksTab'

/**
 * One screen for all four master-data sets, rather than four sidebar entries for
 * things an admin touches during setup and rarely afterwards.
 */
export function AssetMastersPage() {
  const [tab, setTab] = useState('categories')

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/app/assets"
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Register
        </Link>
      </div>

      <PageHeader
        eyebrow="OPERATIONS"
        icon={<Library />}
        title="Asset masters"
        description="Categories, suppliers, and the dimensions assets are classified by"
      />

      <Tabs
        tabs={[
          { id: 'categories', label: 'Categories' },
          { id: 'suppliers', label: 'Suppliers' },
          { id: 'lookups', label: 'Dimensions' },
          { id: 'it-blocks', label: 'Tax blocks' },
        ]}
        value={tab}
        onChange={setTab}
        layoutGroup="asset-masters"
      />

      {tab === 'categories' && <CategoriesTab />}
      {tab === 'suppliers' && <SuppliersTab />}
      {tab === 'lookups' && <LookupsTab />}
      {tab === 'it-blocks' && <ItBlocksTab />}
    </div>
  )
}
