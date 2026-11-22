import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ApiError } from '../services/apiClient'
import { canUseFoodLogs } from '../services/foodLogs'
import { getDailyNutrition, nutrientKeys } from '../services/nutrition'
import type { DailyNutrition, NutrientKey, NutrientSubtotal } from '../services/nutrition'
import { localDateTimeValue } from '../types/localTime'
import { featurePaths } from '../types/navigation'

const button = 'min-h-11 shrink-0 cursor-pointer rounded-xl border border-border px-3 py-2 font-semibold text-forest hover:bg-sage'
const knownReasons = [
  'food_not_found', 'ambiguous_food_match', 'food_state_unknown', 'food_preparation_mismatch',
  'mixed_dish_unsupported', 'quantity_unknown', 'invalid_quantity', 'portion_needs_review',
  'food_reference_binding_invalid', 'food_reference_binding_stale', 'food_reference_binding_version_unavailable',
  'unsupported_unit', 'unsupported_serving_conversion', 'nutrient_data_missing',
]

function localDate() {
  return localDateTimeValue(new Date()).slice(0, 10)
}

function errorKey(error: unknown) {
  if (error instanceof ApiError) return 'unavailable'
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'network'
  return error instanceof TypeError ? 'network' : 'invalid'
}

export function TodayNutrition() {
  const { t } = useTranslation()
  return (
    <section className="card grid min-w-0 gap-4 p-4 sm:p-6" aria-labelledby="nutrition-title">
      <h2 id="nutrition-title">{t('nutrition.title')}</h2>
      {import.meta.env.DEV && canUseFoodLogs()
        ? <LocalNutrition />
        : <p className="text-sm text-muted">{t('nutrition.localOnly')}</p>}
    </section>
  )
}

