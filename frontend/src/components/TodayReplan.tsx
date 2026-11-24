import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { MealPlanResult } from './MealPlanResult'
import { ApiError } from '../services/apiClient'
import type { MealType } from '../services/mealPlans'
import { acceptMealPlan, getSavedMealPlan, PlanStorageError, settingsForMeal } from '../services/mealPlanRepository'
import type { SavedMealPlan } from '../services/mealPlanRepository'
import { eligibleMeals, getReplanContext, getReplanPreview } from '../services/replan'
import type { ReplanContext, ReplanPreview, ReplanRequest } from '../services/replan'
import { localDateTimeValue } from '../types/localTime'

const button = 'min-h-11 cursor-pointer rounded-xl border border-border px-3 py-2 font-semibold text-forest hover:bg-sage disabled:cursor-not-allowed disabled:opacity-50'
const primary = 'min-h-11 cursor-pointer rounded-xl bg-forest px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50'
const localDay = () => localDateTimeValue(new Date()).slice(0, 10)
const timeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

function replanError(error: unknown) {
  if (error instanceof PlanStorageError) return error.code === 'stale' ? 'stale' : 'storage'
  if (error instanceof ApiError) {
    const detail = error.detail
    const status = typeof detail === 'object' && detail !== null && 'status' in detail ? detail.status : null
    if (['meal_slot_completed', 'meal_slot_not_remaining', 'stale_context', 'date_not_today'].includes(String(status))) return 'stale'
    if (status === 'clarification_required') return 'clarify'
    if (status === 'unsupported_constraints') return 'unsupported'
    if (status === 'no_feasible_plan') return 'noPlan'
    if (status === 'catalog_disabled') return 'catalog'
    if (error.status === 504) return 'timeout'
    if (error.status === 422) return 'invalid'
    return 'unavailable'
  }
  return error instanceof TypeError || (error instanceof DOMException && error.name === 'TimeoutError')
    ? 'network' : 'invalid'
}

export function TodayReplan() {
  const { t } = useTranslation()
  const [query, setQuery] = useState(() => ({ date: localDay() }))
  const [loaded, setLoaded] = useState<{
    query: typeof query; context?: ReplanContext; record?: SavedMealPlan | null; error?: string
  }>()
  const [notice, setNotice] = useState('')
  const [acceptedVersion, setAcceptedVersion] = useState<number>()
  const current = loaded?.query === query ? loaded : undefined
  const active = current?.record?.revisions.at(-1)
  const original = current?.record?.revisions[0]
  function selectDate(date: string) {
    setNotice('')
    setAcceptedVersion(undefined)
    setQuery({ date })
  }

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([getReplanContext(query.date, controller.signal), getSavedMealPlan(query.date)]).then(
      ([context, record]) => { if (!controller.signal.aborted) setLoaded({ query, context, record }) },
      (error: unknown) => { if (!controller.signal.aborted) setLoaded({ query, error: replanError(error) }) },
    )
    return () => controller.abort()
  }, [query])

  return (
    <section className="card grid min-w-0 gap-3 p-4 sm:p-6" aria-labelledby="replan-title">
      <h2 id="replan-title">{t('replan.title')}</h2>
      <label className="planning-field w-fit text-sm">
        {t('replan.date')}
        <input type="date" min="0001-01-01" max="9999-12-31" className="planning-input" value={query.date}
          onChange={(event) => {
            if (event.target.value && event.target.validity.valid) selectDate(event.target.value)
          }} />
      </label>
      {notice && <p role="alert" className="text-sm text-red-800">{t(`replan.errors.${notice}`)}</p>}
      {acceptedVersion !== undefined && <p role="status" className="text-forest">{t('replan.applied', { revision: acceptedVersion })}</p>}
      {!current && <p role="status" className="text-muted">{t('replan.loading')}</p>}
      {current?.error && (
        <div className="grid justify-items-start gap-2">
          <p role="alert">{t(`replan.errors.${current.error}`)}</p>
          <button type="button" className={button} onClick={() => selectDate(query.date)}>{t('replan.reload')}</button>
        </div>
      )}
      {current?.context && (
        <>
          <p className="text-sm text-muted">{t('replan.confirmed', { count: current.context.confirmed_log_count })} {' '}
            {t('replan.confirmedTypes', {
              types: current.context.locked_meal_types.map((slot) => t(`pages.plan.meals.${slot}`)).join(' · ')
                || t('replan.none'),
            })}
          </p>
          {current.context.unspecified_log_count > 0
            && <p className="text-sm text-muted">{t('replan.unspecified', { count: current.context.unspecified_log_count })}</p>}
          <p className="text-sm text-muted">{t('replan.historyUnknown')}</p>
          {active ? (
            <>
              <details className="min-w-0 rounded-xl border border-border p-3">
                <summary className="min-h-11 cursor-pointer py-2 font-semibold">{t('replan.active', { revision: active.revision })}</summary>
                <MealPlanResult plan={active.plan} language={active.language} />
              </details>
              {original && original.revision !== active.revision && (
                <details className="min-w-0 rounded-xl border border-border p-3">
                  <summary className="min-h-11 cursor-pointer py-2 font-semibold">{t('replan.original')}</summary>
                  <MealPlanResult plan={original.plan} language={original.language} />
                </details>
              )}
            </>
          ) : <p className="text-sm text-muted">{t('replan.noSavedPlan')}</p>}
          {query.date !== localDay() ? <p className="text-muted">{t('replan.todayOnly')}</p> : (
            <ReplanControls key={`${query.date}:${active?.revision ?? 0}:${current.context.context_fingerprint}`}
              context={current.context} record={current.record ?? null}
              onStale={() => { setNotice('stale'); setAcceptedVersion(undefined); setQuery({ date: query.date }) }}
              onApplied={(record) => {
                setNotice('')
                setAcceptedVersion(record.revision)
                setLoaded({ ...current, record })
              }} />
          )}
        </>
      )}
    </section>
  )
}

