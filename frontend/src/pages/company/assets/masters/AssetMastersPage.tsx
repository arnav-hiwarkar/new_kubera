import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Library } from 'lucide-react'
import { PageHeader, Tabs } from '@/components/ui'
import { CategoriesTab } from './CategoriesTab'
import { SuppliersTab } from './SuppliersTab'
import { LookupsTab } from './LookupsTab'
import { ItBlocksTab } from './ItBlocksTab'
import { FinancialYearsTab } from './FinancialYearsTab'

/**
 * One screen for master-data sets and accounting periods.
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
        description="Categories, suppliers, financial years, and the dimensions assets are classified by"
      />

      <Tabs
        tabs={[
          { id: 'categories', label: 'Categories' },
          { id: 'suppliers', label: 'Suppliers' },
          { id: 'financial-years', label: 'Financial Years' },
          { id: 'lookups', label: 'Dimensions' },
          { id: 'it-blocks', label: 'Tax blocks' },
        ]}
        value={tab}
        onChange={setTab}
        layoutGroup="asset-masters"
      />

      {tab === 'categories' && <CategoriesTab />}
      {tab === 'suppliers' && <SuppliersTab />}
      {tab === 'financial-years' && <FinancialYearsTab />}
      {tab === 'lookups' && <LookupsTab />}
      {tab === 'it-blocks' && <ItBlocksTab />}
    </div>
  )
}
