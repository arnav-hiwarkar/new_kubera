import test from 'node:test'
import assert from 'node:assert/strict'

import {
  parseState,
  progressFor,
  reloadDelay,
  remainingSeconds,
  serverOffsetFromDate,
} from './maintenance.js'

test('active and malformed states remain safely active', () => {
  assert.deepEqual(parseState({ mode: 'active' }), { mode: 'active' })
  assert.deepEqual(parseState({ mode: 'closing', ends_at: 'bad' }), { mode: 'active' })
  assert.deepEqual(parseState(null), { mode: 'active' })
})

test('closing state parses its absolute deadline', () => {
  const state = parseState({ mode: 'closing', ends_at: '2026-08-03T12:00:10.000Z' })
  assert.equal(state.mode, 'closing')
  assert.equal(state.endsAt, Date.parse('2026-08-03T12:00:10.000Z'))
})

test('countdown is synchronized for initial and midway visitors', () => {
  const endsAt = Date.parse('2026-08-03T12:00:10.000Z')
  assert.equal(remainingSeconds(endsAt, Date.parse('2026-08-03T12:00:00.000Z')), 10)
  assert.equal(remainingSeconds(endsAt, Date.parse('2026-08-03T12:00:06.200Z')), 4)
  assert.equal(remainingSeconds(endsAt, Date.parse('2026-08-03T12:00:11.000Z')), 0)
})

test('server Date offset compensates for a browser clock difference', () => {
  const clientNow = Date.parse('2026-08-03T11:59:55.000Z')
  const offset = serverOffsetFromDate('Mon, 03 Aug 2026 12:00:00 GMT', clientNow)
  const endsAt = Date.parse('2026-08-03T12:00:10.000Z')
  assert.equal(offset, 5000)
  assert.equal(remainingSeconds(endsAt, clientNow, offset), 10)
})

test('progress is clamped to the ten-second window', () => {
  assert.equal(progressFor(10), 1)
  assert.equal(progressFor(5), 0.5)
  assert.equal(progressFor(0), 0)
  assert.equal(progressFor(50), 1)
})

test('reload is scheduled for the shared deadline with a controlled retry floor', () => {
  const now = Date.parse('2026-08-03T12:00:00.000Z')
  assert.equal(reloadDelay(now + 10_000, now), 10_350)
  assert.equal(reloadDelay(now - 1_000, now), 2000)
})