function ReplanControls({ context, record, onStale, onApplied }: {
  context: ReplanContext; record: SavedMealPlan | null; onStale: () => void; onApplied: (record: SavedMealPlan) => void
}) {
  const { t } = useTranslation()
  const choices = eligibleMeals(context)
  const [target, setTarget] = useState<MealType | ''>(context.remaining_main_meal_types[0] ?? '')
  if (!choices.length) return <p className="text-sm text-muted">{t('replan.noneRemaining')}</p>
  return (
    <details className="rounded-xl border border-border p-3">
      <summary className="min-h-11 cursor-pointer py-2 font-semibold text-forest">{t('replan.action')}</summary>
      <div className="grid gap-3 pt-2">
        {context.remaining_main_meal_types.length === 0 && <p className="text-sm text-muted">{t('replan.snackOnly')}</p>}
        <label className="planning-field text-sm">
          {t('replan.target')}
          <select className="planning-input" value={target} onChange={(event) =>
            setTarget(choices.find((slot) => slot === event.target.value) ?? '')}>
            <option value="">{t('replan.choose')}</option>
            {choices.map((slot) => <option key={slot} value={slot}>{t(`pages.plan.meals.${slot}`)}</option>)}
          </select>
        </label>
        {target && <ReplanTarget key={target} target={target} context={context} record={record}
          onStale={onStale} onApplied={onApplied} />}
      </div>
    </details>
  )
}

