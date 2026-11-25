import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { MealPlanResult } from './MealPlanResult'
import { PlanChangeSummary } from './PlanChangeSummary'
import { mealTypes } from '../services/mealPlans'
import type { MealType } from '../services/mealPlans'
import { acceptMealPlan, getLocalReplanSnapshot, PlanStorageError, savePlanLocks } from '../services/mealPlanRepository'
import type { PlanAcceptance } from '../services/mealPlanRepository'
import { quickReplanMinutes, suggestLocalMeal } from '../services/localReplan'
import { localDateTimeValue } from '../types/localTime'

const button = 'min-h-11 cursor-pointer rounded-xl border border-border px-3 py-2 font-semibold text-forest hover:bg-sage'
const primary = 'min-h-11 cursor-pointer rounded-xl bg-forest px-4 py-2 font-semibold text-white'
const today = () => localDateTimeValue(new Date()).slice(0, 10)
type Snapshot = Awaited<ReturnType<typeof getLocalReplanSnapshot>>

export function PublicTodayReplan({ refresh, onSaved }: { refresh: number; onSaved: () => void }) {
  const { t } = useTranslation()
  const [query, setQuery] = useState(() => ({ date: today() }))
  const [loaded, setLoaded] = useState<{ query: typeof query; refresh: number; snapshot?: Snapshot }>()
  const [notice, setNotice] = useState<{ error?: string; revision?: number; locks?: boolean }>({})
  const current = loaded?.query === query && loaded.refresh === refresh ? loaded : undefined
  useEffect(() => {
    let active = true
    void getLocalReplanSnapshot(query.date).then(
      (snapshot) => { if (active) setLoaded({ query, refresh, snapshot }) },
      () => { if (active) setLoaded({ query, refresh }) },
    )
    return () => { active = false }
  }, [query, refresh])

  return (
    <section className="card grid min-w-0 gap-3 p-4 sm:p-6" aria-labelledby="public-replan-title">
      <h2 id="public-replan-title">{t('replan.title')}</h2>
      <p className="text-sm text-muted">{t('replan.local.intro')}</p>
      <label className="planning-field w-fit text-sm">
        {t('replan.date')}
        <input type="date" min="0001-01-01" max="9999-12-31" className="planning-input" value={query.date}
          onChange={(event) => {
            if (!event.target.value || !event.target.validity.valid) return
            setNotice({})
            setQuery({ date: event.target.value })
          }} />
      </label>
      {notice.error && <p role="alert" className="text-red-800">{t(`replan.errors.${notice.error}`)}</p>}
      {notice.revision !== undefined && <p role="status">{t('replan.applied', { revision: notice.revision })}</p>}
      {notice.locks && <p role="status">{t('replan.local.locksSaved')}</p>}
      {!current ? <p role="status">{t('replan.loading')}</p> : !current.snapshot ? (
        <div className="grid justify-items-start gap-2">
          <p role="alert">{t('replan.errors.storage')}</p>
          <button type="button" className={button} onClick={() => setQuery({ date: query.date })}>{t('replan.reload')}</button>
        </div>
      ) : (
        <LocalReplanControls key={`${query.date}:${current.snapshot.record?.revision}:${current.snapshot.record?.lockRevision}:${current.snapshot.fingerprint}`}
          date={query.date} snapshot={current.snapshot}
          onStale={() => { setNotice({ error: 'stale' }); setQuery({ date: query.date }) }}
          onSaved={(revision) => {
            setNotice(revision === undefined ? { locks: true } : { revision })
            onSaved()
          }} />
      )}
    </section>
  )
}

