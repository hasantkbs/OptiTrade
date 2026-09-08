import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Dialog } from './Dialog'

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(
      <Dialog open={false} title="Create thing" onClose={vi.fn()}>
        content
      </Dialog>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the title and children when open', () => {
    render(
      <Dialog open title="Create thing" onClose={vi.fn()}>
        <p>form goes here</p>
      </Dialog>,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Create thing')).toBeInTheDocument()
    expect(screen.getByText('form goes here')).toBeInTheDocument()
  })

  it('calls onClose when the overlay is clicked, but not when the dialog itself is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <Dialog open title="Create thing" onClose={onClose}>
        <p>form goes here</p>
      </Dialog>,
    )
    await user.click(screen.getByText('form goes here'))
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <Dialog open title="Create thing" onClose={onClose}>
        content
      </Dialog>,
    )
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
