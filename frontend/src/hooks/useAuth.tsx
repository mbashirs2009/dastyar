import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi, api, clearToken, getStoredUser, setStoredUser, setAccess } from '../lib/api'
import type { AuthResponse, User } from '../lib/types'
import { useTelegram } from './useTelegram'

interface AuthValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name: string) => Promise<void>
  logout: () => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(() => getStoredUser())
  const [loading, setLoading] = useState<boolean>(true)
  const { initData } = useTelegram()

  const applyAuth = useCallback((res: AuthResponse) => {
    setAccess(res.access_token)
    setUserState(res.user)
    setStoredUser(res.user)
  }, [])

  // Restore session: refresh cookie (OAuth / نشست قبلی) یا تلگرام
  useEffect(() => {
    let cancelled = false

    async function restore() {
      try {
        const res = await authApi.refresh()
        if (cancelled) return
        if (res) {
          setUserState(res.user)
          setStoredUser(res.user)
        } else {
          setUserState(null)
        }
      } catch {
        if (!cancelled) setUserState(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void restore()

    return () => {
      cancelled = true
    }
  }, [])

  // تلگرام: اگر initData آمد و هنوز user نداریم
  useEffect(() => {
    let cancelled = false
    if (!initData || getStoredUser()) return
    api<{ access_token: string; user: User }>('/auth/telegram/verify', {
      method: 'POST',
      body: JSON.stringify({ initData }),
    })
      .then((res) => {
        if (cancelled) return
        applyAuth(res)
        setLoading(false)
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [initData, applyAuth])

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await authApi.login(email, password)
      applyAuth(res)
    },
    [applyAuth],
  )

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await authApi.register({ email, password, name })
      if ('access_token' in res && res.access_token) {
        applyAuth(res as AuthResponse)
        return
      }
      // پیام مبهم ثبت‌نام (ایمیل تکراری) — کاربر را به ورود می‌فرستیم
      const message = (res as { message?: string }).message ?? AMBIGUOUS
      throw new Error(message)
    },
    [applyAuth],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // حتی اگر توکن منقضی بود، خروج محلی انجام می‌شود
    }
    clearToken()
    setUserState(null)
  }, [])

  const setUser = useCallback((next: User) => {
    setUserState(next)
    setStoredUser(next)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, setUser }),
    [user, loading, login, register, logout, setUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

const AMBIGUOUS = 'اگر این ایمیل معتبر باشد، حساب شما فعال است. وارد شوید.'

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
