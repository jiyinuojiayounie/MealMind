import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { PlanChangeSummary } from '../components/PlanChangeSummary'
import { publicPlanningExample } from '../services/blindBox'
import { MealPlanResult } from '../components/MealPlanResult'
import { ApiError } from '../services/apiClient'
import { generateMealPlan, mealTypes } from '../services/mealPlans'
import type { MealPlanRequest } from '../services/mealPlans'
import { acceptMealPlan, createPlanId, getSavedMealPlan, PlanStorageError } from '../services/mealPlanRepository'
import type { PlanAcceptance, SavedMealPlan } from '../services/mealPlanRepository'
import { localDateTimeValue } from '../types/localTime'
import { featurePaths } from '../types/navigation'

const scopes = ['single_meal', 'full_day'] as const
const examples = ['quickDinner', 'existingIngredients', 'fullDay'] as const
const planButton = 'min-h-11 cursor-pointer rounded-xl border border-border px-4 py-2 font-semibold text-forest hover:bg-sage disabled:cursor-not-allowed disabled:opacity-50'

function localPlanDate() {
  return localDateTimeValue(new Date()).slice(0, 10)
}

function storageError(error: unknown) {
  return error instanceof PlanStorageError ? error.code : 'unavailable'
}

function errorKey(error: unknown) {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 422: {
        const detail = error.detail
        const status = typeof detail === 'object' && detail !== null && 'status' in detail ? detail.status : undefined
        if (status === 'dietary_restriction_unverified') return 'dietaryUnverified'
        if (status === 'ingredient_restriction_unverified') return 'ingredientsUnverified'
        if (status === 'time_limit_unverified') return 'timeUnverified'
        return 'invalid'
      }
      case 429: return 'rateLimit'
      case 502: return 'generation'
      case 503: return 'unavailable'
      case 504: return 'timeout'
      default: return 'unexpected'
    }
  }
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'timeout'
  if (error instanceof TypeError) return import.meta.env.DEV ? 'networkDev' : 'network'
  return 'unexpected'
}

