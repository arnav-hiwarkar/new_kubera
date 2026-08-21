export type GraphThemeMode = 'light' | 'dark'

export interface GraphTheme {
  mode: GraphThemeMode
  background: string
  fogNear: number
  fogFar: number
  linkBucketDoc: string
  linkTag: string
  particle: string
  selectionRing: string
  bucketRing: string
  spriteText: string
  spriteBgBucket: string
  spriteBgDoc: string
  spriteBorderDoc: string
  emissiveMultiplier: number
  ambientIntensity: number
  directionalIntensity: number
}

export const GRAPH_THEMES: Record<GraphThemeMode, GraphTheme> = {
  dark: {
    mode: 'dark',
    background: '#0a0e0c',
    fogNear: 220,
    fogFar: 900,
    linkBucketDoc: 'rgba(31, 185, 140, 0.28)',
    linkTag: 'rgba(224, 181, 102, 0.18)',
    particle: '#1fb98c',
    selectionRing: '#1fb98c',
    bucketRing: '#e0b566',
    spriteText: '#edf2ee',
    spriteBgBucket: 'rgba(10, 16, 13, 0.92)',
    spriteBgDoc: 'rgba(10, 16, 13, 0.82)',
    spriteBorderDoc: 'rgba(237, 242, 238, 0.18)',
    emissiveMultiplier: 1,
    ambientIntensity: 0.7,
    directionalIntensity: 0.8,
  },
  light: {
    mode: 'light',
    background: '#f6f7f5',
    fogNear: 260,
    fogFar: 1100,
    linkBucketDoc: 'rgba(15, 157, 118, 0.35)',
    linkTag: 'rgba(196, 139, 44, 0.25)',
    particle: '#0f9d76',
    selectionRing: '#0f9d76',
    bucketRing: '#c48b2c',
    spriteText: '#10201a',
    spriteBgBucket: 'rgba(255, 255, 255, 0.94)',
    spriteBgDoc: 'rgba(255, 255, 255, 0.9)',
    spriteBorderDoc: 'rgba(16, 32, 26, 0.18)',
    emissiveMultiplier: 0.45,
    ambientIntensity: 1.1,
    directionalIntensity: 0.9,
  },
}

export function getGraphTheme(mode: GraphThemeMode): GraphTheme {
  return GRAPH_THEMES[mode]
}
