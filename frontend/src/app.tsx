import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent } from 'react'
import { api, downloadExport, loadSession, request, setCsrfToken } from './lib/api'
import type { VaultRecord } from './types'

type SessionState = {
  ready: boolean
  authenticated: boolean
  setupRequired: boolean
  error: string
}

const SCALE_KEY = 'personal-vault-text-scale'
const MIN_SCALE = 80
const MAX_SCALE = 150

function readScale(): number {
  try {
    const value = Number(localStorage.getItem(SCALE_KEY) || 100)
    if (!Number.isFinite(value)) return 100
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(value / 5) * 5))
  } catch {
    return 100
  }
}

function dayKey(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function dayLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (dayKey(value) === dayKey(today.toISOString())) return 'Today'
  if (dayKey(value) === dayKey(yesterday.toISOString())) return 'Yesterday'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date)
}

function timeLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date)
}

function App() {
  const [session, setSession] = useState<SessionState>({ ready: false, authenticated: false, setupRequired: false, error: '' })
  const [scale, setScale] = useState(readScale)

  useEffect(() => {
    document.documentElement.dataset.textScale = String(scale)
    try { localStorage.setItem(SCALE_KEY, String(scale)) } catch { /* local preference is optional */ }
  }, [scale])

  useEffect(() => {
    let active = true
    loadSession()
      .then((value) => {
        if (!active) return
        setSession({ ready: true, authenticated: value.authenticated, setupRequired: value.setup_required, error: '' })
        if (value.authenticated && window.location.pathname === '/login') {
          window.history.replaceState({}, '', '/')
        }
      })
      .catch((error: unknown) => {
        if (!active) return
        setSession({ ready: true, authenticated: false, setupRequired: false, error: error instanceof Error ? error.message : 'Could not connect to the Vault service.' })
      })
    return () => { active = false }
  }, [])

  if (!session.ready) return <div className="screen-state">Opening your vault…</div>
  if (session.error) return <div className="screen-state"><div className="state-card"><h1>Personal Vault</h1><p>{session.error}</p><button className="plain-button" onClick={() => window.location.reload()}>Reload</button></div></div>
  if (!session.authenticated) {
    return <LoginScreen setupRequired={session.setupRequired} onSuccess={() => setSession((current) => ({ ...current, authenticated: true, setupRequired: false }))} />
  }
  return <ChatRoom scale={scale} onScaleChange={setScale} />
}

function LoginScreen({ setupRequired, onSuccess }: { setupRequired: boolean; onSuccess: () => void }) {
  const [setup, setSetup] = useState(setupRequired)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [setupKey, setSetupKey] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    loadSession().then((value) => {
      setSetup(value.setup_required)
      if (value.authenticated) onSuccess()
    }).catch(() => setError('Could not connect to the Vault service.'))
  }, [onSuccess])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (setup && password !== confirmPassword) throw new Error('The passwords do not match.')
      if (setup && !setupKey.trim()) throw new Error('Enter the one-time setup key from your hosting settings.')
      const endpoint = setup ? '/api/auth/setup' : '/api/auth/login'
      const payload = setup
        ? { password, confirm_password: confirmPassword, setup_key: setupKey }
        : { password }
      const result = await request<{ ok: boolean; csrf_token: string }>(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setCsrfToken(result.csrf_token)
      onSuccess()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Authentication failed.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="login-screen">
    <form className="login-card" onSubmit={submit}>
      <h1>Personal Vault</h1>
      <p>{setup ? 'Create your private workspace' : 'Sign in to your vault'}</p>
      {setup ? <>
        <label htmlFor="setup-password">Create password</label>
        <input id="setup-password" type="password" minLength={16} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        <label htmlFor="setup-key">One-time setup key</label>
        <input id="setup-key" type="password" autoComplete="off" value={setupKey} onChange={(event) => setSetupKey(event.target.value)} required />
        <label htmlFor="setup-confirm">Confirm password</label>
        <input id="setup-confirm" type="password" minLength={16} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
      </> : <>
        <label htmlFor="vault-password">Password</label>
        <input id="vault-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required autoFocus />
      </>}
      {error ? <div className="inline-error" role="alert">{error}</div> : null}
      <button className="login-submit" type="submit" disabled={busy || !password || (setup && (!setupKey || !confirmPassword))}>{busy ? 'Please wait…' : setup ? 'Create Vault' : 'Continue'}</button>
    </form>
  </main>
}

