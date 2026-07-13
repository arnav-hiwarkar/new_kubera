import { useState } from 'react'
import { PageHeader } from '@/components/ui'
import { cn } from '@/lib/cn'
import type { Domain } from '@/api/hooks/compliance'
import { RecordsTab } from './RecordsTab'
import { DocumentTypesTab } from './DocumentTypesTab'

type Tab = 'records' | 'types'

const COPY: Record<Domain, { title: string; description: string }> = {
  roc: {
    title: 'ROC Compliance',
    description: 'Registrar of Companies document types and meeting records',
  },
  secretarial: {
    title: 'SecretarialEase',
    description: 'Secretarial compliance document types and meeting records',
  },
}

export function CompliancePage({ domain }: { domain: Domain }) {
  const [tab, setTab] = useState<Tab>('records')
  const copy = COPY[domain]

  const tabs: { id: Tab; label: string }[] = [
    { id: 'records', label: 'Records' },
    { id: 'types', label: 'Document Types' },
  ]

  return (
    <div>
      <PageHeader title={copy.title} description={copy.description} />

      <div className="mb-4 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.id
                ? 'border-accent text-text-primary'
                : 'border-transparent text-text-muted hover:text-text-primary',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'records' ? (
        <RecordsTab domain={domain} />
      ) : (
        <DocumentTypesTab domain={domain} />
      )}
    </div>
  )
}
