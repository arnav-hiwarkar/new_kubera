import React from 'react'
import { clsx } from 'clsx'
import type { RequirementRequestResponse } from '@/api/types'
import { computeRequirementsStats, type RequirementStatusFilter } from './progress'

interface RequirementsOverviewProps {
  items: RequirementRequestResponse[]
  activeFilter?: RequirementStatusFilter
  onSelectFilter?: (filter: RequirementStatusFilter) => void
  className?: string
}

export const RequirementsOverview: React.FC<RequirementsOverviewProps> = ({
  items,
  activeFilter = 'all',
  onSelectFilter,
  className,
}) => {
  const stats = computeRequirementsStats(items)
  const { total, closed, awaiting, responded, closedPercent } = stats

  const closedWidth = total > 0 ? (closed / total) * 100 : 0
  const respondedWidth = total > 0 ? (responded / total) * 100 : 0
  const awaitingWidth = total > 0 ? (awaiting / total) * 100 : 0

  const filterButtons: Array<{
    id: RequirementStatusFilter
    label: string
    count: number
    dotColor: string
    activeClass: string
  }> = [
    {
      id: 'all',
      label: 'All Requirements',
      count: total,
      dotColor: 'bg-zinc-400',
      activeClass: 'border-zinc-500 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100',
    },
    {
      id: 'closed',
      label: 'Closed',
      count: closed,
      dotColor: 'bg-emerald-500',
      activeClass: 'border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300',
    },
    {
      id: 'responded',
      label: 'Responded',
      count: responded,
      dotColor: 'bg-blue-500',
      activeClass: 'border-blue-500 bg-blue-50 text-blue-900 dark:bg-blue-950/40 dark:text-blue-300',
    },
    {
      id: 'awaiting',
      label: 'Awaiting Response',
      count: awaiting,
      dotColor: 'bg-amber-500',
      activeClass: 'border-amber-500 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-300',
    },
  ]

  return (
    <div
      className={clsx(
        'rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900',
        className
      )}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Requirements Overview
          </h3>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            ({total} total)
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">
            {closedPercent}% Closed
          </span>
          <span className="text-xs text-zinc-400">
            ({closed} of {total})
          </span>
        </div>
      </div>

      {/* Segmented Progress Bar */}
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800 flex">
        {closedWidth > 0 && (
          <div
            style={{ width: `${closedWidth}%` }}
            className="h-full bg-emerald-500 transition-all duration-300"
            title={`Closed: ${closed} (${Math.round(closedWidth)}%)`}
          />
        )}
        {respondedWidth > 0 && (
          <div
            style={{ width: `${respondedWidth}%` }}
            className="h-full bg-blue-500 transition-all duration-300"
            title={`Responded: ${responded} (${Math.round(respondedWidth)}%)`}
          />
        )}
        {awaitingWidth > 0 && (
          <div
            style={{ width: `${awaitingWidth}%` }}
            className="h-full bg-amber-500 transition-all duration-300"
            title={`Awaiting Response: ${awaiting} (${Math.round(awaitingWidth)}%)`}
          />
        )}
      </div>

      {/* Filter Chips / Stat Buttons */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {filterButtons.map((btn) => {
          const isActive = activeFilter === btn.id
          return (
            <button
              key={btn.id}
              type="button"
              onClick={() => onSelectFilter?.(btn.id)}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium border transition-colors',
                isActive
                  ? btn.activeClass
                  : 'border-zinc-200 bg-zinc-50/50 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-400 dark:hover:bg-zinc-800'
              )}
            >
              <span className={clsx('w-2 h-2 rounded-full', btn.dotColor)} />
              <span>{btn.label}</span>
              <span className="font-semibold">{btn.count}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
