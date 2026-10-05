import { useCallback, useEffect, useState } from 'react'
import { getApplicationReminders, getApplicationSummary, type ApplicationReminders, type ApplicationSummary } from '../../services/applicationService'
import { errorMessage } from './applicationFormat'

export type LoadState = 'loading' | 'ready' | 'error'

// Summary + reminders always come straight from the backend; callers re-run
// `reload` after any mutation so dashboard counts are never stale.
export function useApplicationOverview(reminderDays = 7) {
  const [summary, setSummary] = useState<ApplicationSummary | null>(null)
  const [reminders, setReminders] = useState<ApplicationReminders | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    setState('loading'); setError('')
    try {
      const [nextSummary, nextReminders] = await Promise.all([getApplicationSummary(), getApplicationReminders(reminderDays)])
      setSummary(nextSummary)
      setReminders(nextReminders)
      setState('ready')
    } catch (reason: unknown) {
      setState('error')
      setError(errorMessage(reason, 'We could not load your application activity.'))
    }
  }, [reminderDays])

  useEffect(() => { void reload() }, [reload])

  return { summary, reminders, state, error, reload }
}
