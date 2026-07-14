import { useState } from 'react'
import { ClipboardCheck, ScrollText } from 'lucide-react'
import { PageHeader, Tabs } from '@/components/ui'
import type { Domain } from '@/api/hooks/compliance'
import { RecordsTab } from './RecordsTab'
import { DocumentTypesTab } from './DocumentTypesTab'

type Tab = 'records' | 'types'

const COPY: Record<Domain, { title: string; description: string; icon: typeof ClipboardCheck }> = {
  roc: {
    title: 'ROC Compliance',
    description: 'Registrar of Companies document types and meeting records',
    icon: ClipboardCheck,
  },
  secretarial: {
    title: 'SecretarialEase',
    description: 'Secretarial compliance document types and meeting records',
    icon: ScrollText,
  },
}

export function CompliancePage({ domain }: { domain: Domain }) {
  const [tab, setTab] = useState<Tab>('records')
  const copy = COPY[domain]
  const Icon = copy.icon

  const tabs = [
    { id: 'records', label: 'Records' },
    { id: 'types', label: 'Document Types' },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="COMPLIANCE"
        icon={<Icon />}
        title={copy.title}
        description={copy.description}
      />

      <Tabs tabs={tabs} value={tab} onChange={(id) => setTab(id as Tab)} />

      {tab === 'records' ? (
        <RecordsTab domain={domain} />
      ) : (
        <DocumentTypesTab domain={domain} />
      )}
    </div>
  )
}
