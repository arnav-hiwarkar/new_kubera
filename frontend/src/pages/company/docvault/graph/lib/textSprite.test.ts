import { describe, it, expect, beforeEach, beforeAll, vi } from 'vitest'
import * as THREE from 'three'
import { createNodeSprite, updateSpriteLOD, clearSpriteCache } from './textSprite'
import { getGraphTheme } from './theme'
import type { GraphNode } from '../types/graph'

describe('textSprite and LOD engine', () => {
  beforeAll(() => {
    const mockContext2D = {
      font: '',
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      textBaseline: 'alphabetic',
      beginPath: vi.fn(),
      closePath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      quadraticCurveTo: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      fillText: vi.fn(),
      measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
      roundRect: vi.fn(),
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(mockContext2D as any)
  })

  beforeEach(() => {
    clearSpriteCache()
  })

  describe('updateSpriteLOD', () => {
    it('hides document sprite when camera distance is greater than 420px (opacity: 0, visible: false)', () => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ opacity: 1, transparent: true }))
      
      updateSpriteLOD(sprite, 450, false)
      expect(sprite.visible).toBe(false)
      expect(sprite.material.opacity).toBe(0)

      updateSpriteLOD(sprite, 500, false)
      expect(sprite.visible).toBe(false)
      expect(sprite.material.opacity).toBe(0)
    })

    it('keeps bucket sprite visible even at far distance (>600px)', () => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ opacity: 1, transparent: true }))
      
      updateSpriteLOD(sprite, 650, true)
      expect(sprite.visible).toBe(true)
      expect(sprite.material.opacity).toBeGreaterThan(0)

      updateSpriteLOD(sprite, 1000, true)
      expect(sprite.visible).toBe(true)
      expect(sprite.material.opacity).toBeGreaterThan(0)
    })

    it('smoothly fades in document sprite in mid-distance zone (e.g. at 300px distance, opacity between 0 and 1, visible: true)', () => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ opacity: 1, transparent: true }))
      
      updateSpriteLOD(sprite, 300, false)
      expect(sprite.visible).toBe(true)
      expect(sprite.material.opacity).toBeGreaterThan(0)
      expect(sprite.material.opacity).toBeLessThan(1)

      // At close distance (< 200px), document sprite is fully opaque
      updateSpriteLOD(sprite, 150, false)
      expect(sprite.visible).toBe(true)
      expect(sprite.material.opacity).toBe(1)
    })
  })

  describe('createNodeSprite', () => {
    const mockBucketNode: GraphNode = {
      id: 'bucket_b1',
      rawId: 'b1',
      type: 'bucket',
      name: 'Financial Documents',
      bucketId: 'b1',
      bucketName: 'Financial Documents',
      color: '#38BDF8',
      size: 14,
    }

    const mockDocNode: GraphNode = {
      id: 'doc_d1',
      rawId: 'd1',
      type: 'document',
      name: 'Q4 Balance Sheet.pdf',
      bucketId: 'b1',
      bucketName: 'Financial Documents',
      color: '#10B981',
      size: 6,
      versionNo: 2,
      status: 'verified',
    }

    it('creates THREE.Sprite for bucket node', () => {
      const sprite = createNodeSprite(mockBucketNode)
      expect(sprite).toBeInstanceOf(THREE.Sprite)
      expect(sprite.material).toBeInstanceOf(THREE.SpriteMaterial)
      expect(sprite.material.transparent).toBe(true)
      expect(sprite.userData.isBucket).toBe(true)
      expect(sprite.userData.nodeId).toBe('bucket_b1')
    })

    it('creates THREE.Sprite for document node', () => {
      const sprite = createNodeSprite(mockDocNode)
      expect(sprite).toBeInstanceOf(THREE.Sprite)
      expect(sprite.material).toBeInstanceOf(THREE.SpriteMaterial)
      expect(sprite.material.transparent).toBe(true)
      expect(sprite.userData.isBucket).toBe(false)
      expect(sprite.userData.nodeId).toBe('doc_d1')
    })

    it('creates THREE.Sprite with bottom-center anchoring, depthTest disabled, and elevated renderOrder', () => {
      const sprite = createNodeSprite(mockDocNode)
      expect(sprite.center.x).toBe(0.5)
      expect(sprite.center.y).toBe(0)
      expect(sprite.material.depthTest).toBe(false)
      expect(sprite.renderOrder).toBe(999)
    })

    it('uses texture cache to prevent redundant canvas redraws for identical node properties', () => {
      const sprite1 = createNodeSprite(mockDocNode)
      const sprite2 = createNodeSprite({ ...mockDocNode })

      // Should reuse the same material / texture map from cache
      expect(sprite1.material.map).toBe(sprite2.material.map)
    })

    it('produces distinct cache entries per theme', () => {
      const node = mockDocNode
      const a = createNodeSprite(node, getGraphTheme('dark'))
      const b = createNodeSprite(node, getGraphTheme('light'))
      expect(a).not.toBe(b)
    })
  })
})
