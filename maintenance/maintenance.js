const COUNTDOWN_SECONDS = 10
const POLL_INTERVAL_MS = 1000
const FINAL_RETRY_MS = 2000

export function parseState(value) {
  if (!value || typeof value !== 'object') return { mode: 'active' }
  if (value.mode !== 'closing' || typeof value.ends_at !== 'string') return { mode: 'active' }
  const endsAt = Date.parse(value.ends_at)
  return Number.isFinite(endsAt) ? { mode: 'closing', endsAt } : { mode: 'active' }
}

export function serverOffsetFromDate(dateHeader, clientNow = Date.now()) {
  const serverNow = Date.parse(dateHeader || '')
  return Number.isFinite(serverNow) ? serverNow - clientNow : 0
}

export function remainingSeconds(endsAt, now = Date.now(), serverOffset = 0) {
  return Math.max(0, Math.ceil((endsAt - (now + serverOffset)) / 1000))
}

export function progressFor(seconds) {
  return Math.max(0, Math.min(1, seconds / COUNTDOWN_SECONDS))
}

export function reloadDelay(endsAt, now = Date.now(), serverOffset = 0) {
  const untilDeadline = endsAt - (now + serverOffset)
  return Math.max(FINAL_RETRY_MS, untilDeadline + 350)
}

const elements = typeof document === 'undefined' ? null : {
  statusText: document.querySelector('[data-status-text]'),
  message: document.querySelector('[data-message]'),
  live: document.querySelector('[data-live]'),
  coreMark: document.querySelector('[data-core-mark]'),
  countdown: document.querySelector('[data-countdown]'),
  ring: document.querySelector('.ring-progress'),
}

let finalRetryTimer
let closingSeen = false

function showActive() {
  if (!elements) return
  clearTimeout(finalRetryTimer)
  finalRetryTimer = undefined
  closingSeen = false
  elements.statusText.textContent = 'Scheduled maintenance'
  elements.message.textContent = 'We are making a few careful improvements. Your workspace and data remain safe while we finish up.'
  elements.live.textContent = ''
  elements.coreMark.hidden = false
  elements.countdown.hidden = true
  elements.ring.style.strokeDashoffset = '326.73'
}

function showClosing(seconds) {
  if (!elements) return
  elements.statusText.textContent = 'Ready to return'
  elements.message.textContent = 'The finishing touches are complete. Kubera is reopening securely.'
  elements.coreMark.hidden = true
  elements.countdown.hidden = false

  if (seconds > 0) {
    elements.countdown.textContent = String(seconds)
    elements.live.textContent = `Returning to Kubera in ${seconds} second${seconds === 1 ? '' : 's'}.`
    elements.ring.style.strokeDashoffset = String(326.73 * (1 - progressFor(seconds)))
    return
  }

  elements.countdown.textContent = '0'
  elements.live.textContent = 'Final checks…'
  elements.ring.style.strokeDashoffset = '0'
}

function scheduleReturn(endsAt, now, serverOffset) {
  if (finalRetryTimer) return
  closingSeen = true
  finalRetryTimer = setTimeout(
    () => window.location.reload(),
    reloadDelay(endsAt, now, serverOffset),
  )
}

async function pollState() {
  try {
    const response = await fetch('/maintenance-state.json', { cache: 'no-store' })
    if (!response.ok) {
      if (!closingSeen) showActive()
      return
    }
    const state = parseState(await response.json())
    if (state.mode === 'active') {
      showActive()
      return
    }
    const offset = serverOffsetFromDate(response.headers.get('Date'))
    const now = Date.now()
    scheduleReturn(state.endsAt, now, offset)
    showClosing(remainingSeconds(state.endsAt, now, offset))
  } catch {
    if (!closingSeen) showActive()
  }
}

if (elements) {
  showActive()
  pollState()
  setInterval(pollState, POLL_INTERVAL_MS)
}
