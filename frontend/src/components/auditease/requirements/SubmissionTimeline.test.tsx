import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SubmissionTimeline } from './SubmissionTimeline'
import type { RequirementSubmissionOut } from '@/api/types'

describe('SubmissionTimeline', () => {
  const submissions: RequirementSubmissionOut[] = [
    {
      id: 'sub-1',
      requirement_id: 'req-1',
      round_number: 1,
      text_answer: 'First round answer',
      created_at: '2026-01-01T10:00:00Z',
      responded_by_name: 'Alice',
      documents: [
        {
          document_id: 'doc-1',
          filename: 'doc1.pdf',
          size_bytes: 1024,
          mime_type: 'application/pdf',
        },
      ],
    },
    {
      id: 'sub-2',
      requirement_id: 'req-1',
      round_number: 2,
      text_answer: 'Second round answer',
      created_at: '2026-01-02T10:00:00Z',
      responded_by_name: 'Bob',
      documents: [],
    },
  ]

  it('renders empty state when no submissions', () => {
    render(<SubmissionTimeline submissions={[]} />)
    expect(screen.getByText(/no responses submitted yet/i)).toBeInTheDocument()
  })

  it('renders submissions in reverse chronological order (latest round first)', () => {
    render(<SubmissionTimeline submissions={submissions} />)
    expect(screen.getByText('Submission History (2 rounds)')).toBeInTheDocument()

    const roundBadges = screen.getAllByText(/Round \d/)
    expect(roundBadges).toHaveLength(2)
    // The first round chip in the list should be Round 2 (latest)
    expect(roundBadges[0]).toHaveTextContent('Round 2')
    expect(screen.getByText('Latest')).toBeInTheDocument()

    expect(screen.getByText('Second round answer')).toBeInTheDocument()
    expect(screen.getByText('First round answer')).toBeInTheDocument()
    expect(screen.getByText('doc1.pdf')).toBeInTheDocument()
  })

  it('triggers download when document chip download button is clicked', () => {
    const onDownload = vi.fn()
    render(<SubmissionTimeline submissions={submissions} onDownloadDoc={onDownload} />)
    const downloadBtn = screen.getByLabelText('Download doc1.pdf')
    fireEvent.click(downloadBtn)
    expect(onDownload).toHaveBeenCalledWith('doc-1', 'doc1.pdf')
  })
})
