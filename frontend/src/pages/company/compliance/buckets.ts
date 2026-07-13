import { docvaultApi } from '@/api/endpoints/docvault'

/**
 * Find a docVault bucket by name, creating it if it does not exist. Returns the
 * bucket id. Templates and per-domain record documents each live in their own
 * named bucket, resolved lazily on first upload.
 */
export async function resolveBucket(name: string): Promise<string> {
  const buckets = await docvaultApi.listBuckets()
  const existing = buckets.find((b) => b.name === name)
  if (existing) return existing.id
  const created = await docvaultApi.createBucket({ name })
  return created.id
}