function LocalReplanControls({ date, snapshot, onSaved, onStale }: {
  date: string; snapshot: Snapshot; onSaved: (revision?: number) => void; onStale: () => void
}) {
  const { t, i18n } = useTranslation()
  const { record, logs, fingerprint } = snapshot
  const active = record?.revisions.at(-1)
  const current = active?.plan.meals ?? []
  const consumed = new Set(logs.map((log) => log.meal_type))
  const locked = new Set(record?.lockedMealTypes ?? [])
  const choices = mealTypes.filter((slot) => !consumed.has(slot) && !locked.has(slot)
    && (slot !== 'snack' || current.some((meal) => meal.meal_type === slot)))
  const [target, setTarget] = useState<MealType | ''>('')
  const [restriction, setRestriction] = useState('')
  const [preview, setPreview] = useState<PlanAcceptance>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const activeWrite = useRef(false)
  const [locks, setLocks] = useState(() => [...locked])
  const locksChanged = locks.length !== locked.size || locks.some((slot) => !locked.has(slot))

  function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!target || !choices.includes(target) || restriction !== 'none_declared' || activeWrite.current || locksChanged) return
    const form = new FormData(event.currentTarget)
    const choice = suggestLocalMeal(record, logs, target, {
      noodles: form.has('noodles'), quick: form.has('quick'), avoidRepeat: form.has('avoidRepeat'),
      hasRestriction: restriction !== 'none_declared',
    }, i18n.resolvedLanguage === 'zh-CN' ? 'zh-CN' : 'en-US', t('blindBox.serving'))
    setPreview(choice)
    setError(choice ? '' : 'noPlan')
  }

  async function write(kind: 'accept' | 'lock') {
    if (activeWrite.current || (kind === 'accept' ? !preview || restriction !== 'none_declared' : !record)) return
    activeWrite.current = true
    setBusy(true)
    setError('')
    try {
      if (kind === 'accept' && preview) {
        const saved = await acceptMealPlan(date, preview, record, fingerprint)
        onSaved(saved.revision)
      } else if (record) {
        await savePlanLocks(date, record, locks)
        onSaved()
      }
    } catch (failure) {
      setPreview(undefined)
      if (failure instanceof PlanStorageError && ['locked', 'stale'].includes(failure.code)) onStale()
      else setError('storage')
    } finally {
      activeWrite.current = false
      setBusy(false)
    }
  }

  const listSlots = (slots: MealType[]) => slots.map((slot) => t(`pages.plan.meals.${slot}`)).join(' · ') || t('replan.none')
  const targetSlot = preview?.plan.meals[0]?.meal_type
  const unchanged = current.filter((meal) => meal.meal_type !== targetSlot).map((meal) => meal.meal_type)
  const currentTarget = current.filter((meal) => meal.meal_type === targetSlot)

  return (
    <div className="grid min-w-0 gap-3">
      <p className="text-sm text-muted">{t('replan.local.consumed', { slots: listSlots(mealTypes.filter((slot) => consumed.has(slot))) })}</p>
      <p className="text-sm text-muted">{t('replan.local.userLocked', { slots: listSlots([...locked]) })}</p>
      {consumed.has('unspecified') && <p className="text-sm text-muted">
        {t('replan.unspecified', { count: logs.filter((log) => log.meal_type === 'unspecified').length })}
      </p>}
      {active ? <p className="text-sm">{t('replan.active', { revision: active.revision })}</p>
        : <p className="text-sm">{t('replan.noSavedPlan')}</p>}
      {current.length > 0 && (
        <details className="rounded-xl border border-border p-3">
          <summary className="min-h-11 cursor-pointer py-2">{t('replan.local.manageLocks')}</summary>
          <fieldset disabled={busy} className="grid gap-2">
            {current.map(({ meal_type: slot }) => (
              <label className="flex min-h-11 items-center gap-2" key={slot}>
                <input type="checkbox" checked={locks.includes(slot)}
                  onChange={(event) => {
                    setPreview(undefined)
                    setLocks(event.target.checked ? [...locks, slot] : locks.filter((value) => value !== slot))
                  }} />
                {t('replan.local.keepSlot', { slot: t(`pages.plan.meals.${slot}`) })}
              </label>
            ))}
            <button type="button" className={`${button} w-fit`}
              disabled={!locksChanged}
              onClick={() => void write('lock')}>{t('replan.local.saveLocks')}</button>
          </fieldset>
        </details>
      )}
      {!choices.length ? <p>{t('replan.noneRemaining')}</p> : (
        <form onSubmit={propose} onChange={() => { setPreview(undefined); setError('') }}>
          <fieldset disabled={busy} className="grid min-w-0 gap-3">
            <label className="planning-field text-sm">
              {t('replan.target')}
              <select className="planning-input" value={target} onChange={(event) => {
                setTarget(choices.find((slot) => slot === event.target.value) ?? '')
              }}>
                <option value="">{t('replan.choose')}</option>
                {choices.map((slot) => <option key={slot} value={slot}>{t(`pages.plan.meals.${slot}`)}</option>)}
              </select>
            </label>
            <label className="planning-field text-sm">
              {t('replan.restrictions')}
              <select className="planning-input" value={restriction} onChange={(event) => setRestriction(event.target.value)}>
                <option value="">{t('replan.review')}</option>
                <option value="none_declared">{t('replan.noRestrictions')}</option>
                <option value="present">{t('replan.hasRestrictions')}</option>
              </select>
            </label>
            <p className="text-sm text-muted">{t('replan.reviewHelp')}</p>
            {restriction === 'present' && <p role="status">{t('replan.errors.unsupported')}</p>}
            <div className="flex flex-wrap gap-x-4">
              {(['noodles', 'quick', 'avoidRepeat'] as const).map((key) => (
                <label key={key} className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" name={key} />
                  {t(`replan.local.${key}`, { minutes: quickReplanMinutes })}
                </label>
              ))}
            </div>
            <button type="submit" className={`${primary} justify-self-start`}
              disabled={!target || restriction !== 'none_declared' || locksChanged}>{t('replan.generate')}</button>
          </fieldset>
        </form>
      )}
      {error && <p role="alert" className="text-red-800">{t(`replan.errors.${error}`)}</p>}
      {preview && (
        <section className="grid min-w-0 gap-3 rounded-xl border border-border p-3" aria-label={t('replan.suggestion')}>
          <p className="text-sm text-muted">{t('replan.previewOnly')}</p>
          <PlanChangeSummary current={currentTarget} proposed={preview.plan.meals} />
          <p className="text-sm">{t('replan.local.unchanged', { slots: listSlots(unchanged) })}</p>
          <details>
            <summary className="min-h-11 cursor-pointer py-2">{t('blindBox.viewRecipe')}</summary>
            <MealPlanResult plan={preview.plan} language={preview.language} />
          </details>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} className={primary} onClick={() => void write('accept')}>{t(busy ? 'replan.saving' : 'replan.accept')}</button>
            <button type="button" disabled={busy} className={button} onClick={() => setPreview(undefined)}>{t('replan.keep')}</button>
          </div>
        </section>
      )}
    </div>
  )
}
