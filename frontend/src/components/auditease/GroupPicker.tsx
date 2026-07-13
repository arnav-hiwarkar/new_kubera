import { useEffect, useMemo, useState } from 'react'
import { Select } from '@/components/ui'
import type { LedgerGroupResponse } from '@/api/types'

const byName = (a: LedgerGroupResponse, b: LedgerGroupResponse) => a.name.localeCompare(b.name)

/**
 * Cascading group → subgroup → subsubgroup picker that enforces the leaf rule:
 * a deeper select only appears when the chosen node has children, and `onChange`
 * fires the leaf group id only once a leaf is reached (null while incomplete).
 */
export function GroupPicker({
  groups,
  value,
  onChange,
  disabled,
}: {
  groups: LedgerGroupResponse[]
  value: string | null
  onChange: (leafGroupId: string | null) => void
  disabled?: boolean
}) {
  const byId = useMemo(() => new Map(groups.map((g) => [g.id, g])), [groups])
  const childrenOf = (pid: string) => groups.filter((g) => g.parent_id === pid).sort(byName)
  const tops = useMemo(() => groups.filter((g) => g.level === 0).sort(byName), [groups])

  const [top, setTop] = useState('')
  const [sub, setSub] = useState('')
  const [subsub, setSubsub] = useState('')

  useEffect(() => {
    if (!value) {
      setTop('')
      setSub('')
      setSubsub('')
      return
    }
    const chain: LedgerGroupResponse[] = []
    let cur = byId.get(value)
    while (cur) {
      chain.unshift(cur)
      cur = cur.parent_id ? byId.get(cur.parent_id) : undefined
    }
    setTop(chain[0]?.id ?? '')
    setSub(chain[1]?.id ?? '')
    setSubsub(chain[2]?.id ?? '')
  }, [value, byId])

  const resolveLeaf = (t: string, s: string, ss: string): string | null => {
    const tg = byId.get(t)
    if (!tg) return null
    if (!tg.has_children) return t
    const sg = byId.get(s)
    if (!sg) return null
    if (!sg.has_children) return s
    return byId.get(ss) ? ss : null
  }

  const onTop = (v: string) => {
    setTop(v)
    setSub('')
    setSubsub('')
    onChange(resolveLeaf(v, '', ''))
  }
  const onSub = (v: string) => {
    setSub(v)
    setSubsub('')
    onChange(resolveLeaf(top, v, ''))
  }
  const onSubsub = (v: string) => {
    setSubsub(v)
    onChange(resolveLeaf(top, sub, v))
  }

  const topG = byId.get(top)
  const subG = byId.get(sub)

  return (
    <div className="flex flex-wrap gap-2">
      <Select value={top} onChange={(e) => onTop(e.target.value)} disabled={disabled} className="min-w-[9rem]">
        <option value="">Group…</option>
        {tops.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </Select>

      {topG?.has_children && (
        <Select value={sub} onChange={(e) => onSub(e.target.value)} disabled={disabled} className="min-w-[9rem]">
          <option value="">Subgroup…</option>
          {childrenOf(top).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </Select>
      )}

      {subG?.has_children && (
        <Select value={subsub} onChange={(e) => onSubsub(e.target.value)} disabled={disabled} className="min-w-[9rem]">
          <option value="">Subsubgroup…</option>
          {childrenOf(sub).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </Select>
      )}
    </div>
  )
}