function ChatRoom({ scale, onScaleChange }: { scale: number; onScaleChange: (value: number) => void }) {
  const [records, setRecords] = useState<VaultRecord[]>([])
  const [composer, setComposer] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [sending, setSending] = useState(false)
  const [importing, setImporting] = useState(false)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [status, setStatus] = useState('')
  const threadRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const importInputRef = useRef<HTMLInputElement | null>(null)


  useEffect(() => {
    let active = true
    api.messages(1, 100)
      .then((result) => {
        if (!active) return
        setRecords([...result.records].reverse())
        setPage(result.page)
        setTotalPages(result.total_pages)
        requestAnimationFrame(() => {
          const thread = threadRef.current
          if (thread) thread.scrollTop = thread.scrollHeight
        })
      })
      .catch((error: unknown) => setStatus(error instanceof Error ? error.message : 'Could not load messages.'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!status) return
    const timer = window.setTimeout(() => setStatus(''), 5000)
    return () => window.clearTimeout(timer)
  }, [status])

  useEffect(() => {
    if (!settingsOpen) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setSettingsOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [settingsOpen])

  function scrollToBottom() {
    requestAnimationFrame(() => {
      const thread = threadRef.current
      if (thread) thread.scrollTop = thread.scrollHeight
    })
  }

  async function loadOlder() {
    if (loadingOlder || page >= totalPages) return
    const thread = threadRef.current
    const previousHeight = thread?.scrollHeight || 0
    const previousTop = thread?.scrollTop || 0
    setLoadingOlder(true)
    try {
      const result = await api.messages(page + 1, 100)
      setRecords((current) => [...result.records].reverse().concat(current))
      setPage(result.page)
      setTotalPages(result.total_pages)
      requestAnimationFrame(() => {
        const element = threadRef.current
        if (element) element.scrollTop = element.scrollHeight - previousHeight + previousTop
      })
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not load older messages.')
    } finally {
      setLoadingOlder(false)
    }
  }

  function onThreadScroll() {
    if (threadRef.current && threadRef.current.scrollTop < 24 && page < totalPages && !loadingOlder) void loadOlder()
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = composer.trim()
    if (!text || sending) return
    const temporaryId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const optimistic: VaultRecord = {
      id: temporaryId,
      text,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hashtags: [],
      links: [],
      source: 'web',
    }
    setRecords((current) => [...current, optimistic])
    setComposer('')
    setSending(true)
    setStatus('')
    scrollToBottom()
    try {
      const result = await api.createMessage(text)
      setRecords((current) => current.map((record) => record.id === temporaryId ? result.record : record))
      scrollToBottom()
    } catch (error) {
      setRecords((current) => current.filter((record) => record.id !== temporaryId))
      setComposer((current) => current || text)
      setStatus(error instanceof Error ? error.message : 'Message could not be saved.')
      scrollToBottom()
    } finally {
      setSending(false)
      composerRef.current?.focus()
    }
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file) return
    const extension = file.name.toLowerCase().split('.').pop()
    if (extension !== 'json' && extension !== 'jsonl') {
      setStatus('Choose a .json or .jsonl file.')
      return
    }
    setImporting(true)
    try {
      const result = await api.importFile(file)
      const refreshed = await api.messages(1, 100)
      setRecords([...refreshed.records].reverse())
      setPage(refreshed.page)
      setTotalPages(refreshed.total_pages)
      setSettingsOpen(false)
      setStatus(`Import complete · ${result.added} new, ${result.updated} updated.`)
      scrollToBottom()
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Import failed.')
    } finally {
      setImporting(false)
    }
  }

  return <main className="vault-screen">
    <header className="chat-header">
      <h1>Personal Vault</h1>
      <button className="settings-trigger" type="button" onClick={() => setSettingsOpen(true)}>Settings</button>
    </header>

    <section className="chat-thread" ref={threadRef} onScroll={onThreadScroll} aria-label="Saved messages">
      {loading ? <div className="thread-state">Loading messages…</div> : null}
      {!loading && records.length === 0 ? <div className="thread-state empty-thread">Your saved messages will appear here.</div> : null}
      {loadingOlder ? <div className="older-state">Loading older messages…</div> : null}
      {records.map((record, index) => {
        const previous = records[index - 1]
        const showDate = !previous || dayKey(previous.created_at) !== dayKey(record.created_at)
        return <div className="message-group" key={record.id}>
          {showDate ? <div className="date-divider"><span>{dayLabel(record.created_at)}</span></div> : null}
          <article className={`message-bubble ${record.id.startsWith('pending-') ? 'message-pending' : ''}`}>
            <p>{record.text}</p>
            <div className="message-meta"><time dateTime={record.created_at}>{timeLabel(record.created_at)}</time><span aria-label={record.id.startsWith('pending-') ? 'Sending' : 'Saved'}>{record.id.startsWith('pending-') ? '·' : '✓'}</span></div>
          </article>
        </div>
      })}
    </section>

    {status ? <div className="status-line" role="status">{status}</div> : null}
    <form className="composer" onSubmit={sendMessage}>
      <textarea
        ref={composerRef}
        rows={1}
        value={composer}
        onChange={(event) => setComposer(event.target.value)}
        onKeyDown={handleComposerKey}
        placeholder="Type your note…"
        aria-label="Message"
        disabled={sending}
      />
      <button className="send-button" type="submit" disabled={!composer.trim() || sending}>{sending ? 'Saving' : 'Send'}</button>
    </form>

    <input ref={importInputRef} className="visually-hidden" type="file" accept=".json,.jsonl,application/json,application/x-ndjson" onChange={handleImport} />

    {settingsOpen ? <div className="settings-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false) }}>
      <section className="settings-sheet" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div className="settings-heading"><h2 id="settings-title">Settings</h2><button className="close-settings" type="button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button></div>
        <div className="settings-scale-row">
          <div className="scale-copy"><label htmlFor="text-scale">Text Scaling</label><output htmlFor="text-scale">{scale}%</output></div>
          <input id="text-scale" className="scale-slider" type="range" min={MIN_SCALE} max={MAX_SCALE} step="5" value={scale} onChange={(event) => onScaleChange(Number(event.target.value))} />
        </div>
        <button className="settings-action" type="button" onClick={downloadExport}>Export</button>
        <button className="settings-action" type="button" onClick={() => importInputRef.current?.click()} disabled={importing}>{importing ? 'Importing…' : 'Import'}</button>
      </section>
    </div> : null}
  </main>
}

export default App
