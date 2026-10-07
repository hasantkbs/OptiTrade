import { Dialog } from '../../components/ui/Dialog'
import { Button } from '../../components/ui/Button'
import { apiErrorMessage } from '../../api/client'
import { SymbolSearch } from '../market/SymbolSearch'
import { useAddWatchlistItem } from './hooks'
import styles from './AddSymbolDialog.module.css'

interface AddSymbolDialogProps {
  open: boolean
  watchlistId: number | undefined
  onClose: () => void
}

/** Lets a user add a symbol to their watchlist directly, instead of the
 * only previous path (open an asset's detail page, use "Add to
 * watchlist" there). */
export function AddSymbolDialog({ open, watchlistId, onClose }: AddSymbolDialogProps) {
  const addItem = useAddWatchlistItem(watchlistId)

  function handleClose() {
    addItem.reset()
    onClose()
  }

  function handleSelect(symbol: string) {
    addItem.mutate(symbol, { onSuccess: handleClose })
  }

  return (
    <Dialog open={open} title="Add symbol" onClose={handleClose}>
      <div className={styles.body}>
        <SymbolSearch onSelect={handleSelect} />

        {addItem.isError ? (
          <p className={styles.error} role="alert">
            {apiErrorMessage(addItem.error)}
          </p>
        ) : null}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" size="sm" onClick={handleClose}>
            Close
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
