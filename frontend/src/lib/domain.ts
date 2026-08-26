export function getAppUrl(path = '/login'): string {
  if (typeof window === 'undefined') return path
  const host = window.location.hostname.toLowerCase()
  if (host.startsWith('app.') || host === 'localhost' || host === '127.0.0.1') {
    return path
  }
  const protocol = window.location.protocol
  const port = window.location.port ? `:${window.location.port}` : ''
  const rootDomain = host.replace(/^www\./, '')
  return `${protocol}//app.${rootDomain}${port}${path}`
}

export function isMarketingDomain(): boolean {
  if (typeof window === 'undefined') return false
  const host = window.location.hostname.toLowerCase()
  if (host === 'localhost' || host === '127.0.0.1' || host.startsWith('app.')) {
    return false
  }
  return true
}
