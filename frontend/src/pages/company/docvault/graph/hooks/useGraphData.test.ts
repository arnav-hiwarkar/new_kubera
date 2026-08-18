import { describe, it, expect } from 'vitest'
import { transformToGraphData } from './useGraphData'
import type { BucketResponse, DocumentResponse } from '@/api/types'

describe('transformToGraphData', () => {
  const mockBuckets: BucketResponse[] = [
    {
      id: 'b1',
      name: 'Finance',
      visibility: 'everyone',
      company_id: 'c1',
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      access_user_ids: [],
    },
  ]

  const mockDocs: DocumentResponse[] = [
    {
      id: 'd1',
      company_id: 'c1',
      title: 'Tax Filing 2026',
      bucket_id: 'b1',
      status: 'verified',
      is_editable: true,
      doc_type_id: null,
      current_version_id: 'v1',
      tags: ['tax', 'q1'],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
    {
      id: 'd2',
      company_id: 'c1',
      title: 'Audit Report',
      bucket_id: 'b1',
      status: 'pending_approval',
      is_editable: true,
      doc_type_id: null,
      current_version_id: 'v2',
      tags: ['tax', 'audit'],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
    {
      id: 'd3',
      company_id: 'c1',
      title: 'Uncategorized Doc',
      bucket_id: null,
      status: 'uploaded',
      is_editable: true,
      doc_type_id: null,
      current_version_id: 'v3',
      tags: [],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
  ]

  it('generates bucket hub nodes and document nodes with primary cluster links', () => {
    const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['all']))
    
    // 1 bucket hub + 1 uncategorized hub + 3 documents = 5 nodes
    expect(data.nodes.length).toBe(5)
    
    const bucketHub = data.nodes.find((n) => n.id === 'bucket_b1')
    expect(bucketHub).toBeDefined()
    expect(bucketHub?.type).toBe('bucket')
    expect(bucketHub?.size).toBe(14)

    const docNode = data.nodes.find((n) => n.id === 'doc_d1')
    expect(docNode).toBeDefined()
    expect(docNode?.type).toBe('document')
    expect(docNode?.size).toBe(6)

    // Check primary links
    const primaryLinks = data.links.filter((l) => l.kind === 'bucket-doc')
    expect(primaryLinks.length).toBe(3)
  })

  it('filters nodes when specific buckets are selected', () => {
    const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['b1']))
    // Only bucket b1 and its 2 documents
    expect(data.nodes.length).toBe(3)
    expect(data.nodes.some((n) => n.id === 'doc_d3')).toBe(false)
  })
})
