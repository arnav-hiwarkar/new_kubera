import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ExplainLink } from './ExplainLink'
import { DerivedRow } from '@/pages/company/assets/tabs/SectionShell'

describe('ExplainLink', () => {
  it('reads as an invitation to see the working', () => {
    const onClick = vi.fn()
    render(<ExplainLink onClick={onClick} />)
    const button = screen.getByRole('button', { name: /see the calculation/i })
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalled()
  })

  it('accepts a shorter label for tight spots', () => {
    render(<ExplainLink onClick={vi.fn()} label="See working" />)
    expect(screen.getByRole('button', { name: /see working/i })).toBeTruthy()
  })
})

describe('DerivedRow', () => {
  it('offers no explain affordance by default', () => {
    render(<DerivedRow label="Depreciable base" value="₹95,000.00" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('deep-links into the calculation when given a handler', () => {
    const onExplain = vi.fn()
    render(<DerivedRow label="Depreciable base" value="₹95,000.00" onExplain={onExplain} />)
    fireEvent.click(screen.getByRole('button', { name: /how .*depreciable base.* calculated/i }))
    expect(onExplain).toHaveBeenCalled()
  })
})
