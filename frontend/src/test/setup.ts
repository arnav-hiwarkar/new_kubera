import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Newer Node runtimes expose an unconfigured global localStorage property that
// can shadow jsdom's implementation. Provide the standard in-memory behavior
// tests expect when that Node property resolves to undefined.
if (!globalThis.localStorage) {
  const entries = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return entries.size
    },
    clear: () => entries.clear(),
    getItem: (key) => entries.get(key) ?? null,
    key: (index) => [...entries.keys()][index] ?? null,
    removeItem: (key) => {
      entries.delete(key)
    },
    setItem: (key, value) => {
      entries.set(key, String(value))
    },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storage,
  })
}

afterEach(() => {
  cleanup()
  localStorage.clear()
})