function ReplanTarget({ target, context, record, onStale, onApplied }: {
  target: MealType; context: ReplanContext; record: SavedMealPlan | null
  onStale: () => void; onApplied: (record: SavedMealPlan) => void
}) {
  const { t, i18n } = useTranslation()
  const active = record?.revisions.at(-1)
  const savedSettings = active ? settingsForMeal(active, target) : undefined
  const [restriction, setRestriction] = useState('')
  const [busy, setBusy] = useState<'preview' | 'apply'>()
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<{ result: ReplanPreview; request: ReplanRequest }>()
  const operation = useRef<AbortController | null>(null)
  const currentMeal = active?.plan.meals.find((meal) => meal.meal_type === target)

  useEffect(() => () => operation.current?.abort(), [])

  async function run(kind: 'preview' | 'apply', task: (signal: AbortSignal) => Promise<void>) {
    if (operation.current) return
    const controller = new AbortController()
    operation.current = controller
    setBusy(kind)
    setError('')
    try {
      await task(controller.signal)
    } catch (failure) {
      if (controller.signal.aborted) return
      const key = replanError(failure)
      if (key === 'stale') {
        setPreview(undefined)
        onStale()
      } else setError(key)
    } finally {
      operation.current = null
      if (!controller.signal.aborted) setBusy(undefined)
    }
  }

  function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (restriction !== 'none_declared' || operation.current) return
    if (localDay() !== context.date) { onStale(); return }
    const form = new FormData(event.currentTarget)
    const pantry = String(form.get('ingredients') ?? '').split(/[,，、;；\n]+/).map((value) => value.trim()).filter(Boolean)
    const instructions = String(form.get('instructions') ?? '').trim()
    const limit = String(form.get('minutes') ?? '')
    const minutes = limit ? Number(limit) : undefined
    const ingredientMode = form.get('ingredient-mode') === 'existing' ? 'existing' : 'flexible'
    if (pantry.length > 60 || pantry.some((name) => Array.from(name).length > 120)
      || (ingredientMode === 'existing' && !pantry.length) || Array.from(instructions).length > 1900
      || (minutes !== undefined && (!Number.isInteger(minutes) || minutes < 1 || minutes > 480))) {
      setError('inputs')
      return
    }
    const request: ReplanRequest = {
      date: context.date, timezone: timeZone(), target_meal_type: target,
      expected_context_fingerprint: context.context_fingerprint,
      current_plan: active && record ? {
        plan_id: record.planId, revision: record.revision, date: record.date, source: active.source, plan: active.plan,
      } : undefined,
      planning_mode: 'prompt_only',
      constraints: {
        language: i18n.resolvedLanguage === 'zh-CN' ? 'zh-CN' : 'en-US',
        ingredient_mode: ingredientMode, available_ingredients: pantry, cooking_time_limit: minutes,
        prefer_low_effort: form.has('effort'), one_person: form.has('one-person'), restriction_status: 'none_declared',
      },
      instructions,
    }
    setPreview(undefined)
    void run('preview', async (signal) => {
      const result = await getReplanPreview(request, signal)
      if (!signal.aborted) setPreview({ result, request })
    })
  }

  function apply() {
    if (!preview || restriction !== 'none_declared') return
    const { result, request } = preview
    void run('apply', async (signal) => {
      if (localDay() !== request.date || timeZone() !== request.timezone) throw new PlanStorageError('stale')
      const [latestContext, latestPlan] = await Promise.all([
        getReplanContext(request.date, signal), getSavedMealPlan(request.date),
      ])
      if (signal.aborted) return
      if (localDay() !== request.date || timeZone() !== request.timezone
        || latestContext.context_fingerprint !== request.expected_context_fingerprint
        || !eligibleMeals(latestContext).includes(request.target_meal_type)
        || latestPlan?.planId !== request.current_plan?.plan_id
        || latestPlan?.revision !== request.current_plan?.revision) throw new PlanStorageError('stale')
      const settings = request.constraints
      const saved = await acceptMealPlan(request.date, {
        acceptanceId: result.proposal_id, plan: result.suggested_plan, source: request.planning_mode,
        language: settings.language,
        constraints: {
          scope: 'single_meal', meal_type: request.target_meal_type, inferScope: false,
          ingredient_mode: settings.ingredient_mode, available_ingredients: settings.available_ingredients,
          cooking_time_limit: settings.cooking_time_limit, onePerson: settings.one_person,
          preferLowEffort: settings.prefer_low_effort,
        },
      }, latestPlan)
      if (!saved) throw new PlanStorageError('unavailable')
      if (!signal.aborted) onApplied(saved)
    })
  }

  return (
    <div className="grid min-w-0 gap-3">
      <form className="grid gap-3" onSubmit={generate} onChange={() => setPreview(undefined)}>
        <fieldset className="grid min-w-0 gap-3" disabled={!!busy}>
          <label className="planning-field text-sm">
            {t('replan.restrictions')}
            <select className="planning-input" value={restriction} aria-describedby="replan-review-help"
              onChange={(event) => setRestriction(event.target.value)}>
              <option value="">{t('replan.review')}</option>
              <option value="none_declared">{t('replan.noRestrictions')}</option>
              <option value="present">{t('replan.hasRestrictions')}</option>
            </select>
          </label>
          <p id="replan-review-help" className="text-sm text-muted">{t('replan.reviewHelp')}</p>
          {restriction === 'present' && <p role="status" className="text-sm text-muted">{t('replan.errors.unsupported')}</p>}
          <details className="rounded-xl bg-paper p-3">
            <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">{t('replan.constraints')}</summary>
            <div className="grid gap-2 pt-2">
              <label className="planning-field text-sm">
                {t('replan.ingredientMode')}
                <select name="ingredient-mode" className="planning-input" defaultValue={savedSettings?.constraints.ingredient_mode ?? 'flexible'}>
                  <option value="flexible">{t('replan.flexible')}</option>
                  <option value="existing">{t('replan.existing')}</option>
                </select>
              </label>
              <label className="planning-field text-sm">
                {t('replan.ingredients')}
                <textarea name="ingredients" className="planning-input" rows={2}
                  defaultValue={savedSettings?.constraints.available_ingredients?.join(', ')} />
              </label>
              <label className="planning-field text-sm">
                {t('replan.minutes')}
                <input name="minutes" type="number" min="1" max="480" step="1" className="planning-input"
                  defaultValue={savedSettings?.constraints.cooking_time_limit} />
              </label>
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input name="one-person" type="checkbox" defaultChecked={savedSettings?.constraints.onePerson ?? true} />
                {t('replan.onePerson')}
              </label>
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input name="effort" type="checkbox" defaultChecked={savedSettings?.constraints.preferLowEffort ?? false} />
                {t('replan.effort')}
              </label>
              <label className="planning-field text-sm">
                {t('replan.instructions')}
                <textarea name="instructions" maxLength={1900} rows={2} className="planning-input" />
              </label>
            </div>
          </details>
          <button type="submit" className={`${primary} justify-self-start`}
            disabled={restriction !== 'none_declared'}>
            {t(busy === 'preview' ? 'replan.generating' : 'replan.generate')}
          </button>
        </fieldset>
      </form>
      {busy && <p className="sr-only" role="status">{t(busy === 'preview' ? 'replan.generating' : 'replan.saving')}</p>}
      {error && <p role="alert" className="text-sm text-red-800">{t(`replan.errors.${error}`)}</p>}
      {preview && (
        <div className="grid min-w-0 gap-3">
          <p className="text-sm text-muted">{t('replan.previewOnly')}</p>
          <div className="grid min-w-0 gap-3 lg:grid-cols-2">
            <section className="min-w-0">
              <h3>{t('replan.currentMeal')}</h3>
              {currentMeal && active ? (
                <MealPlanResult plan={{
                  ...active.plan, title: t(`pages.plan.meals.${target}`), meals: [currentMeal], additional_ingredients: [],
                }} language={savedSettings?.language ?? active.language} />
              ) : <p className="mt-2 text-sm text-muted">{t('replan.noCurrentMeal')}</p>}
            </section>
            <section className="min-w-0">
              <h3>{t('replan.suggestion')}</h3>
              <MealPlanResult plan={preview.result.suggested_plan} language={preview.request.constraints.language} />
            </section>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={primary} onClick={apply} disabled={!!busy}>
              {t(busy === 'apply' ? 'replan.saving' : 'replan.accept')}
            </button>
            <button type="button" className={button} disabled={!!busy}
              onClick={() => { setPreview(undefined); setError('') }}>{t('replan.keep')}</button>
          </div>
        </div>
      )}
    </div>
  )
}
