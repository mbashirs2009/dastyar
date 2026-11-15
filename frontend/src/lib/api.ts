import type { AuthResponse, ProfilePatch, User } from './types'
import { clearAccess, getAccess, setAccess } from './auth-store'

export { getAccess, setAccess, clearAccess }

const USER_KEY = 'dastyar_user'

export function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function setStoredUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearToken(): void {
  clearAccess()
  localStorage.removeItem(USER_KEY)
}

/** سازگاری با کد قبلی — توکن فقط در حافظه است. */
export const getToken = getAccess
export const setToken = setAccess

function detailOf(body: unknown, fallback: string): string {
  if (!body) return fallback
  if (typeof body === 'string') return body
  const candidate = body as Record<string, unknown>
  if (typeof candidate.detail === 'string') return candidate.detail
  if (typeof candidate.error === 'object' && candidate.error) {
    const err = candidate.error as { message?: string }
    if (err.message) return err.message
  }
  if (Array.isArray(candidate.detail)) {
    const first = candidate.detail[0] as { msg?: string } | undefined
    if (first?.msg) return first.msg
  }
  return fallback
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  const token = getAccess()
  return fetch(path, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
}

async function refreshAccess(): Promise<string | null> {
  const res = await fetch('/auth/refresh', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) return null
  const body = (await res.json()) as { access_token?: string }
  if (!body.access_token) return null
  setAccess(body.access_token)
  return body.access_token
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res = await rawFetch(path, init)

  if (res.status === 401 && !path.startsWith('/auth/refresh') && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
    const newToken = await refreshAccess()
    if (newToken) {
      res = await rawFetch(path, init)
    } else {
      clearAccess()
      throw new Error('نشست شما منقضی شده؛ دوباره وارد شوید.')
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    if (res.status === 401) {
      clearAccess()
      throw new Error(detailOf(body, 'نشست شما منقضی شده؛ دوباره وارد شوید.'))
    }
    throw new Error(detailOf(body, `خطای ${res.status}`))
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/* ---------------- auth ---------------- */

export interface RegisterPayload {
  email: string
  password: string
  name: string
}

export interface RegisterResult extends Partial<AuthResponse> {
  ok?: boolean
  message?: string
}

export const authApi = {
  register: (payload: RegisterPayload): Promise<AuthResponse | RegisterResult> =>
    api<AuthResponse | RegisterResult>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  login: (email: string, password: string): Promise<AuthResponse> =>
    api<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => api<User>('/auth/me'),

  logout: () => api<{ ok: boolean }>('/auth/logout', { method: 'POST' }),

  refresh: async (): Promise<AuthResponse | null> => {
    const res = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    })
    if (!res.ok) return null
    const body = (await res.json()) as AuthResponse
    setAccess(body.access_token)
    return body
  },

  changePassword: (current_password: string, new_password: string) =>
    api<{ ok: boolean }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
}

/* ---------------- profile ---------------- */

export const profileApi = {
  update: (patch: ProfilePatch) =>
    api<User>('/profile', { method: 'PATCH', body: JSON.stringify(patch) }),
}

/* ---------------- conversations ---------------- */

export interface ConversationRow {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface MessageRow {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface Page<T> {
  items: T[]
  next_cursor: number | null
}

export const chatApi = {
  listConversations: (cursor?: number) => {
    const q = cursor ? `?cursor=${cursor}` : ''
    return api<Page<ConversationRow>>(`/conversations${q}`)
  },
  createConversation: (title?: string) =>
    api<ConversationRow>('/conversations', {
      method: 'POST',
      body: JSON.stringify(title ? { title } : {}),
    }),
  listMessages: (id: number, cursor?: number) => {
    const q = cursor ? `?cursor=${cursor}` : ''
    return api<Page<MessageRow>>(`/conversations/${id}/messages${q}`)
  },
  deleteConversation: (id: number) =>
    api<{ ok: boolean }>(`/conversations/${id}`, { method: 'DELETE' }),
}

/* ---------------- SSE chat ---------------- */

export interface StreamHandlers {
  onToken: (text: string) => void
  onDone: () => void
  onError: (message: string) => void
}

export async function streamChat(
  conversationId: number,
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = getAccess()
  let res: Response
  try {
    res = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ conversation_id: conversationId, message }),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    handlers.onError('ارتباط با سرور برقرار نشد.')
    return
  }

  // access منقضی شد → refresh و یک بار تلاش مجدد
  if (res.status === 401) {
    const newToken = await refreshAccess()
    if (newToken) {
      return streamChat(conversationId, message, handlers, signal)
    }
    clearAccess()
    handlers.onError('نشست شما منقضی شده؛ دوباره وارد شوید.')
    return
  }

  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    handlers.onError(detailOf(body, 'پاسخی دریافت نشد.'))
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        const dataLines = part
          .split('\n')
          .filter((line) => line.startsWith('data: '))
          .map((line) => line.slice(6))
        if (dataLines.length === 0) continue
        if (dataLines.includes('[DONE]')) {
          handlers.onDone()
          return
        }
        const text = dataLines.join('\n')
        if (text) handlers.onToken(text)
      }
    }
    handlers.onDone()
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    handlers.onError('جریان پاسخ قطع شد.')
  }
}
