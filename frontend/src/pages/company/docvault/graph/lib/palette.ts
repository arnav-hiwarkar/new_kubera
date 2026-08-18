export const BUCKET_PALETTE = [
  '#38BDF8', // Sky
  '#818CF8', // Indigo
  '#A78BFA', // Violet
  '#F472B6', // Pink
  '#FB7185', // Rose
  '#FBBF24', // Amber
  '#34D399', // Emerald
  '#2DD4BF', // Teal
  '#60A5FA', // Blue
  '#C084FC', // Purple
]

export const STATUS_COLORS: Record<string, string> = {
  verified: '#10B981',
  uploaded: '#3B82F6',
  submitted: '#6366F1',
  pending_approval: '#F59E0B',
  action_required: '#EF4444',
  overdue: '#DC2626',
  archived: '#6B7280',
}

export function getBucketColor(bucketId: string | null | undefined, index = 0): string {
  if (!bucketId || bucketId === 'uncategorized') return '#94A3B8'
  let hash = 0
  for (let i = 0; i < bucketId.length; i++) {
    hash = (hash << 5) - hash + bucketId.charCodeAt(i)
    hash |= 0
  }
  const idx = Math.abs(hash + index) % BUCKET_PALETTE.length
  return BUCKET_PALETTE[idx]
}

export function getDocumentColor(
  doc: { bucket_id: string | null; status: string },
  colorMode: 'bucket' | 'status',
  bucketIndex = 0,
): string {
  if (colorMode === 'status') {
    return STATUS_COLORS[doc.status] || '#94A3B8'
  }
  return getBucketColor(doc.bucket_id, bucketIndex)
}
