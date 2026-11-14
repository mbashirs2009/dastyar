import { useEffect, useState } from 'react'
import { useTelegram } from '../hooks/useTelegram'

/**
 * `beforeinstallprompt` is not in lib.dom yet — Chromium-only, and the event
 * can be used exactly once.
 */
interface BeforeInstallPromptEvent extends Event {
  readonly platforms?: string[]
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

type Status = 'idle' | 'busy' | 'failed'

function readStandalone(): boolean {
  if (typeof window === 'undefined') return false
  const ios =
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  return ios || window.matchMedia('(display-mode: standalone)').matches
}

const BASE =
  'inline-flex h-8 select-none items-center gap-1.5 rounded-[4px] border border-transparent bg-accent px-2.5 text-[12px] font-medium leading-none text-on-accent transition-colors hover:bg-accent-strong active:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'

/**
 * «نصب روی گوشی» — appears only when the browser offers an install prompt.
 * Hidden in standalone mode (already installed) and inside Telegram, where
 * installation happens through the client, not the page.
 */
export function InstallPwa({ className = '' }: { className?: string }) {
  const { isTg } = useTelegram()
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [installed, setInstalled] = useState(readStandalone)
  const [status, setStatus] = useState<Status>('idle')

  useEffect(() => {
    if (installed || isTg) return

    const onPrompt = (event: Event) => {
      // Keep the event; the default banner would compete with the in-app button.
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
    }
    const onInstalled = () => {
      setInstalled(true)
      setDeferred(null)
    }
    const media = window.matchMedia('(display-mode: standalone)')
    const onDisplayMode = () => {
      if (readStandalone()) setInstalled(true)
    }

    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    media.addEventListener?.('change', onDisplayMode)

    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
      media.removeEventListener?.('change', onDisplayMode)
    }
  }, [installed, isTg])

  // A failed prompt is not retryable in place: say so briefly, then hide.
  useEffect(() => {
    if (status !== 'failed') return
    const id = window.setTimeout(() => {
      setStatus('idle')
      setDeferred(null)
    }, 4000)
    return () => window.clearTimeout(id)
  }, [status])

  if (isTg || installed || !deferred) return null

  const install = async () => {
    if (status !== 'idle') return
    setStatus('busy')
    setDeferred(null) // consume before awaiting — the event is one-shot
    const prompt = deferred

    try {
      await prompt.prompt()
      const { outcome } = await prompt.userChoice
      if (outcome === 'accepted') {
        setInstalled(true)
        setStatus('idle')
      } else {
        // Dismissed: Chromium re-fires the event on a later visit.
        setStatus('idle')
      }
    } catch {
      setStatus('failed')
    }
  }

  const label =
    status === 'busy' ? 'در حال نصب…' : status === 'failed' ? 'نصب در دسترس نیست' : 'نصب روی گوشی'

  return (
    <button
      type="button"
      onClick={() => void install()}
      disabled={status !== 'idle'}
      aria-busy={status === 'busy'}
      className={`${BASE} ${className}`.trim()}
    >
      {status === 'busy' ? (
        <span
          aria-hidden="true"
          className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent"
        />
      ) : (
        <svg
          viewBox="0 0 24 24"
          width={14}
          height={14}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3v11" />
          <path d="m7.5 9.5 4.5 4.5 4.5-4.5" />
          <path d="M5 20h14" />
        </svg>
      )}
      {label}
    </button>
  )
}

export default InstallPwa
