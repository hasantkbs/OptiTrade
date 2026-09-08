import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { apiErrorMessage } from '../../api/client'
import { useCreatePortfolio } from './hooks'
import styles from './CreatePortfolioDialog.module.css'

interface CreatePortfolioDialogProps {
  open: boolean
  onClose: () => void
}

/**
 * POST /portfolios only takes `name` (portfolio/models.py::
 * CreatePortfolioRequest - `base_currency` defaults server-side to
 * PortfolioConfig.default_base_currency when omitted, so it is never
 * sent from here rather than guessing a currency).
 */
export function CreatePortfolioDialog({ open, onClose }: CreatePortfolioDialogProps) {
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState<string | undefined>(undefined)
  const createPortfolio = useCreatePortfolio()

  function handleClose() {
    setName('')
    setNameError(undefined)
    createPortfolio.reset()
    onClose()
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setNameError('Portfolio name is required.')
      return
    }
    setNameError(undefined)
    createPortfolio.mutate({ name: name.trim() }, { onSuccess: handleClose })
  }

  return (
    <Dialog open={open} title="Create portfolio" onClose={handleClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Portfolio name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={nameError}
          autoFocus
        />

        {createPortfolio.isError ? (
          <p className={styles.error} role="alert">
            {apiErrorMessage(createPortfolio.error)}
          </p>
        ) : null}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" isLoading={createPortfolio.isPending}>
            Create portfolio
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
