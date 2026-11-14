import { useCallback, useMemo } from 'react'

/** Brand header colour — same value as the accent token and the manifest theme. */
export const TELEGRAM_HEADER_COLOR = '#0F62FE'

export interface TelegramWebAppUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  language_code?: string
  is_premium?: boolean
  photo_url?: string
}

/** Subset of the initData payload we currently read; Telegram may send more. */
export interface TelegramWebAppInitDataUnsafe {
  user?: TelegramWebAppUser
  auth_date?: number
  hash?: string
  start_param?: string
  chat?: { id: number; type: string; title?: string; username?: string }
}

/**
 * The members of `window.Telegram.WebApp` used by this app.
 * Methods that were added in later Bot API versions are optional on purpose:
 * old clients do not expose them at all.
 */
export interface TelegramWebApp {
  initData: string
  initDataUnsafe: TelegramWebAppInitDataUnsafe
  /** "unknown" when the page is not running inside a Telegram client. */
  platform: string
  version: string
  colorScheme: 'light' | 'dark'
  ready: () => void
  expand: () => void
  close?: () => void
  setHeaderColor?: (color: string) => void
  setBackgroundColor?: (color: string) => void
  isVersionAtLeast?: (version: string) => boolean
  onEvent?: (event: string, handler: () => void) => void
  offEvent?: (event: string, handler: () => void) => void
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}

function getWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null
  return window.Telegram?.WebApp ?? null
}

/**
 * `telegram-web-app.js` is loaded on every page (see index.html), so the
 * namespace also exists in a plain browser. A real Mini App always carries
 * `initData` (or, at minimum, a resolved platform instead of "unknown").
 */
function detectMiniApp(app: TelegramWebApp | null): boolean {
  if (!app) return false
  if (app.initData) return true
  if (app.initDataUnsafe?.user) return true
  return typeof app.platform === 'string' && app.platform !== '' && app.platform !== 'unknown'
}

export function useTelegram() {
  const tg = useMemo(getWebApp, [])
  const isTg = useMemo(() => detectMiniApp(tg), [tg])
  const initData = tg?.initData ?? ''

  const ready = useCallback(() => {
    if (!tg) return

    try {
      tg.ready()
    } catch {
      // Client already called ready() — harmless.
    }

    try {
      tg.expand()
    } catch {
      // Older clients without expand support.
    }

    try {
      // Not available before Bot API 6.1 and unsupported in some clients.
      tg.setHeaderColor?.(TELEGRAM_HEADER_COLOR)
    } catch {
      // Keep the client's own header colour.
    }
  }, [tg])

  return { isTg, tg, initData, ready }
}
