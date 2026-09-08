import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { apiErrorMessage } from '../../api/client'
import { useCreateWatchlist } from './hooks'
import styles from './CreateWatchlistDialog.module.css'

interface CreateWatchlistDialogProps {
  open: boolean
  onClose: () => void
}

/** POST /watchlists only takes `name` (watchlist/models.py::CreateWatchlistRequest). */
export function CreateWatchlistDialog({ open, onClose }: CreateWatchlistDialogProps) {
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState<string | undefined>(undefined)
  const createWatchlist = useCreateWatchlist()

  function handleClose() {
    setName('')
    setNameError(undefined)
    createWatchlist.reset()
    onClose()
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setNameError('Watchlist name is required.')
      return
    }
    setNameError(undefined)
    createWatchlist.mutate({ name: name.trim() }, { onSuccess: handleClose })
  }

  return (
    <Dialog open={open} title="Create watchlist" onClose={handleClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Watchlist name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={nameError}
          autoFocus
        />

        {createWatchlist.isError ? (
          <p className={styles.error} role="alert">
            {apiErrorMessage(createWatchlist.error)}
          </p>
        ) : null}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" isLoading={createWatchlist.isPending}>
            Create watchlist
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
