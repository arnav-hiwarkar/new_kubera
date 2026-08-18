import * as THREE from 'three'
import type { GraphNode } from '../types/graph'

export const DOC_LOD_FULL_DISTANCE = 200
export const DOC_LOD_CUTOFF_DISTANCE = 420

interface CachedTextureEntry {
  texture: THREE.Texture
  aspect: number
}

// In-memory cache for textures to avoid expensive canvas re-renders
const textureCache = new Map<string, CachedTextureEntry>()

export function clearSpriteCache(): void {
  textureCache.forEach((entry) => {
    entry.texture.dispose()
  })
  textureCache.clear()
}

function getNodeCacheKey(node: GraphNode): string {
  if (node.type === 'bucket') {
    return `bucket:${node.name}:${node.color}`
  }
  return `doc:${node.name}:${node.color}:${node.versionNo ?? 1}:${node.status ?? ''}`
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  if (typeof ctx.roundRect === 'function') {
    ctx.beginPath()
    ctx.roundRect(x, y, width, height, radius)
    return
  }
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}

function truncateText(text: string, maxLength = 26): string {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 3)}...`
}

function createTextTexture(node: GraphNode): CachedTextureEntry {
  const DPI = 2
  const isBucket = node.type === 'bucket'
  
  if (typeof document === 'undefined') {
    return { texture: new THREE.Texture(), aspect: 1 }
  }

  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')

  if (!ctx) {
    return { texture: new THREE.Texture(), aspect: 1 }
  }

  const labelText = isBucket ? node.name : truncateText(node.name, 28)
  const versionText = !isBucket && node.versionNo ? `v${node.versionNo}` : null

  // Typography settings
  const fontSize = isBucket ? 14 * DPI : 12 * DPI
  const fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'
  const fontWeight = isBucket ? '700' : '500'
  ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`

  // Measure text
  const textMetrics = ctx.measureText(labelText)
  const textWidth = textMetrics.width || labelText.length * (fontSize * 0.6)

  let versionWidth = 0
  const versionFontSize = 10 * DPI
  if (versionText) {
    ctx.font = `600 ${versionFontSize}px ${fontFamily}`
    const vMetrics = ctx.measureText(versionText)
    versionWidth = (vMetrics.width || versionText.length * (versionFontSize * 0.6)) + 12 * DPI
    // Reset font for main label
    ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`
  }

  // Padding & Dimensions
  const paddingX = isBucket ? 16 * DPI : 10 * DPI
  const paddingY = isBucket ? 8 * DPI : 6 * DPI
  const dotRadius = isBucket ? 5 * DPI : 3.5 * DPI
  const dotGap = 8 * DPI

  const totalContentWidth = dotRadius * 2 + dotGap + textWidth + (versionWidth ? 8 * DPI + versionWidth : 0)
  const width = Math.ceil(totalContentWidth + paddingX * 2)
  const height = Math.ceil(fontSize + paddingY * 2)
  const radius = height / 2

  canvas.width = width
  canvas.height = height

  // Set crisp context rendering
  ctx.textBaseline = 'middle'

  // Draw Background Pill
  drawRoundedRect(ctx, 1 * DPI, 1 * DPI, width - 2 * DPI, height - 2 * DPI, radius)
  ctx.fillStyle = isBucket ? 'rgba(15, 23, 42, 0.92)' : 'rgba(15, 23, 42, 0.82)'
  ctx.fill()

  // Border Stroke
  if (isBucket) {
    ctx.lineWidth = 2 * DPI
    ctx.strokeStyle = node.color || '#38BDF8'
  } else {
    ctx.lineWidth = 1 * DPI
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)'
  }
  ctx.stroke()

  // Draw Color Dot Indicator
  const dotCenterX = paddingX + dotRadius
  const dotCenterY = height / 2
  ctx.beginPath()
  ctx.arc(dotCenterX, dotCenterY, dotRadius, 0, Math.PI * 2)
  ctx.fillStyle = node.color || '#94A3B8'
  ctx.fill()

  // Draw Text Label
  const textX = dotCenterX + dotRadius + dotGap
  const textY = height / 2 + (DPI * 0.5) // Slight optical vertical alignment
  ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`
  ctx.fillStyle = isBucket ? '#FFFFFF' : '#F1F5F9'
  ctx.fillText(labelText, textX, textY)

  // Draw Version Badge if present
  if (versionText && versionWidth > 0) {
    const badgeX = textX + textWidth + 8 * DPI
    const badgeY = height / 2 - (versionFontSize / 2 + 2 * DPI)
    const badgeHeight = versionFontSize + 4 * DPI
    const badgeRadius = badgeHeight / 2

    drawRoundedRect(ctx, badgeX, badgeY, versionWidth, badgeHeight, badgeRadius)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)'
    ctx.fill()

    ctx.font = `600 ${versionFontSize}px ${fontFamily}`
    ctx.fillStyle = '#94A3B8'
    ctx.fillText(versionText, badgeX + 6 * DPI, height / 2 + (DPI * 0.5))
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.needsUpdate = true

  return {
    texture,
    aspect: width / height,
  }
}

function getOrCreateTexture(node: GraphNode): CachedTextureEntry {
  const cacheKey = getNodeCacheKey(node)
  const cached = textureCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const created = createTextTexture(node)
  textureCache.set(cacheKey, created)
  return created
}

export function createNodeSprite(node: GraphNode): THREE.Sprite {
  const { texture, aspect } = getOrCreateTexture(node)
  
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    opacity: 1.0,
  })

  const sprite = new THREE.Sprite(material)
  
  // Scale sprite in 3D world space
  const isBucket = node.type === 'bucket'
  const spriteHeight = isBucket ? 8 : 5
  const spriteWidth = spriteHeight * aspect
  
  sprite.scale.set(spriteWidth, spriteHeight, 1)
  
  // Position slightly above the sphere node center
  sprite.center.set(0.5, -0.3)
  
  // Attach metadata to sprite userData
  sprite.userData = {
    nodeId: node.id,
    isBucket,
    node,
  }

  return sprite
}

export function updateSpriteLOD(
  sprite: THREE.Sprite,
  distance: number,
  isBucket: boolean,
): void {
  if (!sprite || !sprite.material) return

  if (isBucket) {
    // Bucket landmark labels remain permanently visible
    sprite.visible = true
    sprite.material.opacity = 1.0
    return
  }

  if (distance >= DOC_LOD_CUTOFF_DISTANCE) {
    sprite.visible = false
    sprite.material.opacity = 0
  } else if (distance <= DOC_LOD_FULL_DISTANCE) {
    sprite.visible = true
    sprite.material.opacity = 1.0
  } else {
    // Smooth linear fade in mid-distance zone
    const factor = (DOC_LOD_CUTOFF_DISTANCE - distance) / (DOC_LOD_CUTOFF_DISTANCE - DOC_LOD_FULL_DISTANCE)
    const opacity = Math.max(0, Math.min(1, factor))
    sprite.visible = opacity > 0.001
    sprite.material.opacity = opacity
  }
}
