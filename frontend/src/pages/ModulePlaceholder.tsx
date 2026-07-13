import { PageHeader, EmptyState } from '@/components/ui'

export interface ModulePlaceholderProps {
  title: string
  description: string
  /** The backend routes this module maps to — surfaced so the scaffold documents itself. */
  endpoints?: string[]
}

/**
 * Scaffold landing page for a module. Renders the header + an empty state noting
 * which backend endpoints the full screen will be built against.
 */
export function ModulePlaceholder({ title, description, endpoints }: ModulePlaceholderProps) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <EmptyState
        title="Scaffold ready"
        description={
          endpoints
            ? `This module is wired to the API client. Backed by: ${endpoints.join(', ')}`
            : 'This module is scaffolded and ready to build out.'
        }
      />
    </div>
  )
}
