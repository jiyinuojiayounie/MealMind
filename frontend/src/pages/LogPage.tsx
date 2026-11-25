import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { BindingAction } from '../components/FoodMatchingReview'
import { FoodMatchingReview } from '../components/FoodMatchingReview'
import type { Candidate } from '../services/foodMatching'
import { ApiError } from '../services/apiClient'
import {
  canUseFoodLogs, confirmFoodLog, deleteFoodLog, listFoodLogs, logMealTypes, maxFoodPhotoBytes,
  readBindingError, recognizeFoodImage, recognizeFoodText, referenceSelection, sameFoodItem, saveFoodLog,
} from '../services/foodLogs'
import type { FoodItem, FoodLog, FoodLogDraft, FoodRecognition, PortionNote, RecognitionEvidence, RecognitionSource, ReferenceSelection } from '../services/foodLogs'
import { confirmLocalFoodLog, deleteLocalFoodLog, listLocalFoodLogs, saveLocalFoodLog } from '../services/localFoodLogRepository'
import { localDateTimeValue, timestampAtLocalTime } from '../types/localTime'

const button = 'min-h-11 cursor-pointer rounded-xl border border-border px-3 py-2 font-semibold text-forest hover:bg-sage disabled:cursor-not-allowed disabled:opacity-50'
const primaryButton = 'min-h-11 cursor-pointer rounded-xl bg-forest px-4 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50'

type RowBinding = {
  selection: Omit<ReferenceSelection, 'confirmed'> & { confirmed: boolean }
  state: Candidate['state']
  candidate?: Candidate
  preparation?: string
  saved: boolean
}

function foodRow(
  item?: FoodItem & { recognition_evidence?: RecognitionEvidence },
  portionNote: PortionNote = null, identityUncertain = false,
) {
  return {
    key: crypto.randomUUID(), name: item?.name ?? '', quantity: item?.quantity?.toString() ?? '',
    unit: item?.unit ?? '', method: item?.preparation_method ?? '', portionNote, identityUncertain,
    evidence: item?.recognition_evidence, binding: null as RowBinding | null, invalidBinding: false,
  }
}

function rowItem(row: ReturnType<typeof foodRow>): FoodItem {
  return {
    name: row.name.trim(),
    quantity: row.quantity === '' ? null : Number(row.quantity),
    unit: row.unit.trim() || null,
    preparation_method: row.method.trim() || null,
  }
}

