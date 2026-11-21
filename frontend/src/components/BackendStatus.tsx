import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getHealth } from '../services/health'

type Status = 'loading' | 'connected' | 'unavailable'

export function BackendStatus() {
  const { t } = useTranslation()
  const [attempt, setAttempt] = useState(0)
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    const controller = new AbortController()

    void getHealth(controller.signal).then(
      () => {
        if (!controller.signal.aborted) setStatus('connected')
      },
      () => {
        if (!controller.signal.aborted) setStatus('unavailable')
      },
    )

    return () => controller.abort()
  }, [attempt])

  return (
    <div className="frame flex min-h-8 flex-wrap items-center justify-between gap-x-3 text-xs text-muted">
      <p role="status">{t(`backend.${status}`)}</p>
      {(status === 'unavailable' || (status === 'loading' && attempt > 0)) && (
        <button
          className="min-h-11 cursor-pointer font-semibold text-forest underline underline-offset-4 aria-disabled:cursor-default aria-disabled:opacity-60"
          type="button"
          aria-disabled={status !== 'unavailable'}
          onClick={() => {
            if (status !== 'unavailable') return
            setStatus('loading')
            setAttempt((current) => current + 1)
          }}
        >
          {t('backend.retry')}
        </button>
      )}
    </div>
  )
}
