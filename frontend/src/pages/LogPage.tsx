import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../services/apiClient'
import {
  canUseFoodLogs, confirmFoodLog, deleteFoodLog, listFoodLogs, logMealTypes, recognizeFoodText, saveFoodLog,
} from '../services/foodLogs'
import type { FoodItem, FoodLog, FoodLogDraft, FoodRecognition, PortionNote } from '../services/foodLogs'
import { localDateTimeValue, timestampAtLocalTime } from '../types/localTime'

const button = 'min-h-11 cursor-pointer rounded-xl border border-border px-3 py-2 font-semibold text-forest hover:bg-sage disabled:cursor-not-allowed disabled:opacity-50'
const primaryButton = 'min-h-11 cursor-pointer rounded-xl bg-forest px-4 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50'

function foodRow(item?: FoodItem, portionNote: PortionNote = null) {
  return {
    key: crypto.randomUUID(), name: item?.name ?? '', quantity: item?.quantity?.toString() ?? '',
    unit: item?.unit ?? '', method: item?.preparation_method ?? '', portionNote,
  }
}

type Row = ReturnType<typeof foodRow>

function initialForm() {
  return { description: '', consumedAt: localDateTimeValue(new Date()), mealType: 'unspecified' as FoodLogDraft['meal_type'],
    rows: [foodRow()], editing: null as FoodLog | null,
    recognized: null as Pick<FoodRecognition, 'description' | 'notes'> | null }
}

function recognitionError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 504) return 'timeout'
    if ([403, 404, 503].includes(error.status)) return 'unavailable'
    if (error.status === 422) return 'input'
    return 'provider'
  }
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'timeout'
  return error instanceof TypeError ? 'network' : 'invalid'
}

function errorKey(error: unknown, action: string) {
  if (error instanceof ApiError) {
    if (error.status === 409 || (error.status === 404 && action !== 'list' && action !== 'create')) return 'conflict'
    if (error.status === 403 || error.status === 404 || error.status === 503) return 'unavailable'
    if (error.status === 422) return 'invalid'
  }
  if (action === 'create') return 'saveUnknown'
  return 'network'
}

export function LogPage() {
  const { t } = useTranslation()
  return (
    <div className="grid gap-6">
      <header>
        <h1>{t('feature.log')}</h1>
        <p className="intro">{t('pages.log.intro')}</p>
      </header>
      {import.meta.env.DEV && canUseFoodLogs()
        ? <LocalFoodLogs />
        : <p className="card p-5 text-muted">{t('pages.log.unavailable')}</p>}
    </div>
  )
}

