import { describe, it, expect } from 'vitest'
import { GRAPH_THEMES, getGraphTheme } from './theme'

describe('graph themes', () => {
  it('exposes dark and light modes', () => {
    expect(Object.keys(GRAPH_THEMES).sort()).toEqual(['dark', 'light'])
  })

  it('dark mode uses the app emerald-black background', () => {
    expect(getGraphTheme('dark').background).toBe('#0a0e0c')
    expect(getGraphTheme('dark').emissiveMultiplier).toBe(1)
  })

  it('light mode uses warm paper background and reduced emissive', () => {
    const t = getGraphTheme('light')
    expect(t.background).toBe('#f6f7f5')
    expect(t.emissiveMultiplier).toBeLessThan(1)
  })

  it('tag links are gold-tinted in both modes', () => {
    expect(getGraphTheme('dark').linkTag).toContain('224, 181, 102')
    expect(getGraphTheme('light').linkTag).toContain('196, 139, 44')
  })
})