function initialForm() {
  return { creationId: String(crypto.randomUUID()), description: '', consumedAt: localDateTimeValue(new Date()), mealType: 'unspecified' as FoodLogDraft['meal_type'],
    rows: [foodRow()], editing: null as FoodLog | null,
    recognized: null as Pick<FoodRecognition, 'source' | 'description' | 'notes' | 'cooking_evidence'> | null }
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
    if (error.status === 403 || error.status === 404 || error.status === 503) return import.meta.env.PROD ? 'storage' : 'unavailable'
    if (error.status === 422) return 'invalid'
  }
  if (import.meta.env.PROD) return 'storage'
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
      {import.meta.env.PROD || canUseFoodLogs()
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
  const [recognizing, setRecognizing] = useState<RecognitionSource | null>(null)
  const [recognition, setRecognition] = useState<{
    proposal?: FoodRecognition; error?: { source: RecognitionSource; key: string }
  }>({})
  const [photo, setPhoto] = useState<{ file: File; url: string } | null>(null)
  const previewUrl = useRef<string | null>(null)
  const [feedback, setFeedback] = useState<{ error?: string; notice?: string; item?: number; listError?: boolean }>({})
  const action = useRef<AbortController | null>(null)
  const formHeading = useRef<HTMLHeadingElement>(null)
  const listHeading = useRef<HTMLHeadingElement>(null)
  const currentList = list?.view === view ? list : undefined
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumSignificantDigits: 15 })
  const proposal = recognition.proposal
  const proposalStale = proposal?.source === 'ai_text' && proposal.description !== form.description
  const appliedStale = form.recognized?.source === 'ai_text' && form.recognized.description !== form.description
  const cookingEvidence = proposal
    ? (proposalStale ? undefined : proposal.cooking_evidence)
    : (appliedStale ? undefined : form.recognized?.cooking_evidence)

  useEffect(() => {
    const controller = new AbortController()
    void (import.meta.env.PROD ? listLocalFoodLogs(view.date) : listFoodLogs(view.date, controller.signal)).then(
      (logs) => { if (!controller.signal.aborted) setList({ view, logs }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setList({ view, error: errorKey(error, 'list') })
      },
    )
    return () => controller.abort()
  }, [view])

  useEffect(() => () => {
    action.current?.abort()
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
  }, [])

  function changePhoto(file?: File) {
    if (recognizing === 'ai_image') {
      action.current?.abort()
      action.current = null
      setRecognizing(null)
      setBusy(false)
    }
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
    previewUrl.current = null
    setPhoto(null)
    setRecognition((previous) => ({
      proposal: previous.proposal?.source === 'ai_image' ? undefined : previous.proposal,
      error: previous.error?.source === 'ai_image' ? undefined : previous.error,
    }))
    if (!file) return
    const supported = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)
      || ((!file.type || file.type === 'application/octet-stream') && /\.(jpe?g|png|webp)$/i.test(file.name))
    const key = !supported ? 'format' : file.size > maxFoodPhotoBytes ? 'size' : !file.size ? 'corrupt' : null
    if (key) {
      setRecognition((previous) => ({ ...previous, error: { source: 'ai_image', key } }))
      return
    }
    const url = URL.createObjectURL(file)
    previewUrl.current = url
    setPhoto({ file, url })
  }

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
        changePhoto()
        setRecognition({})
      }
      setFeedback({ notice: kind === 'update' && result?.status === 'confirmed' ? 'corrected' : kind })
      reload(result?.consumed_at.slice(0, 10))
      listHeading.current?.focus()
    } catch (error) {
      if (controller.signal.aborted) return
      const listError = kind === 'confirm' || kind === 'delete'
      const bindingError = readBindingError(error)
      if (bindingError) {
        setFeedback({ error: bindingError.key, item: bindingError.index + 1, listError })
        return
      }
      const key = errorKey(error, kind)
      setFeedback({ error: key, listError })
      if (key === 'conflict') reload()
    } finally {
      action.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  function applyRecognition(result: FoodRecognition) {
    if (!result.items.length || (result.source === 'ai_text' && result.description !== form.description)) return
    setForm((previous) => ({
      ...previous,
      rows: result.items.map((item) => foodRow(item, item.portion_note, item.identity_uncertain)),
      recognized: { source: result.source, description: result.description, notes: result.notes, cooking_evidence: result.cooking_evidence },
    }))
    setRecognition({})
  }

  async function recognize(source: RecognitionSource) {
    if (action.current) return
    const description = form.description
    if (source === 'ai_image' && !photo) return
    if (source === 'ai_text' && (!description.trim() || Array.from(description).length > 2000)) {
      setRecognition((previous) => ({ ...previous, error: { source, key: 'input' } }))
      return
    }
    const controller = new AbortController()
    action.current = controller
    setRecognizing(source)
    setBusy(true)
    setRecognition((previous) => ({ proposal: previous.proposal }))
    try {
      const result = source === 'ai_image' && photo
        ? await recognizeFoodImage(photo.file, controller.signal)
        : await recognizeFoodText(description, controller.signal)
      if (controller.signal.aborted || (source === 'ai_image' && previewUrl.current !== photo?.url)) return
      const hasEntries = form.rows.length !== 1
        || form.rows.some((row) => row.name || row.quantity || row.unit || row.method)
      if (hasEntries || !result.items.length) setRecognition({ proposal: result })
      else applyRecognition(result)
    } catch (error) {
      if (!controller.signal.aborted) {
        const key = source === 'ai_image' && error instanceof ApiError
          ? ({ 400: 'corrupt', 413: 'size', 415: 'format' }[error.status] ?? recognitionError(error))
          : recognitionError(error)
        setRecognition((previous) => ({ ...previous, error: { source, key } }))
      }
    } finally {
      if (action.current === controller && !controller.signal.aborted) {
        action.current = null
        setBusy(false)
        setRecognizing(null)
      }
    }
  }

  function updateRow(key: string, field: 'name' | 'quantity' | 'unit' | 'method', value: string) {
    setForm((previous) => ({
      ...previous,
      rows: previous.rows.map((row) => row.key === key
        ? { ...row, [field]: value, portionNote: field === 'method' ? row.portionNote : null,
            identityUncertain: field === 'name' ? false : row.identityUncertain,
            evidence: undefined, binding: null, invalidBinding: false } : row),
    }))
  }

  function changeReference(key: string, item: FoodItem, candidate: Candidate, version: string, action: BindingAction) {
    setForm((previous) => ({
      ...previous,
      rows: previous.rows.map((row) => {
        if (row.key !== key || !sameFoodItem(rowItem(row), item)) return row
        const binding = row.binding
        const current = binding?.selection.food_id === candidate.food_id
          && binding.selection.reference_version === version ? binding.selection : undefined
        if (action.type === 'choose' && current) return row
        return {
          ...row,
          binding: {
            selection: {
              food_id: candidate.food_id, reference_version: version, item,
              confirmed: action.type === 'confirm' || current?.confirmed === true,
              edible_weight_confirmed: action.type === 'weight' ? action.checked : current?.edible_weight_confirmed ?? false,
            },
            state: candidate.state, candidate, saved: false,
          },
          invalidBinding: false,
        }
      }),
    }))
    setFeedback({})
  }

  function clearReference(key: string) {
    setForm((previous) => ({
      ...previous,
      rows: previous.rows.map((row) => row.key === key ? { ...row, binding: null, invalidBinding: false } : row),
    }))
    setFeedback({})
  }

  function moveRow(index: number, offset: number) {
    setForm((previous) => {
      const rows = [...previous.rows]
      const target = index + offset
      if (target < 0 || target >= rows.length) return previous
      const row = rows[index]
      rows[index] = rows[target]
      rows[target] = row
      return { ...previous, rows }
    })
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
    if (!form.rows.length || form.rows.some((row) => !row.name.trim())) {
      setFeedback({ error: 'items' })
      return
    }
    if (form.rows.some((row) => row.invalidBinding)) {
      setFeedback({ error: 'bindingInvalid', item: form.rows.findIndex((row) => row.invalidBinding) + 1 })
      return
    }
    const items = form.rows.map((row) => {
      const item = { ...rowItem(row), ...(row.evidence && { recognition_evidence: row.evidence }) }
      return row.binding?.selection.confirmed && sameFoodItem(item, row.binding.selection.item)
        ? { ...item, reference_binding: { ...row.binding.selection, confirmed: true as const } }
        : item
    })
    if (event.currentTarget.querySelector('input[type="number"]:invalid')
      || items.some(({ quantity }) => quantity !== null && (!Number.isFinite(quantity) || quantity <= 0))) {
      setFeedback({ error: 'quantity' })
      return
    }
    const payload = {
      description: form.description.trim() ? form.description : null,
      consumed_at: consumedAt, meal_type: form.mealType, items,
    }
    const source = form.recognized?.source ?? 'manual_text'
    void mutate(existing ? 'update' : 'create', (signal) => import.meta.env.PROD
      ? saveLocalFoodLog(payload, existing, form.creationId)
      : saveFoodLog(payload, existing, source, signal))
  }

  function edit(log: FoodLog) {
    setForm({
      creationId: log.id, editing: log, description: log.description ?? '', consumedAt: log.consumed_at.slice(0, 16),
      mealType: log.meal_type,
      rows: log.items.map((item) => {
        const row = foodRow(item)
        const binding = item.reference_binding
        if (!binding) return row
        if ('status' in binding || !sameFoodItem(item, binding.item)) return { ...row, invalidBinding: true }
        return { ...row, binding: { selection: referenceSelection(binding), state: binding.state, preparation: binding.preparation, saved: true } }
      }),
      recognized: null,
    })
    changePhoto()
    setRecognition({})
    setFeedback({})
    formHeading.current?.focus()
  }

  const matchingEntries = form.rows.map((row) => ({
    selection: row.binding?.selection,
    rowKey: row.key, item: rowItem(row), identity_uncertain: row.identityUncertain,
  })).filter(({ item }) => item.name && (item.quantity === null || (Number.isFinite(item.quantity) && item.quantity > 0)))
  // Reset suggestions and local choices whenever the candidate input changes.
  const matchingKey = JSON.stringify(matchingEntries.map(({ rowKey, item, identity_uncertain }) => ({ rowKey, item, identity_uncertain })))

  return (
    <>
      <p className="rounded-xl bg-sage px-4 py-3 text-sm text-forest">{t(import.meta.env.PROD ? 'pages.log.browserLocal' : 'pages.log.local')}</p>
      <p className="sr-only" role="status">
        {recognizing === 'ai_image' ? t('pages.log.photo.loading')
          : recognizing ? t('pages.log.ai.loading') : busy ? t('pages.log.working') : ''}
      </p>
      <form className="card grid gap-4 p-4 sm:p-6" onSubmit={submit} noValidate>
        <h2 ref={formHeading} tabIndex={-1}>{t(form.editing?.status === 'confirmed' ? 'pages.log.editConfirmedTitle' : form.editing ? 'pages.log.editTitle' : 'pages.log.newTitle')}</h2>
        {feedback.error && !feedback.listError && <p id="food-log-error" role="alert" className="break-words text-red-800">{t(`pages.log.errors.${feedback.error}`, { number: feedback.item })}</p>}
        <fieldset disabled={busy} className="grid min-w-0 gap-4">
          <label className="planning-field">
            {t('pages.log.description')}
            <textarea className="planning-input" rows={4} maxLength={2000} value={form.description}
              placeholder={t('pages.log.example')}
              onChange={(event) => {
                const description = event.target.value
                setForm((previous) => ({
                  ...previous, description,
                  rows: previous.rows.map((row) => row.evidence ? { ...row, evidence: undefined } : row),
                }))
              }} />
          </label>
          {import.meta.env.DEV && (
            <div className="grid justify-items-start gap-2">
              <button type="button" className={button} aria-describedby="food-recognition-help"
                onClick={() => void recognize('ai_text')}>
                {t(recognizing === 'ai_text' ? 'pages.log.ai.loading' : 'pages.log.ai.action')}
              </button>
              <p id="food-recognition-help" className="text-sm text-muted">{t('pages.log.ai.help')}</p>
              {recognition.error?.source === 'ai_text' && (
                <p role="alert" className="text-red-800">{t(`pages.log.ai.errors.${recognition.error.key}`)}</p>
              )}
            </div>
          )}
        </fieldset>
        {import.meta.env.DEV && (
          <fieldset disabled={busy && recognizing !== 'ai_image'} className="grid min-w-0 gap-2 border-t border-border pt-3">
            <label className="planning-field">
              {t('pages.log.photo.label')}
              <input type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                aria-describedby="photo-recognition-help"
                className="w-full min-w-0 text-sm text-muted file:mr-2 file:min-h-11 file:cursor-pointer file:rounded-xl file:border file:border-border file:bg-surface file:px-3 file:font-semibold file:text-forest"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0]
                  if (file) changePhoto(file)
                  event.currentTarget.value = ''
                }} />
            </label>
            <p id="photo-recognition-help" className="text-sm text-muted">{t('pages.log.photo.help')}</p>
            {photo && (
              <>
                <img key={photo.url} src={photo.url} alt={t('pages.log.photo.preview')}
                  className="max-h-36 max-w-full rounded-xl object-contain"
                  onError={() => {
                    if (previewUrl.current !== photo.url) return
                    changePhoto()
                    setRecognition((previous) => ({ ...previous, error: { source: 'ai_image', key: 'corrupt' } }))
                  }} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={button} disabled={busy} onClick={() => void recognize('ai_image')}>
                    {t(recognizing === 'ai_image' ? 'pages.log.photo.loading' : 'pages.log.photo.action')}
                  </button>
                  <button type="button" className={button} onClick={() => changePhoto()}>{t('pages.log.photo.remove')}</button>
                </div>
              </>
            )}
            {recognition.error?.source === 'ai_image' && (
              <p role="alert" className="text-red-800">
                {t(`pages.log.ai.errors.${recognition.error.key}`)}
              </p>
            )}
          </fieldset>
        )}
        <fieldset disabled={busy} className="grid min-w-0 gap-4">
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
                aria-invalid={feedback.error === 'time'}
                aria-describedby={feedback.error === 'time' ? 'food-log-error' : undefined}
                onChange={(event) => setForm({ ...form, consumedAt: event.target.value })} />
            </label>
          </div>

          <div className="grid gap-3">
            <div>
              <h3 className="mt-0">{t('pages.log.items')}</h3>
              <p className="mt-1 text-sm text-muted">{t('pages.log.manualHelp')}</p>
            </div>
            {(form.recognized || form.editing?.recognition_weight_review) && (
              <p className="text-sm text-muted">{t('pages.log.ai.reviewWeight')}</p>
            )}
            {(proposalStale || appliedStale) && (
              <p role="status" className="rounded-xl bg-paper p-3 text-sm">{t('pages.log.ai.stale')}</p>
            )}
            {form.recognized && (
              <div role="status" className="grid gap-1 rounded-xl bg-sage p-3 text-sm text-forest">
                <p>{t('pages.log.ai.applied')}</p>
                {form.recognized.notes.map((note) => <p key={note}>{t(`pages.log.ai.notes.${note}`)}</p>)}
              </div>
            )}
            {cookingEvidence && cookingEvidence.length > 0 && (
              <div className="grid gap-1 rounded-xl bg-sage p-3 text-sm" role="status">
                <p>{t('pages.log.ai.cookingContextOnly')}</p>
                <ul className="list-disc pl-5">
                  {cookingEvidence.map(({ quote }, index) => <li key={index}>{quote}</li>)}
                </ul>
              </div>
            )}
            {proposal && (
              <div className="grid gap-2 rounded-xl border border-border bg-paper p-3">
                <p role="status">{t(proposal.items.length ? 'pages.log.ai.pending' : cookingEvidence?.length ? 'pages.log.ai.noConsumedItems' : 'pages.log.ai.empty')}</p>
                {proposal.notes.filter((note) => note !== 'no_identifiable_foods')
                  .map((note) => <p className="text-sm text-muted" key={note}>{t(`pages.log.ai.notes.${note}`)}</p>)}
                {proposal.items.length > 0 && (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                    {proposal.items.map((item, index) => (
                      <li key={index} className="wrap-anywhere">
                        {item.name} · {item.quantity === null ? t('pages.log.unknown') : number.format(item.quantity)}
                        {item.unit && ` ${item.unit}`}{item.preparation_method && ` · ${item.preparation_method}`}
                        {item.identity_uncertain && ` · ${t('pages.log.photo.uncertain')}`}
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
                    aria-invalid={feedback.error === 'items' && !row.name.trim()}
                    aria-describedby={[
                      row.identityUncertain && `identity-${row.key}`,
                      feedback.error === 'items' && !row.name.trim() && 'food-log-error',
                    ].filter(Boolean).join(' ') || undefined}
                    onChange={(event) => updateRow(row.key, 'name', event.target.value)} />
                </label>
                {row.identityUncertain && (
                  <p id={`identity-${row.key}`} className="col-span-2 text-sm text-muted">{t('pages.log.photo.uncertain')}</p>
                )}
                <label className="planning-field">
                  {t('pages.log.quantity')}
                  <input className="planning-input" type="number" inputMode="decimal" min="0" step="any"
                    aria-describedby={[
                      row.portionNote && `portion-${row.key}`,
                      feedback.error === 'quantity' && 'food-log-error',
                    ].filter(Boolean).join(' ') || undefined}
                    value={row.quantity} onChange={(event) => updateRow(row.key, 'quantity', event.target.value)} />
                </label>
                {row.evidence && (
                  <div className="col-span-2 break-words rounded-xl bg-sage p-2 text-sm">
                    <p>{t('pages.log.ai.evidence', { quote: row.evidence.quote })}</p>
                    {row.evidence.weighing_text && (
                      <p>{t('pages.log.ai.weighing', { text: row.evidence.weighing_text })}</p>
                    )}
                    {row.evidence.decision === 'withheld' && (
                      <p>{t(row.evidence.context === 'cooking_input'
                        ? 'pages.log.ai.cookingEvidence' : 'pages.log.ai.withheldEvidence')}</p>
                    )}
                  </div>
                )}
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
                {(row.binding || row.invalidBinding) && (
                  <div className="col-span-2 grid gap-1 rounded-xl bg-sage p-2 text-sm">
                    <p role="status">{row.binding ? t(
                      row.binding.saved ? 'pages.log.matching.saved'
                        : row.binding.selection.confirmed ? 'pages.log.matching.pendingSave' : 'pages.log.matching.awaitingConfirmation',
                      { state: t(`pages.log.matching.states.${row.binding.state}`) },
                    ) : t('pages.log.matching.invalidSaved')}</p>
                    {row.binding?.candidate && <p>{i18n.resolvedLanguage?.startsWith('zh')
                      ? row.binding.candidate.names.zh_cn : row.binding.candidate.names.en_us}</p>}
                    {row.binding?.preparation && <p lang="en">{row.binding.preparation}</p>}
                    {row.binding?.selection.edible_weight_confirmed && <p>{t('pages.log.matching.weightConfirmed')}</p>}
                    <button type="button" className={`${button} justify-self-start`} onClick={() => clearReference(row.key)}>
                      {t('pages.log.matching.clear')}
                    </button>
                  </div>
                )}
                {form.rows.length > 1 && (
                  <div className="col-span-2 flex flex-wrap gap-2">
                    <button type="button" className={button} disabled={index === 0}
                      onClick={() => moveRow(index, -1)} aria-label={t('pages.log.moveUpNumber', { number: index + 1 })}>
                      {t('pages.log.moveUp')}
                    </button>
                    <button type="button" className={button} disabled={index === form.rows.length - 1}
                      onClick={() => moveRow(index, 1)} aria-label={t('pages.log.moveDownNumber', { number: index + 1 })}>
                      {t('pages.log.moveDown')}
                    </button>
                    <button type="button" className={button}
                      aria-label={t('pages.log.removeNumber', { number: index + 1 })}
                      onClick={() => setForm({ ...form, rows: form.rows.filter((item) => item.key !== row.key) })}>
                      {t('pages.log.remove')}
                    </button>
                  </div>
                )}
              </fieldset>
            ))}
            <button type="button" className={`${button} justify-self-start`} disabled={form.rows.length >= 50}
              onClick={() => setForm({ ...form, rows: [...form.rows, foodRow()] })}>{t('pages.log.add')}</button>
          </div>
          {import.meta.env.DEV && <FoodMatchingReview key={matchingKey} entries={matchingEntries} buttonClass={button} onBindingAction={changeReference} onClear={clearReference} />}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={primaryButton}>{t(import.meta.env.PROD && form.editing?.status === 'confirmed' ? 'pages.log.saveCorrection' : 'pages.log.save')}</button>
            {form.editing && (
              <button type="button" className={button} onClick={() => {
                setForm(initialForm())
                changePhoto()
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
        {feedback.error && feedback.listError && (
          <p role="alert" className="break-words text-red-800">{t(`pages.log.errors.${feedback.error}`, { number: feedback.item })}</p>
        )}
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
            {log.description && <p className="whitespace-pre-wrap wrap-anywhere">{log.description}</p>}
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
              {log.items.map((item, index) => (
                <li key={index} className="wrap-anywhere">
                  {item.name} · {item.quantity === null ? t('pages.log.unknown') : number.format(item.quantity)}
                  {item.unit && ` ${item.unit}`}{item.preparation_method && ` · ${item.preparation_method}`}
                </li>
              ))}
            </ul>
            {import.meta.env.DEV && log.status === 'confirmed' && <p className="text-sm text-muted">{t('pages.log.locked')}</p>}
            {form.editing?.id === log.id && <p className="text-sm text-muted">{t('pages.log.editing')}</p>}
            <div className="flex flex-wrap gap-2">
              {(import.meta.env.PROD || log.status === 'draft') && (
                <button type="button" className={button} disabled={busy}
                  onClick={() => edit(log)}>{t(log.status === 'confirmed' ? 'pages.log.correctConfirmed' : 'pages.log.correct')}</button>
              )}
              {log.status === 'draft' && (
                <button type="button" className={primaryButton} disabled={busy || form.editing?.id === log.id}
                  onClick={() => void mutate('confirm', (signal) => import.meta.env.PROD
                    ? confirmLocalFoodLog(log) : confirmFoodLog(log, signal))}>{t('pages.log.confirm')}</button>
              )}
              <button type="button" className={`${button} text-red-800`} disabled={busy || form.editing?.id === log.id}
                onClick={() => {
                  if (window.confirm(t('pages.log.confirmDelete'))) void mutate('delete', (signal) => import.meta.env.PROD ? deleteLocalFoodLog(log) : deleteFoodLog(log, signal))
                }}>{t('pages.log.delete')}</button>
            </div>
          </article>
        ))}
      </section>
    </>
  )
}
