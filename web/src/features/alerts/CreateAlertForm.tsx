import { useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { useCreateAlert } from './hooks'
import { ALERT_CATEGORY_LABEL, alertTypesForCategory, type AlertTypeConfig } from './alertTypes'
import { apiErrorMessage } from '../../api/client'
import type { AlertCategory, AlertType } from '../../api/types'
import styles from './CreateAlertForm.module.css'

const CATEGORIES: AlertCategory[] = ['price', 'technical', 'decision', 'news']

function firstType(category: AlertCategory): AlertType {
  return alertTypesForCategory(category)[0].type
}

/**
 * Builds a real CreateAlertRequest (watchlist/models.py::
 * CreateAlertRequest) entirely from `ALERT_TYPE_CONFIG` - the field set
 * adapts per alert type using the backend's actual required/optional
 * parameters (WEB STEP 6 audit of price_alerts.py/technical_alerts.py/
 * alert_engine.py/news_alerts.py/portfolio_alerts.py). Client-side
 * validation only catches obvious input errors (missing symbol,
 * missing required threshold, non-numeric values) - the backend
 * remains authoritative for everything else.
 */
export function CreateAlertForm() {
  const [category, setCategory] = useState<AlertCategory>('price')
  const [type, setType] = useState<AlertType>(firstType('price'))
  const [symbol, setSymbol] = useState('')
  const [paramValues, setParamValues] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const createAlert = useCreateAlert()

  const typeConfig = alertTypesForCategory(category).find((config) => config.type === type) as AlertTypeConfig

  function handleCategoryChange(nextCategory: AlertCategory) {
    setCategory(nextCategory)
    setType(firstType(nextCategory))
    setParamValues({})
    setErrors({})
    createAlert.reset()
  }

  function handleTypeChange(nextType: AlertType) {
    setType(nextType)
    setParamValues({})
    setErrors({})
    createAlert.reset()
  }

  function validate(): boolean {
    const nextErrors: Record<string, string> = {}

    if (typeConfig.symbol === 'required' && !symbol.trim()) {
      nextErrors.symbol = 'Symbol is required for this alert type.'
    }
    for (const field of typeConfig.parameters) {
      const raw = paramValues[field.key]?.trim()
      if (field.required && !raw) {
        nextErrors[field.key] = `${field.label} is required.`
      } else if (raw && Number.isNaN(Number(raw))) {
        nextErrors[field.key] = `${field.label} must be a number.`
      }
    }

    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!validate() || createAlert.isPending) return

    const parameters: Record<string, number> = {}
    for (const field of typeConfig.parameters) {
      const raw = paramValues[field.key]?.trim()
      if (raw) parameters[field.key] = Number(raw)
    }

    createAlert.mutate(
      {
        category: typeConfig.category,
        alert_type: typeConfig.type,
        parameters,
        symbol: typeConfig.symbol !== 'none' && symbol.trim() ? symbol.trim().toUpperCase() : undefined,
      },
      {
        onSuccess: () => {
          setSymbol('')
          setParamValues({})
        },
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Create alert</CardTitle>
          <CardSubtitle>Evaluated by the backend's Alert Engine, not calculated here</CardSubtitle>
        </div>
      </CardHeader>

      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="alert-category">
            Category
          </label>
          <select
            id="alert-category"
            className={styles.select}
            value={category}
            onChange={(event) => handleCategoryChange(event.target.value as AlertCategory)}
          >
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {ALERT_CATEGORY_LABEL[cat]}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="alert-type">
            Alert type
          </label>
          <select id="alert-type" className={styles.select} value={type} onChange={(event) => handleTypeChange(event.target.value as AlertType)}>
            {alertTypesForCategory(category).map((config) => (
              <option key={config.type} value={config.type}>
                {config.label}
              </option>
            ))}
          </select>
        </div>

        {typeConfig.symbol !== 'none' ? (
          <Input
            label={typeConfig.symbol === 'required' ? 'Symbol' : 'Symbol (optional)'}
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            placeholder="e.g. AAPL"
            error={errors.symbol}
          />
        ) : null}

        {typeConfig.parameters.map((field) => (
          <Input
            key={field.key}
            label={field.required ? field.label : `${field.label} (optional)`}
            value={paramValues[field.key] ?? ''}
            onChange={(event) => setParamValues((prev) => ({ ...prev, [field.key]: event.target.value }))}
            placeholder={field.hint}
            inputMode="decimal"
            error={errors[field.key]}
          />
        ))}

        {typeConfig.parameters.length === 0 ? <p className={styles.note}>This alert type takes no additional parameters.</p> : null}

        {createAlert.isError ? <p className={styles.error}>{apiErrorMessage(createAlert.error)}</p> : null}
        {createAlert.isSuccess ? <p className={styles.success}>Alert created.</p> : null}

        <Button type="submit" isLoading={createAlert.isPending} disabled={createAlert.isPending}>
          Create alert
        </Button>
      </form>
    </Card>
  )
}
