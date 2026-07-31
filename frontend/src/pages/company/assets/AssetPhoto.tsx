import { useEffect, useState } from 'react'
import { FileText, ImageOff } from 'lucide-react'
import { assetsApi } from '@/api/endpoints/assets'
import { Spinner } from '@/components/ui'
import { cn } from '@/lib/cn'

/**
 * Renders an attached vault file as an image.
 *
 * Vault files are AES-256-GCM encrypted at rest with a per-file DEK, so there is no
 * URL a browser can put in an <img src>. The bytes come through an authenticated
 * decrypt-and-stream endpoint and become a blob URL, which is revoked on unmount so
 * a gallery of fifty photographs does not leak fifty object URLs.
 */
export function AssetPhoto({
  linkId,
  alt,
  mimeType,
  className,
}: {
  linkId: string
  alt: string
  mimeType?: string | null
  className?: string
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const isImage = (mimeType ?? '').startsWith('image/')

  useEffect(() => {
    if (!isImage) return
    let revoked = false
    let objectUrl: string | null = null

    assetsApi
      .documentBlob(linkId)
      .then((blob) => {
        if (revoked) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => setFailed(true))

    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [linkId, isImage])

  const box = cn(
    'flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-input border border-border bg-bg-raised',
    className,
  )

  if (!isImage) {
    return (
      <div className={box} aria-label={alt}>
        <FileText className="h-6 w-6 text-text-muted" />
      </div>
    )
  }
  if (failed) {
    return (
      <div className={box} aria-label={`${alt} (preview unavailable)`}>
        <ImageOff className="h-6 w-6 text-text-muted" />
      </div>
    )
  }
  if (!url) {
    return (
      <div className={box}>
        <Spinner />
      </div>
    )
  }
  return (
    <div className={box}>
      <img src={url} alt={alt} className="h-full w-full object-cover" />
    </div>
  )
}