function LocalNutrition() {
  const { t, i18n } = useTranslation()
  const [query, setQuery] = useState(() => ({ date: localDate() }))
  const [result, setResult] = useState<{ query: typeof query; data?: DailyNutrition; error?: string }>()
  const current = result?.query === query ? result : undefined
  const formatter = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumFractionDigits: 1 })

  useEffect(() => {
    const controller = new AbortController()
    void getDailyNutrition(query.date, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setResult({ query, data }) },
      (error: unknown) => { if (!controller.signal.aborted) setResult({ query, error: errorKey(error) }) },
    )
    return () => controller.abort()
  }, [query])

  function estimate(value: string, unit: 'kcal' | 'g') {
    const amount = Number(value)
    const display = amount > 0 && amount < 0.1 ? '<' + formatter.format(0.1) : formatter.format(amount)
    return t('nutrition.measure', { value: display, unit: t(`nutrition.units.${unit}`) })
  }

  function totals(nutrients: Record<NutrientKey, NutrientSubtotal>, count: number, compact = false) {
    if (!nutrientKeys.some((key) => nutrients[key].subtotal !== null)) return null
    return (
      <dl className={`grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4 ${compact ? 'text-sm' : ''}`}>
        {nutrientKeys.map((key) => {
          const { subtotal, unit, contributing_items: contributors } = nutrients[key]
          return (
            <div key={key} className="min-w-0 rounded-xl bg-paper px-3 py-2 wrap-anywhere">
              <dt className="text-sm text-muted">{t(`nutrition.nutrients.${key}`)}</dt>
              <dd className="font-semibold tabular-nums">
                {subtotal === null ? t('nutrition.noValue') : estimate(subtotal, unit)}
              </dd>
              {contributors !== count && (
                <dd className="text-xs text-muted">{t('nutrition.estimatedItems', { computed: contributors, total: count })}</dd>
              )}
            </div>
          )
        })}
      </dl>
    )
  }

  const data = current?.data
  return (
    <>
      <div className="flex flex-wrap items-end gap-2">
        <label className="planning-field text-sm">
          {t('nutrition.date')}
          <input type="date" min="0001-01-01" max="9999-12-31" value={query.date} className="planning-input"
            onChange={(event) => {
              if (event.target.value && event.target.validity.valid) setQuery({ date: event.target.value })
            }} />
        </label>
        <button type="button" className={button} onClick={() => setQuery({ date: localDate() })}>
          {t('nutrition.today')}
        </button>
      </div>
      {!current && <p role="status" className="text-sm text-muted">{t('nutrition.loading')}</p>}
      {current?.error && (
        <div className="grid justify-items-start gap-2">
          <p role="alert">{t(`nutrition.errors.${current.error}`)}</p>
          <button type="button" className={button} onClick={() => setQuery({ date: query.date })}>
            {t('nutrition.retry')}
          </button>
        </div>
      )}
      {data && (
        <div className="grid min-w-0 gap-3">
          <div className="grid gap-1" role="status">
            <p className="font-semibold text-forest">{t(`nutrition.states.${data.status}`)}</p>
            {data.confirmed_log_count > 0 && (
              <p className="text-sm text-muted">
                {t('nutrition.logCount', { count: data.confirmed_log_count })} · {' '}
                {t('nutrition.estimatedItems', { computed: data.calculated_item_count, total: data.item_count })}
              </p>
            )}
          </div>
          {totals(data.nutrients, data.item_count)}
          {data.calculated_item_count > 0 && <p className="text-sm text-muted">{t('nutrition.recordedOnly')}</p>}
          {data.status === 'no_confirmed_logs' && (
            <Link className="text-link justify-self-start" to={featurePaths.log}>{t('nutrition.openLog')}</Link>
          )}
          {data.logs.length > 0 && (
            <ul className="grid gap-2" aria-label={t('nutrition.logs')}>
              {data.logs.map((log) => (
                <li key={log.log_id} className="min-w-0 rounded-xl border border-border p-3">
                  <details>
                    <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-forest">
                      {t(`pages.log.meals.${log.meal_type}`)} · <time dateTime={log.consumed_at}>{log.consumed_at.slice(11, 16)}</time>
                      {' · '}{t('nutrition.estimatedItems', { computed: log.summary.calculated_item_count, total: log.summary.item_count })}
                    </summary>
                    <div className="grid gap-2 pt-1">
                      {log.summary.calculated_item_count > 0 && (
                        <p className="text-sm font-medium">{t(log.summary.fully_calculated_item_count === log.summary.item_count
                          ? 'nutrition.logEstimate' : 'nutrition.logPartial')}</p>
                      )}
                      {totals(log.summary.nutrients, log.summary.item_count, true)}
                      <ul className="divide-y divide-border">
                        {log.items.map((item) => (
                          <li key={item.item_index} className="grid min-w-0 gap-1 py-2 text-sm wrap-anywhere">
                            <p className="font-semibold">{item.name}</p>
                            {item.reasons.map((reason) => (
                              <p key={reason} className="text-muted">
                                {t(`nutrition.reasons.${knownReasons.includes(reason) ? reason : 'unknown'}`)}
                              </p>
                            ))}
                            {item.conversion === 'reference_portion' && <p className="text-muted">{t('nutrition.estimatedPortion')}</p>}
                            {nutrientKeys.some((key) => item.nutrients[key] !== null) && (
                              <p className="flex flex-wrap gap-x-3 text-muted">
                                {nutrientKeys.map((key) => {
                                  const value = item.nutrients[key]
                                  return value === null ? null : (
                                    <span key={key}>{t(`nutrition.nutrients.${key}`)} {estimate(value, log.summary.nutrients[key].unit)}</span>
                                  )
                                })}
                              </p>
                            )}
                            {item.provenance && <a className="text-link min-h-8 justify-self-start"
                              href={`https://fdc.nal.usda.gov/food-details/${item.provenance.fdc_id}/nutrients`}>
                              {t('nutrition.itemSource')}
                            </a>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          )}
          {data.logs.length > 0 && (
            <details className="text-sm text-muted">
              <summary className="min-h-11 cursor-pointer py-2 font-medium">{t('nutrition.sources')}</summary>
              <p className="wrap-anywhere">{t('nutrition.sourceVersion', {
                release: data.reference_source.release, version: data.reference_version,
              })}</p>
            </details>
          )}
        </div>
      )}
    </>
  )
}