function LocalFoodLogs() {
  const { t, i18n } = useTranslation()
  const [form, setForm] = useState(initialForm)
  const [view, setView] = useState(() => ({ date: localDateTimeValue(new Date()).slice(0, 10), refresh: 0 }))
  const [list, setList] = useState<{ view: typeof view; logs?: FoodLog[]; error?: string }>()
  const [busy, setBusy] = useState(false)
  const [recognizing, setRecognizing] = useState(false)
  const [recognition, setRecognition] = useState<{ proposal?: FoodRecognition; error?: string }>({})
  const [feedback, setFeedback] = useState<{ error?: string; notice?: string }>({})
  const action = useRef<AbortController | null>(null)
  const formHeading = useRef<HTMLHeadingElement>(null)
  const listHeading = useRef<HTMLHeadingElement>(null)
  const currentList = list?.view === view ? list : undefined
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumSignificantDigits: 15 })
  const proposal = recognition.proposal
  const proposalStale = proposal !== undefined && proposal.description !== form.description
  const appliedStale = form.recognized !== null && form.recognized.description !== form.description

  useEffect(() => {
    const controller = new AbortController()
    void listFoodLogs(view.date, controller.signal).then(
      (logs) => { if (!controller.signal.aborted) setList({ view, logs }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setList({ view, error: errorKey(error, 'list') })
      },
    )
    return () => controller.abort()
  }, [view])

  useEffect(() => () => action.current?.abort(), [])

  function reload(date?: string) {
    setView((previous) => ({ date: date ?? previous.date, refresh: previous.refresh + 1 }))
  }

  async function mutate(
    kind: 'create' | 'update' | 'confirm' | 'delete',
    operation: (signal: AbortSignal) => Promise<FoodLog | void>,
  ) {
    if (action.current) return
    const controller = new AbortController()
    action.current = controller
    setBusy(true)
    setFeedback({})
    try {
      const result = await operation(controller.signal)
      if (controller.signal.aborted) return
      if (kind === 'create' || kind === 'update') {
        setForm(initialForm())
        setRecognition({})
      }
      setFeedback({ notice: kind })
      reload(result?.consumed_at.slice(0, 10))
      listHeading.current?.focus()
    } catch (error) {
      if (controller.signal.aborted) return
      const key = errorKey(error, kind)
      setFeedback({ error: key })
      if (key === 'conflict') reload()
    } finally {
      action.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  function applyRecognition(result: FoodRecognition) {
    if (result.description !== form.description || !result.items.length) return
    setForm((previous) => ({
      ...previous,
      rows: result.items.map((item) => foodRow(item, item.portion_note)),
      recognized: { description: result.description, notes: result.notes },
    }))
    setRecognition({})
  }

  async function recognize() {
    if (action.current) return
    const description = form.description
    if (!description.trim() || Array.from(description).length > 2000) {
      setRecognition((previous) => ({ ...previous, error: 'input' }))
      return
    }
    const controller = new AbortController()
    action.current = controller
    setRecognizing(true)
    setBusy(true)
    setRecognition((previous) => ({ proposal: previous.proposal }))
    try {
      const result = await recognizeFoodText(description, controller.signal)
      if (controller.signal.aborted) return
      const hasEntries = form.rows.length !== 1
        || form.rows.some((row) => row.name || row.quantity || row.unit || row.method)
      if (hasEntries || !result.items.length) setRecognition({ proposal: result })
      else applyRecognition(result)
    } catch (error) {
      if (!controller.signal.aborted) {
        setRecognition((previous) => ({ ...previous, error: recognitionError(error) }))
      }
    } finally {
      action.current = null
      if (!controller.signal.aborted) {
        setBusy(false)
        setRecognizing(false)
      }
    }
  }

  function updateRow(key: string, field: keyof Omit<Row, 'key' | 'portionNote'>, value: string) {
    setForm((previous) => ({
      ...previous,
      rows: previous.rows.map((row) => row.key === key
        ? { ...row, [field]: value, portionNote: field === 'method' ? row.portionNote : null } : row),
    }))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const existing = form.editing
    const consumedAt = existing && existing.consumed_at.slice(0, 16) === form.consumedAt
      ? existing.consumed_at : timestampAtLocalTime(form.consumedAt)
    if (!consumedAt) {
      setFeedback({ error: 'time' })
      return
    }
    if (!form.description.trim() || form.rows.some((row) => !row.name.trim())) {
      setFeedback({ error: 'invalid' })
      return
    }
    const items = form.rows.map((row) => ({
      name: row.name.trim(),
      quantity: row.quantity === '' ? null : Number(row.quantity),
      unit: row.unit.trim() || null,
      preparation_method: row.method.trim() || null,
    }))
    if (items.some(({ quantity }) => quantity !== null && (!Number.isFinite(quantity) || quantity <= 0))) {
      setFeedback({ error: 'quantity' })
      return
    }
    const payload = { description: form.description, consumed_at: consumedAt, meal_type: form.mealType, items }
    const source = form.recognized ? 'ai_text' : 'manual_text'
    void mutate(existing ? 'update' : 'create', (signal) => saveFoodLog(payload, existing, source, signal))
  }

  function edit(log: FoodLog) {
    setForm({
      editing: log, description: log.description, consumedAt: log.consumed_at.slice(0, 16),
      mealType: log.meal_type,
      rows: log.items.map((item) => foodRow(item)),
      recognized: null,
    })
    setRecognition({})
    setFeedback({})
    formHeading.current?.focus()
  }

  return (
    <>
      <p className="rounded-xl bg-sage px-4 py-3 text-sm text-forest">{t('pages.log.local')}</p>
      <p className="sr-only" role="status">{recognizing ? t('pages.log.ai.loading') : busy ? t('pages.log.working') : ''}</p>
      <form className="card grid gap-4 p-4 sm:p-6" onSubmit={submit}>
        <h2 ref={formHeading} tabIndex={-1}>{t(form.editing ? 'pages.log.editTitle' : 'pages.log.newTitle')}</h2>
        {feedback.error && <p role="alert" className="break-words text-red-800">{t(`pages.log.errors.${feedback.error}`)}</p>}
        <fieldset disabled={busy} className="grid min-w-0 gap-4">
          <label className="planning-field">
            {t('pages.log.description')}
            <textarea className="planning-input" rows={4} maxLength={2000} required value={form.description}
              placeholder={t('pages.log.example')}
              onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <div className="grid justify-items-start gap-2">
            <button type="button" className={button} aria-describedby="food-recognition-help"
              onClick={() => void recognize()}>
              {t(recognizing ? 'pages.log.ai.loading' : 'pages.log.ai.action')}
            </button>
            <p id="food-recognition-help" className="text-sm text-muted">{t('pages.log.ai.help')}</p>
            {recognition.error && (
              <p role="alert" className="text-red-800">{t(`pages.log.ai.errors.${recognition.error}`)}</p>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="planning-field">
              {t('pages.log.mealType')}
              <select className="planning-input" value={form.mealType} onChange={(event) => {
                const mealType = logMealTypes.find((type) => type === event.target.value)
                if (mealType) setForm({ ...form, mealType })
              }}>
                {logMealTypes.map((type) => <option value={type} key={type}>{t(`pages.log.meals.${type}`)}</option>)}
              </select>
            </label>
            <label className="planning-field">
              {t('pages.log.consumedAt')}
              <input className="planning-input" type="datetime-local" required value={form.consumedAt}
                onChange={(event) => setForm({ ...form, consumedAt: event.target.value })} />
            </label>
          </div>

          <div className="grid gap-3">
            <div>
              <h3 className="mt-0">{t('pages.log.items')}</h3>
              <p className="mt-1 text-sm text-muted">{t('pages.log.manualHelp')}</p>
            </div>
            {(proposalStale || appliedStale) && (
              <p role="status" className="rounded-xl bg-paper p-3 text-sm">{t('pages.log.ai.stale')}</p>
            )}
            {form.recognized && (
              <div role="status" className="grid gap-1 rounded-xl bg-sage p-3 text-sm text-forest">
                <p>{t('pages.log.ai.applied')}</p>
                {form.recognized.notes.map((note) => <p key={note}>{t(`pages.log.ai.notes.${note}`)}</p>)}
              </div>
            )}
            {proposal && (
              <div className="grid gap-2 rounded-xl border border-border bg-paper p-3">
                <p role="status">{t(proposal.items.length ? 'pages.log.ai.pending' : 'pages.log.ai.empty')}</p>
                {proposal.notes.filter((note) => note !== 'no_identifiable_foods')
                  .map((note) => <p className="text-sm text-muted" key={note}>{t(`pages.log.ai.notes.${note}`)}</p>)}
                {proposal.items.length > 0 && (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                    {proposal.items.map((item, index) => (
                      <li key={index} className="wrap-anywhere">
                        {item.name} · {item.quantity === null ? t('pages.log.unknown') : number.format(item.quantity)}
                        {item.unit && ` ${item.unit}`}{item.preparation_method && ` · ${item.preparation_method}`}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-wrap gap-2">
                  {proposal.items.length > 0 && (
                    <button type="button" className={button} disabled={proposalStale}
                      onClick={() => applyRecognition(proposal)}>{t('pages.log.ai.replace')}</button>
                  )}
                  <button type="button" className={button}
                    onClick={() => setRecognition({})}>{t('pages.log.ai.discard')}</button>
                </div>
              </div>
            )}
            {form.rows.map((row, index) => (
              <fieldset key={row.key} className="grid min-w-0 grid-cols-2 gap-3 rounded-xl border border-border bg-paper p-3">
                <legend className="px-1 text-sm font-semibold">{t('pages.log.itemNumber', { number: index + 1 })}</legend>
                <label className="planning-field col-span-2">
                  {t('pages.log.name')}
                  <input className="planning-input" required maxLength={120} value={row.name}
                    onChange={(event) => updateRow(row.key, 'name', event.target.value)} />
                </label>
                <label className="planning-field">
                  {t('pages.log.quantity')}
                  <input className="planning-input" type="number" inputMode="decimal" min="0" step="any"
                    aria-describedby={row.portionNote ? `portion-${row.key}` : undefined}
                    value={row.quantity} onChange={(event) => updateRow(row.key, 'quantity', event.target.value)} />
                </label>
                {row.portionNote && (
                  <p id={`portion-${row.key}`} className="col-span-2 text-sm text-muted">
                    {t(`pages.log.ai.portions.${row.portionNote}`)}
                  </p>
                )}
                <label className="planning-field">
                  {t('pages.log.unit')}
                  <input className="planning-input" maxLength={120} value={row.unit}
                    onChange={(event) => updateRow(row.key, 'unit', event.target.value)} />
                </label>
                <label className="planning-field col-span-2">
                  {t('pages.log.method')}
                  <input className="planning-input" maxLength={120} value={row.method}
                    onChange={(event) => updateRow(row.key, 'method', event.target.value)} />
                </label>
                {form.rows.length > 1 && (
                  <button type="button" className={`${button} col-span-2 justify-self-start`}
                    aria-label={t('pages.log.removeNumber', { number: index + 1 })}
                    onClick={() => setForm({ ...form, rows: form.rows.filter((item) => item.key !== row.key) })}>
                    {t('pages.log.remove')}
                  </button>
                )}
              </fieldset>
            ))}
            <button type="button" className={`${button} justify-self-start`} disabled={form.rows.length >= 50}
              onClick={() => setForm({ ...form, rows: [...form.rows, foodRow()] })}>{t('pages.log.add')}</button>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={primaryButton}>{t('pages.log.save')}</button>
            {form.editing && (
              <button type="button" className={button} onClick={() => {
                setForm(initialForm())
                setFeedback({})
                setRecognition({})
              }}>
                {t('pages.log.cancelEdit')}
              </button>
            )}
          </div>
        </fieldset>
      </form>

      <section className="grid gap-3" aria-labelledby="food-log-list">
        <h2 ref={listHeading} id="food-log-list" tabIndex={-1}>{t('pages.log.records')}</h2>
        <div className="flex flex-wrap items-end gap-2">
          <label className="planning-field">
            {t('pages.log.viewDate')}
            <input className="planning-input" type="date" min="0001-01-01" max="9999-12-31" value={view.date} disabled={busy}
              onChange={(event) => { if (event.target.validity.valid && event.target.value) reload(event.target.value) }} />
          </label>
          <button type="button" className={button} disabled={busy}
            onClick={() => reload(localDateTimeValue(new Date()).slice(0, 10))}>{t('pages.log.today')}</button>
        </div>
        {feedback.notice && <p role="status" className="text-forest">{t(`pages.log.notices.${feedback.notice}`)}</p>}
        {!currentList && <p role="status" className="text-muted">{t('pages.log.loading')}</p>}
        {currentList?.error && (
          <div className="card grid justify-items-start gap-2 p-4">
            <p role="alert">{t(`pages.log.errors.${currentList.error}`)}</p>
            <button type="button" className={button} onClick={() => reload()}>{t('pages.log.retry')}</button>
          </div>
        )}
        {currentList?.logs?.length === 0 && <p className="card p-4 text-muted">{t('pages.log.empty')}</p>}
        {currentList?.logs?.map((log) => (
          <article key={log.id} className="card grid min-w-0 gap-3 p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="mt-0">{t(`pages.log.meals.${log.meal_type}`)} · <time dateTime={log.consumed_at}>{log.consumed_at.slice(11, 16)}</time></h3>
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ${log.status === 'confirmed' ? 'bg-sage text-forest' : 'border border-border text-muted'}`}>
                {t(`pages.log.statuses.${log.status}`)}
              </span>
            </div>
            <p className="whitespace-pre-wrap wrap-anywhere">{log.description}</p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
              {log.items.map((item, index) => (
                <li key={index} className="wrap-anywhere">
                  {item.name} · {item.quantity === null ? t('pages.log.unknown') : number.format(item.quantity)}
                  {item.unit && ` ${item.unit}`}{item.preparation_method && ` · ${item.preparation_method}`}
                </li>
              ))}
            </ul>
            {log.status === 'confirmed' && <p className="text-sm text-muted">{t('pages.log.locked')}</p>}
            {form.editing?.id === log.id && <p className="text-sm text-muted">{t('pages.log.editing')}</p>}
            <div className="flex flex-wrap gap-2">
              {log.status === 'draft' && (
                <>
                  <button type="button" className={button} disabled={busy}
                    onClick={() => edit(log)}>{t('pages.log.correct')}</button>
                  <button type="button" className={primaryButton} disabled={busy || form.editing?.id === log.id}
                    onClick={() => void mutate('confirm', (signal) => confirmFoodLog(log, signal))}>{t('pages.log.confirm')}</button>
                </>
              )}
              <button type="button" className={`${button} text-red-800`} disabled={busy || form.editing?.id === log.id}
                onClick={() => {
                  if (window.confirm(t('pages.log.confirmDelete'))) void mutate('delete', (signal) => deleteFoodLog(log, signal))
                }}>{t('pages.log.delete')}</button>
            </div>
          </article>
        ))}
      </section>
    </>
  )
}
