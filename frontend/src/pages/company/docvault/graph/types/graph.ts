import type { BucketResponse, DocumentResponse } from '@/api/types'

export type NodeType = 'bucket' | 'document'
export type ColorMode = 'bucket' | 'status'

export interface GraphNode {
  id: string
  rawId: string
  type: NodeType
  name: string
  bucketId: string | null
  bucketName: string
  status?: string
  versionNo?: number
  sizeBytes?: number
  tags?: string[]
  color: string
  size: number
  rawDoc?: DocumentResponse
  rawBucket?: BucketResponse
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
  fx?: number
  fy?: number
  fz?: number
  __sprite?: any
}

export interface GraphLink {
  source: string | GraphNode
  target: string | GraphNode
  kind: 'bucket-doc' | 'tag-shared'
  strength: number
  color: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
  bucketMap: Map<string, BucketResponse>
  totalDocuments: number
  totalBuckets: number
}
