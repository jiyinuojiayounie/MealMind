import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { previewFoodMatching } from '../services/foodMatching'
import type { Candidate, MatchingEntry } from '../services/foodMatching'
import type { ReferenceSelection } from '../services/foodLogs'

type Preview = Awaited<ReturnType<typeof previewFoodMatching>>
const identityReasons = [
  'state_and_edible_basis', 'preparation_and_edible_basis', 'measurement_state', 'conflicting_preparation',
  'grain_variety', 'egg_doneness', 'food_and_state', 'vegetable_and_preparation', 'tofu_type_and_preparation',
  'check_spelling', 'confirm_identity',
]

export type BindingAction =
  | { type: 'choose' }
  | { type: 'weight'; checked: boolean }
  | { type: 'confirm' }

export function FoodMatchingReview({ entries, buttonClass, onBindingAction, onClear }: {
  entries: (MatchingEntry & { rowKey: string; selection?: Omit<ReferenceSelection, 'confirmed'> & { confirmed: boolean } })[]
  buttonClass: string
  onBindingAction: (key: string, item: MatchingEntry['item'], candidate: Candidate, version: string, action: BindingAction) => void
  onClear: (key: string) => void
}) {
  const { t, i18n } = useTranslation()
  const [preview, setPreview] = useState<Preview>()
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => pending.current?.abort(), [])

  async function review() {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setStatus('loading')
    setPreview(undefined)
    try {
      const suggestions = await previewFoodMatching(
        entries.map(({ item, identity_uncertain }) => ({ item, identity_uncertain })), controller.signal,
      )
      if (!controller.signal.aborted) {
        setPreview(suggestions)
        setStatus('idle')
      }
    } catch {
      if (!controller.signal.aborted) setStatus('error')
    } finally {
      pending.current = null
    }
  }

  function name(item: Candidate) {
    return i18n.resolvedLanguage?.startsWith('zh') ? item.names.zh_cn : item.names.en_us
  }

  if (!entries.length) return null

  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <button type="button" className={`${buttonClass} justify-self-start`}
        onClick={() => void review()} disabled={status === 'loading'}>
        {t('pages.log.matching.action')}
      </button>
      {(status !== 'idle' || preview) && (
        <p role="status">{t(`pages.log.matching.${status === 'idle' ? 'reviewHelp' : status}`)}</p>
      )}
      {preview && (
        <ul className="grid gap-2">
          {preview.map((item, index) => {
            const entry = entries[index]
            const selection = entry.selection?.reference_version === item.reference_version ? entry.selection : undefined
            const selected = item.reference ?? item.candidates.find((option) => option.food_id === selection?.food_id)
            const askWeight = selected && item.requires_edible_weight_confirmation
            const weightConfirmed = selected?.food_id === selection?.food_id && selection?.edible_weight_confirmed
            const apply = (candidate: Candidate, action: BindingAction) =>
              onBindingAction(entry.rowKey, entry.item, candidate, item.reference_version, action)
            return (
              <li key={entry.rowKey} className="grid min-w-0 gap-1 rounded-xl border border-border px-3 py-2 wrap-anywhere">
                <p className="font-semibold">{entry.item.name}</p>
                <p>{item.reference
                  ? t('pages.log.matching.identified', { name: name(item.reference) })
                  : t(`pages.log.matching.identity.${item.identity_status}`)}</p>
                {item.clarification && identityReasons.includes(item.clarification) && (
                  <p className="text-muted">{t(`pages.log.matching.reasons.${item.clarification}`)}</p>
                )}
                {item.portion_status !== 'edible_mass' && !(askWeight && item.portion_status === 'needs_review') && (
                  <p className="text-muted">{t(`pages.log.matching.portion.${item.portion_status}`)}</p>
                )}
                {item.candidates.length > 0 && (
                  <label className="planning-field mt-1">
                    {t('pages.log.matching.choose', { name: entry.item.name })}
                    <select className="planning-input min-w-0" value={selected?.food_id ?? ''}
                      onChange={(event) => {
                        const candidate = item.candidates.find((option) => option.food_id === event.target.value)
                        if (candidate) apply(candidate, { type: 'choose' })
                        else onClear(entry.rowKey)
                      }}>
                      <option value="">{t('pages.log.matching.unselected')}</option>
                      {item.candidates.map((option) => (
                        <option key={option.food_id} value={option.food_id}>
                          {name(option)} · {t(`pages.log.matching.states.${option.state}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {selected && (
                  <div className="grid gap-2">
                    {askWeight && (
                      <label className="flex items-start gap-2 py-1">
                        <input type="checkbox" className="mt-1 shrink-0" checked={Boolean(weightConfirmed)}
                          onChange={(event) => apply(selected, { type: 'weight', checked: event.target.checked })} />
                        <span>{t('pages.log.matching.edibleWeight', { name: name(selected) })}</span>
                      </label>
                    )}
                    <button type="button" className={`${buttonClass} justify-self-start`}
                      onClick={() => apply(selected, { type: 'confirm' })}>
                      {t('pages.log.matching.confirmReference', { name: name(selected) })}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
