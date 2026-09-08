import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { apiErrorMessage } from '../../api/client'
import { useAddPosition } from './hooks'
import styles from './AddPositionDialog.module.css'

interface AddPositionDialogProps {
  portfolioId: number | undefined
  open: boolean
  onClose: () => void
}

interface FieldErrors {
  symbol?: string
  quantity?: string
  price?: string
}

const MAX_SYMBOL_LENGTH = 32 // matches portfolio_transactions.symbol VARCHAR(32)

/**
 * POST /portfolios/{id}/buy (portfolio/models.py::TradeRequest) - only
 * `symbol`/`quantity`/`price` are collected; `fee`/`tax`/`notes` are
 * optional on the backend and omitted here to keep the primary flow to
 * exactly the three fields this task asks for. `price` is the trade's
 * own historical entry price, entered by the user - the backend
 * resolves the *current* market price separately, only for valuation
 * (GET /dashboard/portfolios/{id}), never from this form.
 */
export function AddPositionDialog({ portfolioId, open, onClose }: AddPositionDialogProps) {
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const addPosition = useAddPosition(portfolioId)

  function handleClose() {
    setSymbol('')
    setQuantity('')
    setPrice('')
    setFieldErrors({})
    addPosition.reset()
    onClose()
  }

  function validate(): FieldErrors {
    const errors: FieldErrors = {}
    const trimmedSymbol = symbol.trim()
    if (!trimmedSymbol) {
      errors.symbol = 'Symbol is required.'
    } else if (trimmedSymbol.length > MAX_SYMBOL_LENGTH) {
      errors.symbol = `Symbol must be ${MAX_SYMBOL_LENGTH} characters or fewer.`
    }

    const quantityValue = Number(quantity)
    if (!quantity.trim()) {
      errors.quantity = 'Quantity is required.'
    } else if (Number.isNaN(quantityValue) || quantityValue <= 0) {
      errors.quantity = 'Quantity must be a number greater than 0.'
    }

    const priceValue = Number(price)
    if (!price.trim()) {
      errors.price = 'Entry price is required.'
    } else if (Number.isNaN(priceValue) || priceValue <= 0) {
      errors.price = 'Entry price must be a number greater than 0.'
    }

    return errors
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0 || portfolioId === undefined) return

    addPosition.mutate(
      { symbol: symbol.trim().toUpperCase(), quantity: Number(quantity), price: Number(price) },
      { onSuccess: handleClose },
    )
  }

  return (
    <Dialog open={open} title="Add position" onClose={handleClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Symbol"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          error={fieldErrors.symbol}
          placeholder="e.g. AAPL"
          autoComplete="off"
          autoFocus
        />
        <Input
          label="Quantity"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          error={fieldErrors.quantity}
          placeholder="e.g. 10"
          inputMode="decimal"
        />
        <Input
          label="Entry price"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          error={fieldErrors.price}
          placeholder="e.g. 210.00"
          inputMode="decimal"
        />
        <p className={styles.hint}>
          The price you actually paid per share - not today&apos;s market price. Current price is looked up
          automatically once the position is added.
        </p>

        {addPosition.isError ? (
          <p className={styles.error} role="alert">
            {apiErrorMessage(addPosition.error)}
          </p>
        ) : null}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" isLoading={addPosition.isPending} disabled={addPosition.isPending}>
            Add position
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