export function PlanningPage() {
  const { t, i18n } = useTranslation()
  const [scope, setScope] = useState<MealPlanRequest['scope'] | ''>('')
  const [mode, setMode] = useState<MealPlanRequest['ingredient_mode']>('flexible')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<PlanAcceptance>()
  const [selection, setSelection] = useState(() => ({ date: localPlanDate() }))
  const [saved, setSaved] = useState<{ selection: typeof selection; record?: SavedMealPlan | null; error?: string }>()
  const [saveError, setSaveError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [saving, setSaving] = useState(false)
  const saveInFlight = useRef(false)
  const requirements = useRef<HTMLTextAreaElement>(null)
  const options = useRef<HTMLDetailsElement>(null)
  const activeRequest = useRef<AbortController | null>(null)
  const invalidIngredients = error === 'ingredientsRequired' || error === 'ingredientLimit'
  const invalidField = error === 'requirements' || error === 'time' || invalidIngredients
  const current = saved?.selection === selection ? saved : undefined
  const accepted = current?.record?.revisions.at(-1)
  const replacing = Boolean(result?.plan.meals.some((meal) =>
    accepted?.plan.meals.some((stored) => stored.meal_type === meal.meal_type)))
  const alreadySaved = result && current?.record?.revisions.some((version) => version.acceptanceId === result.acceptanceId)

  useEffect(() => () => activeRequest.current?.abort(), [])
  useEffect(() => {
    let active = true
    void getSavedMealPlan(selection.date).then(
      (record) => { if (active) setSaved({ selection, record }) },
      (failure: unknown) => { if (active) setSaved({ selection, error: storageError(failure) }) },
    )
    return () => { active = false }
  }, [selection])

  function selectDate(date: string) {
    if (date === selection.date) return
    setResult(undefined)
    setConfirming(false)
    setSaveError('')
    setSelection({ date })
  }

  async function savePlan(confirmed = false) {
    if (!result || alreadySaved || !current || current.record === undefined || saveInFlight.current) return
    if (replacing && !confirmed) {
      setConfirming(true)
      return
    }
    setConfirming(false)
    saveInFlight.current = true
    setSaving(true)
    setSaveError('')
    try {
      const record = await acceptMealPlan(selection.date, result, current.record)
      setSaved({ selection, record })
    } catch (failure) {
      const key = storageError(failure)
      setSaveError(key)
      if (key === 'stale' || key === 'invalid') setSelection({ date: selection.date })
    } finally {
      saveInFlight.current = false
      setSaving(false)
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (import.meta.env.PROD || activeRequest.current) return
    setConfirming(false)

    const form = new FormData(event.currentTarget)
    const userRequest = String(form.get('requirements') ?? '').trim()
    const ingredients = String(form.get('ingredients') ?? '')
      .split(/[,，、\n;；]+/)
      .map((name) => name.trim())
      .filter(Boolean)
    const time = String(form.get('time') ?? '').trim()
    const minutes = time ? Number(time) : undefined
    const mealType = mealTypes.find((type) => type === form.get('meal-type'))

    if (!userRequest || Array.from(userRequest).length > 2000) {
      setError('requirements')
      return
    }
    if (mode === 'existing' && !ingredients.length) {
      if (options.current) options.current.open = true
      setError('ingredientsRequired')
      return
    }
    if (ingredients.length > 60 || ingredients.some((name) => Array.from(name).length > 120)) {
      if (options.current) options.current.open = true
      setError('ingredientLimit')
      return
    }
    const timeInput = event.currentTarget.elements.namedItem('time')
    if ((timeInput instanceof HTMLInputElement && timeInput.validity.badInput)
      || (minutes !== undefined && (!Number.isInteger(minutes) || minutes < 1 || minutes > 480))) {
      if (options.current) options.current.open = true
      setError('time')
      return
    }

    const language = i18n.resolvedLanguage === 'zh-CN' ? 'zh-CN' : 'en-US'
    const payload: MealPlanRequest = {
      user_request: userRequest,
      language,
      scope: scope || 'single_meal',
      meal_type: scope === 'full_day' ? undefined : mealType,
      available_ingredients: ingredients.length ? ingredients : undefined,
      ingredient_mode: mode,
      cooking_time_limit: minutes,
    }

    const controller = new AbortController()
    activeRequest.current = controller
    setError('')
    setResult(undefined)
    setConfirming(false)
    setSaveError('')
    setBusy(true)
    try {
      const inferScope = scope === '' && !mealType
      const plan = await generateMealPlan(payload, controller.signal, inferScope)
      if (!controller.signal.aborted) {
        setResult({
          plan, language, source: 'prompt_only', acceptanceId: createPlanId(),
          constraints: {
            scope: payload.scope, meal_type: payload.meal_type, ingredient_mode: payload.ingredient_mode,
            available_ingredients: payload.available_ingredients, cooking_time_limit: payload.cooking_time_limit, inferScope,
          },
        })
      }
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(errorKey(failure))
      }
    } finally {
      activeRequest.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return (
    <div className="grid gap-6">
      <h1>{t('pages.plan.requirements')}</h1>

      <section className="card grid min-w-0 gap-2 p-4 sm:p-5" aria-labelledby="saved-plan-heading">
        <h2 id="saved-plan-heading">{t('pages.plan.saved.heading')}</h2>
        <label className="planning-field w-fit text-sm">
          {t('pages.plan.saved.date')}
          <input type="date" className="planning-input" min="0001-01-01" max="9999-12-31" value={selection.date}
            disabled={busy || saving}
            onChange={(event) => {
              if (event.target.value && event.target.validity.valid) selectDate(event.target.value)
            }} />
        </label>
        {!current && <p role="status" className="text-sm text-muted">{t('pages.plan.saved.loading')}</p>}
        {current?.error && (
          <div className="grid justify-items-start gap-2">
            <p role="alert" className="text-sm text-red-800">{t(`pages.plan.saved.errors.${current.error}`)}</p>
            <button type="button" className={planButton} onClick={() => setSelection({ date: selection.date })}>
              {t('pages.plan.saved.retry')}
            </button>
          </div>
        )}
        {current?.record === null && <p className="text-sm text-muted">{t('pages.plan.saved.empty')}</p>}
        {accepted && (
          <details className="min-w-0">
            <summary className="min-h-11 cursor-pointer py-2 font-semibold text-forest wrap-anywhere">
              {t('pages.plan.saved.active', { revision: accepted.revision })} · <span lang={accepted.language}>{accepted.plan.title}</span>
            </summary>
            <MealPlanResult plan={accepted.plan} language={accepted.language} />
          </details>
        )}
      </section>

      {import.meta.env.DEV ? <form className="card p-5 sm:p-6" onSubmit={(event) => void submit(event)} noValidate>
        <fieldset disabled={busy || saving} className="grid min-w-0 gap-4">
          <label className="planning-field">
            <span className="sr-only">{t('pages.plan.requirements')}</span>
            <textarea ref={requirements} name="requirements" className="planning-input" rows={5} maxLength={2000} required
              placeholder={t('pages.plan.requirementsExample')} aria-invalid={error === 'requirements'} />
          </label>

          <div className="flex flex-wrap gap-2" role="group" aria-label={t('pages.plan.examplesLabel')}>
            {examples.map((example) => {
              const prompt = t(`pages.plan.examples.${example}`)
              return (
                <button key={example} type="button"
                  className="min-h-11 cursor-pointer rounded-full bg-sage px-3 py-2 text-start text-sm text-forest hover:bg-forest hover:text-white"
                  onClick={() => {
                    if (!requirements.current) return
                    requirements.current.value = prompt
                    requirements.current.focus()
                    setError('')
                  }}>
                  {prompt}
                </button>
              )
            })}
          </div>

          <button className="min-h-11 w-full cursor-pointer rounded-xl bg-forest px-5 py-2 font-semibold text-white disabled:cursor-wait disabled:opacity-70" type="submit" disabled={busy}>
            {t(busy ? 'pages.plan.loading' : error && !invalidField ? 'pages.plan.retry' : 'pages.plan.submit')}
          </button>
          <details ref={options} className="border-t border-border pt-2">
            <summary className="min-h-11 cursor-pointer py-2.5 font-semibold text-forest">
              {t('pages.plan.moreOptions')}
            </summary>
            <div className="grid gap-4 pt-2">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="planning-field">
                  {t('pages.plan.scope')}
                  <select className="planning-input" value={scope}
                    onChange={(event) => setScope(scopes.find((value) => value === event.target.value) ?? '')}>
                    <option value="">{t('pages.plan.automatic')}</option>
                    <option value="single_meal">{t('pages.plan.single')}</option>
                    <option value="full_day">{t('pages.plan.day')}</option>
                  </select>
                </label>

                <label className="planning-field">
                  {t('pages.plan.mealType')}
                  <select name="meal-type" className="planning-input" disabled={scope === 'full_day'}>
                    <option value="">{t('pages.plan.anyMeal')}</option>
                    {mealTypes.map((type) => <option value={type} key={type}>{t(`pages.plan.meals.${type}`)}</option>)}
                  </select>
                </label>

                <label className="planning-field">
                  {t('pages.plan.mode')}
                  <select className="planning-input" value={mode}
                    onChange={(event) => setMode(event.target.value === 'existing' ? 'existing' : 'flexible')}>
                    <option value="flexible">{t('pages.plan.flexible')}</option>
                    <option value="existing">{t('pages.plan.existing')}</option>
                  </select>
                </label>

                <label className="planning-field">
                  {t('pages.plan.time')}
                  <input name="time" className="planning-input" type="number" min={1} max={480}
                    step={1} inputMode="numeric" aria-invalid={error === 'time'} />
                </label>
              </div>

              <div className="planning-field">
                <label htmlFor="available-ingredients">{t(mode === 'existing' ? 'pages.plan.availableRequired' : 'pages.plan.availableOptional')}</label>
                <textarea id="available-ingredients" name="ingredients" className="planning-input" rows={2} required={mode === 'existing'}
                  aria-describedby="ingredient-hint" aria-invalid={invalidIngredients} />
                <span id="ingredient-hint" className="text-sm font-normal text-muted">{t('pages.plan.ingredientHint')}</span>
              </div>
            </div>
          </details>
        </fieldset>
        {error && <p className="mt-3 text-sm font-medium text-red-800" role="alert">{t(`pages.plan.errors.${error}`)}</p>}
        <p className="sr-only" role="status">{busy ? t('pages.plan.loading') : result ? t('pages.plan.ready') : ''}</p>
      </form> : (
        <section className="card grid gap-3 p-5">
          <h2>{t('release.sampleTitle')}</h2>
          <p>{t('release.planningExample')}</p>
          {!result && <button type="button" className={planButton} onClick={() => {
            const language = i18n.resolvedLanguage === 'en' ? 'en-US' : 'zh-CN'
            setResult({
              acceptanceId: createPlanId(), language, source: 'blind_box',
              plan: publicPlanningExample(language, t('release.sampleTitle'), t('release.planningExample'), t('blindBox.serving')),
              constraints: { scope: 'full_day', ingredient_mode: 'flexible', inferScope: false },
            })
          }}>{t('release.loadExample')}</button>}
        </section>
      )}

      {result && (
        <div className="grid gap-4">
          <div className="card grid justify-items-start gap-2 p-4">
            <p role="status" className="text-sm font-medium text-forest">
              {t(alreadySaved ? 'pages.plan.saved.accepted' : 'pages.plan.saved.temporary', { date: selection.date })}
            </p>
            {saveError && <p role="alert" className="text-sm text-red-800">{t(`pages.plan.saved.errors.${saveError}`)}</p>}
            {!alreadySaved && (confirming ? (
              <section className="grid w-full gap-3" aria-labelledby="planning-replace-title">
                <h2 id="planning-replace-title">{t('release.replacePrompt')}</h2>
                <PlanChangeSummary current={accepted?.plan.meals ?? []} proposed={result.plan.meals} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={planButton} onClick={() => void savePlan(true)}>{t('blindBox.confirmReplace')}</button>
                  <button type="button" className={planButton} onClick={() => setConfirming(false)}>{t('blindBox.cancel')}</button>
                </div>
              </section>
            ) : (
              <button type="button" className={planButton} disabled={saving || current?.record === undefined}
                onClick={() => void savePlan()}>
                {t(saving ? 'pages.plan.saved.saving' : replacing ? 'release.reviewReplacement' : 'release.add')}
              </button>
            ))}
          </div>
          <MealPlanResult plan={result.plan} language={result.language} />
        </div>
      )}
      <Link className="text-link justify-self-start" to={featurePaths.today}>
        <span aria-hidden="true">←</span> {t('back')}
      </Link>
    </div>
  )
}
