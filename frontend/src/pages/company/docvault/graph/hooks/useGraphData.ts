import { useMemo } from 'react'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import type { ColorMode, GraphData, GraphLink, GraphNode } from '../types/graph'
import { getBucketColor, getDocumentColor } from '../lib/palette'

export function transformToGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
): GraphData {
  const bucketMap = new Map<string, BucketResponse>()
  buckets.forEach((b) => bucketMap.set(b.id, b))

  const showAll = visibleBucketIds.has('all')
  const activeDocs = documents.filter((d) => d.status !== 'archived')

  // Filter documents by visible buckets
  const filteredDocs = activeDocs.filter((d) => {
    if (showAll) return true
    if (!d.bucket_id) return visibleBucketIds.has('uncategorized')
    return visibleBucketIds.has(d.bucket_id)
  })

  const nodes: GraphNode[] = []
  const links: GraphLink[] = []

  // Add Bucket Hub Nodes
  const includedBucketIds = new Set<string>()
  filteredDocs.forEach((d) => {
    includedBucketIds.add(d.bucket_id || 'uncategorized')
  })
  if (showAll) {
    buckets.forEach((b) => includedBucketIds.add(b.id))
  }

  Array.from(includedBucketIds).forEach((bId, idx) => {
    const isUncategorized = bId === 'uncategorized'
    const bucket = bucketMap.get(bId)
    const name = isUncategorized ? 'Uncategorized' : bucket?.name || 'Unknown Bucket'
    const color = getBucketColor(isUncategorized ? null : bId, idx)

    nodes.push({
      id: `bucket_${bId}`,
      rawId: bId,
      type: 'bucket',
      name,
      bucketId: isUncategorized ? null : bId,
      bucketName: name,
      color,
      size: 14,
      rawBucket: bucket,
    })
  })

  // Add Document Nodes & Primary Links
  filteredDocs.forEach((doc, idx) => {
    const parentBucketId = doc.bucket_id || 'uncategorized'
    const bucketName = doc.bucket_id
      ? bucketMap.get(doc.bucket_id)?.name || 'Uncategorized'
      : 'Uncategorized'
    const color = getDocumentColor(doc, colorMode, idx)
    const currentVer = doc.versions?.find((v) => v.id === doc.current_version_id)
    const versionNo = currentVer?.version_number ?? (doc.versions?.length || 1)

    const docNodeId = `doc_${doc.id}`
    nodes.push({
      id: docNodeId,
      rawId: doc.id,
      type: 'document',
      name: doc.title,
      bucketId: doc.bucket_id,
      bucketName,
      status: doc.status,
      versionNo,
      sizeBytes: currentVer?.size_bytes,
      tags: doc.tags,
      color,
      size: 6,
      rawDoc: doc,
    })

    // Primary link to parent bucket hub
    links.push({
      source: `bucket_${parentBucketId}`,
      target: docNodeId,
      kind: 'bucket-doc',
      strength: 0.8,
      color: 'rgba(100, 160, 255, 0.35)',
    })
  })

  // Add Secondary Links between docs sharing >= 2 tags
  for (let i = 0; i < filteredDocs.length; i++) {
    for (let j = i + 1; j < filteredDocs.length; j++) {
      const docA = filteredDocs[i]
      const docB = filteredDocs[j]
      if (!docA.tags?.length || !docB.tags?.length) continue
      const sharedTags = docA.tags.filter((t) => docB.tags.includes(t))
      if (sharedTags.length >= 2) {
        links.push({
          source: `doc_${docA.id}`,
          target: `doc_${docB.id}`,
          kind: 'tag-shared',
          strength: 0.15,
          color: 'rgba(255, 255, 255, 0.12)',
        })
      }
    }
  }

  return {
    nodes,
    links,
    bucketMap,
    totalDocuments: activeDocs.length,
    totalBuckets: buckets.length,
  }
}

export function useGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
): GraphData {
  return useMemo(
    () => transformToGraphData(buckets, documents, colorMode, visibleBucketIds),
    [buckets, documents, colorMode, visibleBucketIds],
  )
}
