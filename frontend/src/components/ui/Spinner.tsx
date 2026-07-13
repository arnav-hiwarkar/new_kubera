import { cn } from '@/lib/cn'

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn('animate-spin text-text-muted', className)}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function FullPageSpinner() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-bg-primary">
      <Spinner className="h-8 w-8" />
    </div>
  )
}
