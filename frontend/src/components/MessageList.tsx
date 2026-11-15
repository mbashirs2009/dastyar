import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../lib/types'
import { Markdown } from './Message'
import { Logo } from './Logo'

interface MessageListProps {
  messages: ChatMessage[]
  streaming: boolean
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-2 text-muted" aria-label="در حال نوشتن">
      <i className="typing-dot" />
      <i className="typing-dot" />
      <i className="typing-dot" />
    </span>
  )
}

export function MessageList({ messages, streaming }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)

  // فقط وقتی کاربر نزدیک پایین است auto-scroll کن — در حین استریم با کاربر نجنگیم
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onScroll = () => {
      const near = el.scrollHeight - el.scrollTop - el.clientHeight < 96
      setPinned(near)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!pinned) return
    const el = containerRef.current
    if (!el) return
    // حین استریم instant — smooth صف می‌شود و با اسکرول کاربر قاطی می‌کند
    el.scrollTo({ top: el.scrollHeight, behavior: 'auto' })
  }, [messages, pinned])

  const scrollToEnd = () => {
    const el = containerRef.current
    el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setPinned(true)
  }

  if (messages.length === 0) {
    return (
      <div ref={containerRef} className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <Logo size={48} className="text-ink" />
        <h1 className="font-display text-2xl font-semibold">چطور می‌توانم کمک کنم؟</h1>
        <p className="max-w-sm text-sm leading-relaxed text-muted">
          سؤال بپرسید، کد بنویسید، یا هر کاری که دارید. پاسخ‌ها سریع و جاری می‌آیند.
        </p>
      </div>
    )
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={containerRef} className="mx-auto h-full w-full max-w-3xl overflow-y-auto px-4 py-6 scroll-area">
        {messages.map((msg) => {
        const isUser = msg.role === 'user'
        const empty = !msg.content && (streaming || msg.stopped)
        return (
          <article
            key={msg.id}
            className={`rise-in group mb-6 flex flex-col ${isUser ? 'items-start' : 'items-end'}`}
          >
            <span className="mb-1 text-[11px] font-medium text-muted">
              {isUser ? 'شما' : 'دستیار'}
            </span>
            <div
              className={`w-fit max-w-full rounded-2xl px-4 py-3 ${
                isUser
                  ? 'rounded-bl-md border border-line bg-bubble text-ink'
                  : 'rounded-br-md border border-line bg-paper'
              } ${msg.error ? 'border-danger/40' : ''}`}
            >
              {empty && streaming && !isUser ? (
                <TypingDots />
              ) : empty && msg.stopped ? (
                <p className="text-sm text-muted">تولید پاسخ متوقف شد.</p>
              ) : isUser ? (
                <p className="whitespace-pre-wrap text-[15.5px] leading-[1.9]">{msg.content}</p>
              ) : (
                <Markdown content={msg.content} />
              )}
            </div>
          </article>
        )
      })}
      <div ref={endRef} />
      </div>
      {!pinned && messages.length > 0 && (
        <button
          onClick={scrollToEnd}
          aria-label="برو به پایین"
          className="lift absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-line bg-raised p-2 text-ink-2 shadow-composer"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M12 5v14M19 12l-7 7-7-7" /></svg>
        </button>
      )}
    </div>
  )
}
