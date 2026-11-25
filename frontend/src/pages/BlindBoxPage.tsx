import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PlanChangeSummary } from '../components/PlanChangeSummary'
import { BlindBoxWheel } from '../components/BlindBoxWheel'
import { demoMealPlan, drawDemoMeal } from '../services/blindBox'
import type { BlindBoxMeal } from '../services/blindBox'
import { canUseFoodLogs } from '../services/foodLogs'
import { acceptMealPlan, createPlanId, getSavedMealPlan, PlanStorageError } from '../services/mealPlanRepository'
import type { PlanAcceptance, SavedMealPlan } from '../services/mealPlanRepository'
import { confirmedMealSlots, listLocalFoodLogs } from '../services/localFoodLogRepository'
import { getReplanContext } from '../services/replan'
import { localDateTimeValue } from '../types/localTime'

type SavePreview = {
  date: string
  choice: PlanAcceptance
  record: SavedMealPlan | null
  fingerprint?: string
}

const slots = ['breakfast', 'lunch', 'dinner'] as const

export default function BlindBoxPage({ onSaved }: { onSaved?: () => void }) {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage === 'en' ? 'en-US' : 'zh-CN'
  const [mealType, setMealType] = useState<BlindBoxMeal>('dinner')
  const [hasRestriction, setHasRestriction] = useState(false)
  const [recipe, setRecipe] = useState<ReturnType<typeof drawDemoMeal>>()
  const [attempted, setAttempted] = useState(false)
  const [spinning, setSpinning] = useState(false)
  const [rotation, setRotation] = useState(0)
  const recipeDialog = useRef<HTMLDialogElement>(null)
  const saveDialog = useRef<HTMLDialogElement>(null)
  const recipeTrigger = useRef<HTMLButtonElement>(null)
  const saveTrigger = useRef<HTMLButtonElement>(null)
  const spinTimer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(spinTimer.current), [])

  const [date, setDate] = useState(() => localDateTimeValue(new Date()).slice(0, 10))
  const [saveSlot, setSaveSlot] = useState<BlindBoxMeal>('dinner')
  const [preview, setPreview] = useState<SavePreview>()
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)
  const saveAvailable = import.meta.env.PROD || canUseFoodLogs()
  const plan = recipe && demoMealPlan(recipe, mealType, language, t('blindBox.serving'))
  const meal = plan?.meals[0]
  const existing = preview?.record?.revisions.at(-1)?.plan.meals.find(
    (meal) => meal.meal_type === preview.choice.constraints.meal_type,
  )

  function clearSave() {
    setPreview(undefined)
    setMessage('')
  }

  async function runSave(action: () => Promise<void>) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setMessage('')
    try {
      await action()
    } catch (error) {
      setPreview(undefined)
      setMessage(error instanceof PlanStorageError && (error.code === 'stale' || error.code === 'locked') ? error.code : 'saveFailed')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function reviewSave() {
    if (!recipe || hasRestriction || !saveAvailable || !date || !recipe.meal_types.includes(saveSlot)) return
    const choice: PlanAcceptance = {
      acceptanceId: createPlanId(),
      source: 'blind_box',
      language,
      plan: demoMealPlan(recipe, saveSlot, language, t('blindBox.serving')),
      constraints: { scope: 'single_meal', meal_type: saveSlot, ingredient_mode: 'flexible', inferScope: false, onePerson: true },
    }
    void runSave(async () => {
      const [record, context, logs] = await Promise.all([
        getSavedMealPlan(date), import.meta.env.DEV ? getReplanContext(date) : undefined,
        import.meta.env.PROD ? listLocalFoodLogs(date) : [],
      ])
      if (context?.locked_meal_types.includes(saveSlot) || confirmedMealSlots(logs).has(saveSlot) || record?.lockedMealTypes?.includes(saveSlot)) {
        setMessage('locked')
        return
      }
      setPreview({ date, choice, record, fingerprint: context?.context_fingerprint })
    })
  }

  function confirmSave() {
    if (!preview || !saveAvailable) return
    const { date, choice, record, fingerprint } = preview
    void runSave(async () => {
      const context = import.meta.env.DEV ? await getReplanContext(date) : undefined
      if (choice.constraints.meal_type && context?.locked_meal_types.includes(choice.constraints.meal_type)) {
        setPreview(undefined)
        setMessage('locked')
        return
      }
      if (context?.context_fingerprint !== fingerprint) throw new PlanStorageError('stale')
      const accepted = await acceptMealPlan(date, choice, record)
      if (!accepted) throw new PlanStorageError('unavailable')
      setPreview(undefined)
      setMessage('saved')
      onSaved?.()
    })
  }

  function clearDraw() {
    clearSave()
    setRecipe(undefined)
    setAttempted(false)
    setRotation(0)
  }

  function draw() {
    if (spinTimer.current !== undefined || inFlight.current) return
    const selected = drawDemoMeal(mealType, hasRestriction, recipe?.recipe_id)
    clearSave()
    setSaveSlot(mealType)
    setAttempted(true)
    if (!selected) {
      setRecipe(undefined)
      return
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Rotation is decorative and has no connection to candidate identity or count.
    if (!reducedMotion) setRotation((previous) => previous + 1190)
    if (reducedMotion) {
      setRecipe(selected)
      return
    }
    setSpinning(true)
    spinTimer.current = window.setTimeout(() => {
      spinTimer.current = undefined
      setRecipe(selected)
      setSpinning(false)
    }, 1100)
  }

  return (
    <div className="blind-box" data-compact={Boolean(recipe)}>
      <header className="blind-intro">
        <h1>{t('blindBox.heading')}</h1>
        <p>{t('blindBox.intro')}</p>
      </header>
      <div className="blind-layout">
        <section className="blind-stage card">
          <fieldset disabled={busy || spinning}>
            <legend className="sr-only">{t('blindBox.slot')}</legend>
            <div className="blind-slots">
              {slots.map((slot) => (
                <label key={slot}>
                  <input className="sr-only" type="radio" name="blind-box-slot" checked={mealType === slot} onChange={() => {
                    setMealType(slot)
                    clearDraw()
                  }} />
                  <span>{t(`pages.plan.meals.${slot}`)}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <BlindBoxWheel rotation={rotation} spinning={spinning} />
          <button type="button" disabled={busy || spinning} className="blind-primary" onClick={draw}>
            {t(spinning ? 'blindBox.spinning' : recipe ? 'blindBox.redraw' : 'blindBox.draw')}
          </button>
          <details className="blind-restrictions">
            <summary>{t('blindBox.restrictions')}</summary>
            <label className="mt-2 flex min-h-11 items-start gap-2">
              <input type="checkbox" disabled={busy || spinning} className="mt-1" checked={hasRestriction} onChange={(event) => {
                setHasRestriction(event.currentTarget.checked)
                clearDraw()
              }} />
              {t('blindBox.declare')}
            </label>
          </details>
        </section>
        <p role="status" className={attempted && !recipe && !spinning ? 'card p-4' : 'sr-only'}>
          {spinning ? t('blindBox.spinning') : recipe?.names[language]
            ?? (attempted ? t(hasRestriction ? 'blindBox.unverified' : 'blindBox.empty') : '')}
        </p>
        {recipe && plan && meal && (
          <div className="blind-result grid min-w-0 gap-4" data-recipe-id={recipe.recipe_id} aria-busy={spinning}>
            <article className="blind-meal card">
              <div className="blind-result-art" aria-hidden="true"><span>✧</span><span>✦</span><span>✧</span></div>
              <div className="blind-meal-body">
                <div className="blind-meta">
                  <span>{t(`pages.plan.meals.${mealType}`)}</span>
                  <span>{t('blindBox.oneServing')}</span>
                  <span>{t('pages.plan.estimatedTime', { minutes: meal.estimated_preparation_minutes })}</span>
                </div>
                <h2 lang={language}>{plan.title}</h2>
                <p className="text-muted">{t(`blindBox.meals.${recipe.recipe_id}.description`)}</p>
                <div className="blind-actions">
                  <button ref={recipeTrigger} type="button" className="blind-secondary" aria-haspopup="dialog"
                    disabled={spinning} onClick={() => recipeDialog.current?.showModal()}>{t('blindBox.viewRecipe')}</button>
                  <button ref={saveTrigger} type="button" className="blind-primary" aria-haspopup="dialog"
                    disabled={busy || spinning} onClick={() => saveDialog.current?.showModal()}>{t('blindBox.addToPlan')}</button>
                </div>
              </div>
            </article>
            <dialog ref={recipeDialog} id="blind-box-recipe" className="blind-sheet" aria-labelledby="blind-box-recipe-title"
              onClose={() => recipeTrigger.current?.focus({ preventScroll: true })}>
              <div className="blind-sheet-header">
                <h2 id="blind-box-recipe-title" lang={language}>{plan.title}</h2>
                <button type="button" className="blind-secondary" onClick={() => recipeDialog.current?.close()}>{t('blindBox.closePanel')}</button>
              </div>
              <div className="blind-sheet-body" lang={language} tabIndex={0}>
                {meal.dishes.map((dish) => (
                  <div key={dish.name} className="grid gap-3">
                    <h3 className="mt-0">{t('pages.plan.ingredients')}</h3>
                    <ul className="list-disc space-y-1 ps-5">
                      {dish.ingredients.map((ingredient) => (
                        <li key={ingredient.name}>{ingredient.name} {ingredient.quantity} {ingredient.unit}</li>
                      ))}
                    </ul>
                    <h3>{t('pages.plan.instructions')}</h3>
                    <ol className="list-decimal space-y-2 ps-5">
                      {dish.instructions.map((step) => <li key={step}>{step}</li>)}
                    </ol>
                  </div>
                ))}
              </div>
            </dialog>
            <dialog ref={saveDialog} id="blind-box-save" className="blind-sheet" aria-labelledby="blind-box-save-title" aria-busy={busy}
              onCancel={(event) => { if (inFlight.current) event.preventDefault() }}
              onClose={() => {
                setPreview(undefined)
                setMessage((current) => current === 'saved' ? current : '')
                saveTrigger.current?.focus({ preventScroll: true })
              }}>
              <div className="blind-sheet-header">
                <h2 id="blind-box-save-title">{t('blindBox.saveTitle')}</h2>
                <button type="button" className="blind-secondary" disabled={busy}
                  onClick={() => saveDialog.current?.close()}>{t('blindBox.closePanel')}</button>
              </div>
              <div className="blind-sheet-body">
                {import.meta.env.PROD && <p className="text-sm text-muted">{t('release.browserOnly')}</p>}
                {!saveAvailable ? <p>{t(import.meta.env.VITE_LAN_PREVIEW === '1' ? 'blindBox.lanSave' : 'blindBox.saveFailed')}</p> : (
                  <fieldset disabled={busy} className="grid gap-3">
                    <label className="planning-field">
                      {t('blindBox.date')}
                      <input className="planning-input" type="date" value={date} min="0001-01-01" max="9999-12-31"
                        onChange={(event) => { setDate(event.currentTarget.value); clearSave() }} />
                    </label>
                    <label className="planning-field">
                      {t('blindBox.slot')}
                      <select className="planning-input" value={saveSlot}
                        onChange={(event) => {
                          const slot = slots.find((option) => option === event.currentTarget.value)
                          if (slot) { setSaveSlot(slot); clearSave() }
                        }}>
                        {slots.filter((slot) => recipe.meal_types.includes(slot)).map((slot) => (
                          <option key={slot} value={slot}>{t(`pages.plan.meals.${slot}`)}</option>
                        ))}
                      </select>
                    </label>
                    {preview ? (
                      <>
                        <p>{t(existing ? 'release.replacePrompt' : 'blindBox.confirmNew')}</p>
                        <PlanChangeSummary current={existing ? [existing] : []} proposed={preview.choice.plan.meals} />
                        <div className="flex flex-wrap gap-2">
                          <button type="button" className="min-h-11 rounded-xl bg-forest px-4 text-white" onClick={confirmSave}>
                            {t(existing ? 'blindBox.confirmReplace' : 'release.confirmAdd')}
                          </button>
                          <button type="button" className="min-h-11 rounded-xl border border-border px-4" onClick={() => saveDialog.current?.close()}>
                            {t('blindBox.cancel')}
                          </button>
                        </div>
                      </>
                    ) : (
                      <button type="button" disabled={!date || message === 'saved'}
                        className="min-h-11 rounded-xl border border-border px-4" onClick={reviewSave}>
                        {t('blindBox.reviewSave')}
                      </button>
                    )}
                  </fieldset>
                )}
                <p role="status">{busy ? t(import.meta.env.PROD ? 'release.checkingPlan' : 'blindBox.checking')
                  : message && t(import.meta.env.PROD && (message === 'stale' || message === 'saveFailed')
                    ? (message === 'stale' ? 'release.stalePlan' : 'release.saveFailed')
                    : `blindBox.${message}`)}</p>
              </div>
            </dialog>
          </div>
        )}
      </div>
      <p className="text-xs text-muted">{t(import.meta.env.PROD ? 'release.cookNotice' : 'blindBox.demo')}</p>
    </div>
  )
}
