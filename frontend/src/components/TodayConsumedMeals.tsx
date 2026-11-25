import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { listLocalFoodLogs } from '../services/localFoodLogRepository'
import type { FoodLog } from '../services/foodLogs'
import { localDateTimeValue } from '../types/localTime'
import { featurePaths } from '../types/navigation'

export function TodayConsumedMeals() {
  const { t, i18n } = useTranslation()
  const [view, setView] = useState(() => ({ date: localDateTimeValue(new Date()).slice(0, 10) }))
  const [loaded, setLoaded] = useState<{ view: typeof view; logs?: FoodLog[] }>()
  const current = loaded?.view === view ? loaded : undefined

  useEffect(() => {
    let active = true
    void listLocalFoodLogs(view.date).then(
      (logs) => { if (active) setLoaded({ view, logs: logs.filter((log) => log.status === 'confirmed') }) },
      () => { if (active) setLoaded({ view }) },
    )
    return () => { active = false }
  }, [view])

  useEffect(() => {
    const refresh = () => setView({ date: localDateTimeValue(new Date()).slice(0, 10) })
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumSignificantDigits: 15 })
  return (
    <section className="card grid min-w-0 gap-3 p-4 sm:p-6" aria-labelledby="today-consumed-title">
      <h2 id="today-consumed-title">{t('pages.log.consumedTitle')}</h2>
      {!current ? <p role="status">{t('pages.log.loading')}</p> : current.logs === undefined ? (
        <>
          <p role="alert">{t('pages.log.errors.storage')}</p>
          <button type="button" className="text-link w-fit min-h-11"
            onClick={() => setView({ ...view })}>{t('pages.log.retry')}</button>
        </>
      ) : current.logs.length === 0 ? <p className="text-muted">{t('pages.log.consumedEmpty')}</p> : (
        <ul className="meal-list">
          {current.logs.map((log) => (
            <li key={log.id} className="min-w-0">
              <strong>{t(`pages.log.meals.${log.meal_type}`)} · <time dateTime={log.consumed_at}>{log.consumed_at.slice(11, 16)}</time></strong>
              <span className="min-w-0 wrap-anywhere">{log.items.map((item) =>
                item.quantity === null ? item.name : [item.name, number.format(item.quantity), item.unit].filter(Boolean).join(' '),
              ).join(' / ')}</span>
            </li>
          ))}
        </ul>
      )}
      <Link className="text-link w-fit" to={featurePaths.log}>{t('pages.log.openLog')}</Link>
    </section>
  )
}
