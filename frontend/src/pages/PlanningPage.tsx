import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MealPlanResult } from '../components/MealPlanResult'
import { ApiError } from '../services/apiClient'
import { generateMealPlan, mealTypes } from '../services/mealPlans'
import type { MealPlan, MealPlanRequest } from '../services/mealPlans'
import { featurePaths } from '../types/navigation'

const scopes = ['single_meal', 'full_day'] as const
const examples = ['quickDinner', 'existingIngredients', 'fullDay'] as const

function errorKey(error: unknown) {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 422: return 'invalid'
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
  const [result, setResult] = useState<{ plan: MealPlan; language: MealPlanRequest['language'] }>()
  const requirements = useRef<HTMLTextAreaElement>(null)
  const options = useRef<HTMLDetailsElement>(null)
  const activeRequest = useRef<AbortController | null>(null)
  const invalidIngredients = error === 'ingredientsRequired' || error === 'ingredientLimit'
  const invalidField = error === 'requirements' || error === 'time' || invalidIngredients

  useEffect(() => () => activeRequest.current?.abort(), [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (activeRequest.current) return

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
    setBusy(true)
    try {
      const plan = await generateMealPlan(payload, controller.signal, scope === '' && !mealType)
      if (!controller.signal.aborted) setResult({ plan, language })
    } catch (failure) {
      if (!controller.signal.aborted) setError(errorKey(failure))
    } finally {
      activeRequest.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return (
    <div className="grid gap-6">
      <h1>{t('pages.plan.requirements')}</h1>

      <form className="card p-5 sm:p-6" onSubmit={(event) => void submit(event)} noValidate>
        <fieldset disabled={busy} className="grid min-w-0 gap-4">
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
      </form>

      {result && <MealPlanResult plan={result.plan} language={result.language} />}
      <Link className="text-link justify-self-start" to={featurePaths.today}>
        <span aria-hidden="true">←</span> {t('back')}
      </Link>
    </div>
  )
}
