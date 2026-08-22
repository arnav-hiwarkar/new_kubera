import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CategoryPicker } from './CategoryPicker'

vi.mock('@/api/hooks/assetMasters', () => ({
  useCategoryTree: () => ({
    isLoading: false,
    tree: [
      { parent: { id: 'b', name: 'Buildings' }, children: [
        { id: 'b1', name: 'RCC frame structure buildings',
          default_useful_life_months: 720, default_dep_method: 'slm',
          default_it_block_code: 'BLD-10', default_it_block_rate: 10 },
        { id: 'b2', name: 'Factory buildings' },
      ]},
      { parent: { id: 'o', name: 'Office equipment' }, children: [
        { id: 'o1', name: 'Office equipment' },
      ]},
    ],
  }),
}))

describe('CategoryPicker', () => {
  it('keeps a multi-child category selected while awaiting subcategory choice', () => {
    const onChange = vi.fn()
    render(<CategoryPicker value="" onChange={onChange} />)

    const category = screen.getByLabelText('Category') as HTMLSelectElement
    fireEvent.change(category, { target: { value: 'b' } })

    // Regression: selection used to snap back to the placeholder.
    expect(category.value).toBe('b')
    expect(onChange).toHaveBeenCalledWith('')
    expect((screen.getByLabelText('Subcategory') as HTMLSelectElement).disabled).toBe(false)
  })

  it('auto-selects the only child of a single-child category', () => {
    const onChange = vi.fn()
    render(<CategoryPicker value="" onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'o' } })
    expect(onChange).toHaveBeenCalledWith('o1')
  })
})
