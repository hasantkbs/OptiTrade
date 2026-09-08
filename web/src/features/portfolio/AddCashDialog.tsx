import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/ui/Dialog'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { apiErrorMessage } from '../../api/client'
import { useDeposit } from './hooks'
import styles from './AddCashDialog.module.css'

interface AddCashDialogProps {
  portfolioId: number | undefined
  /** The portfolio's own real base_currency (Portfolio.base_currency) -
   * pre-fills the field so a currency is never invented, only ever the
   * one the portfolio already actually uses. */
  baseCurrency: string
  open: boolean
  onClose: () => void
}

interface FieldErrors {
  amount?: string
}

/**
 * POST /portfolios/{id}/deposit (portfolio/models.py::DepositRequest) -
 * cash_balance is never set locally; the backend replays it from the
 * transaction ledger this appends to (GET /dashboard/portfolios/{id}).
 * Withdrawal is deliberately out of scope for this dialog.
 */
export function AddCashDialog({ portfolioId, baseCurrency, open, onClose }: AddCashDialogProps) {
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState(baseCurrency)
  const [notes, setNotes] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const deposit = useDeposit(portfolioId)

  function handleClose() {
    setAmount('')
    setCurrency(baseCurrency)
    setNotes('')
    setFieldErrors({})
    deposit.reset()
    onClose()
  }

  function validate(): FieldErrors {
    const errors: FieldErrors = {}
    const amountValue = Number(amount)
    if (!amount.trim()) {
      errors.amount = 'Amount is required.'
    } else if (!Number.isFinite(amountValue) || amountValue <= 0) {
      errors.amount = 'Amount must be a number greater than 0.'
    }
    return errors
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0 || portfolioId === undefined) return

    const trimmedCurrency = currency.trim().toUpperCase()
    const trimmedNotes = notes.trim()
    deposit.mutate(
      {
        amount: Number(amount),
        currency: trimmedCurrency ? trimmedCurrency : undefined,
        notes: trimmedNotes ? trimmedNotes : undefined,
      },
      { onSuccess: handleClose },
    )
  }

  return (
    <Dialog open={open} title="Add cash" onClose={handleClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Amount"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          error={fieldErrors.amount}
          placeholder="e.g. 10000"
          inputMode="decimal"
          autoFocus
        />
        <Input
          label="Currency"
          value={currency}
          onChange={(event) => setCurrency(event.target.value.toUpperCase())}
          placeholder={baseCurrency}
        />
        <Input
          label="Notes (optional)"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="e.g. Initial capital"
        />

        {deposit.isError ? (
          <p className={styles.error} role="alert">
            {apiErrorMessage(deposit.error)}
          </p>
        ) : null}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" isLoading={deposit.isPending} disabled={deposit.isPending}>
            Add cash
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
