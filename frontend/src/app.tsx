import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive, ArrowDownToLine, ArrowUpFromLine, ArrowUpRight, Bookmark, Check, ChevronDown,
  ChevronLeft, ChevronRight, ChevronsUpDown, CircleHelp, Cloud, Database,
  FileJson, FileSpreadsheet, FileText, Filter, FolderOpen, HardDrive, Hash,
  Home, Inbox, LayoutDashboard, ListFilter, LockKeyhole, LogOut, Menu, Moon, MoreHorizontal,
  PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Search, Settings2, ShieldCheck, Sparkles,
  Sun, Tag, Trash2, Upload, X, Zap, MessageCircle, Send, Pencil, Image as ImageIcon, File as FileIcon, Link2, Smile, MoreVertical, Paperclip,
} from 'lucide-react'
import { api, downloadExport, loadSession, request, setCsrfToken } from './lib/api'
import { excerpt, formatDate, formatRelative, greeting } from './lib/utils'
import { Badge, Button, Card, EmptyState, Input, Modal } from './components/ui'
import type { DashboardData, MessageResult, SettingsData, VaultRecord } from './types'

const navItems = [
  { id: 'overview', label: 'Dashboard', icon: LayoutDashboard, path: '/app/dashboard' },
  { id: 'chat', label: 'Saved Messages', icon: MessageCircle, path: '/app/chat' },
  { id: 'library', label: 'All notes', icon: Inbox, path: '/app/library' },
  { id: 'trash', label: 'Trash', icon: Trash2, path: '/app/trash' },
] as const

type Page = 'overview' | 'chat' | 'library' | 'trash' | 'settings'
type SettingsTab = 'storage' | 'import' | 'export' | 'backup' | 'security' | 'preferences'

function readScale(key: string, fallback: number, minimum: number, maximum: number): number {
  const raw = Number(localStorage.getItem(key))
  if (!Number.isFinite(raw) || raw < minimum || raw > maximum) return fallback
  return raw
}

function routePage(path: string): Page {
  if (path.startsWith('/app/dashboard')) return 'overview'
  if (path.startsWith('/app/chat')) return 'chat'
  if (path.startsWith('/app/trash')) return 'trash'
  if (path.startsWith('/app/library')) return 'library'
  if (path.startsWith('/app/settings')) return 'settings'
  return 'chat'
}

function routeSettingsTab(): SettingsTab {
  const tab = new URLSearchParams(window.location.search).get('tab')
  const allowed: SettingsTab[] = ['storage', 'import', 'export', 'backup', 'security', 'preferences']
  return allowed.includes(tab as SettingsTab) ? tab as SettingsTab : 'storage'
}

function App() {
  const [session, setSession] = useState<{ authenticated: boolean; setup_required: boolean; ready: boolean }>({ authenticated: false, setup_required: false, ready: false })
  const [page, setPage] = useState<Page>(routePage(window.location.pathname))
  const [settingsTab, setSettingsTab] = useState<SettingsTab>(routeSettingsTab())
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [globalSearch, setGlobalSearch] = useState('')
  const [theme, setTheme] = useState(() => localStorage.getItem('pv-theme') === 'light' ? 'light' : 'dark')
  const [chatScale, setChatScale] = useState(() => readScale('pv-chat-scale', 1.2, 0.9, 1.6))
  const [editor, setEditor] = useState<{ open: boolean; record: VaultRecord | null }>({ open: false, record: null })
  const [toast, setToast] = useState<{ message: string; tone: 'success' | 'error' | 'info' } | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    loadSession().then((value) => {
      setSession({ authenticated: value.authenticated, setup_required: value.setup_required, ready: true })
      if (value.authenticated && window.location.pathname === '/login') window.history.replaceState({}, '', '/app/chat')
      if (!value.authenticated && !window.location.pathname.startsWith('/login')) window.location.assign('/login')
    }).catch(() => setSession({ authenticated: false, setup_required: false, ready: true }))
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.density = localStorage.getItem('pv-density') || 'comfortable'
    document.documentElement.style.setProperty('--chat-scale', String(readScale('pv-chat-scale', 1.2, 0.9, 1.6)))
    document.documentElement.style.setProperty('--dashboard-scale', String(readScale('pv-dashboard-scale', 1, 0.85, 1.3)))
  }, [])

  useEffect(() => {
    const onTheme = (event: Event) => setTheme((event as CustomEvent<string>).detail || 'dark')
    const onChatScale = (event: Event) => setChatScale(Number((event as CustomEvent<number>).detail) || 1.2)
    window.addEventListener('vault-theme-change', onTheme)
    window.addEventListener('vault-chat-scale-change', onChatScale)
    return () => { window.removeEventListener('vault-theme-change', onTheme); window.removeEventListener('vault-chat-scale-change', onChatScale) }
  }, [])

  useEffect(() => {
    const handlePop = () => {
      setPage(routePage(window.location.pathname))
      setSettingsTab(routeSettingsTab())
    }
    window.addEventListener('popstate', handlePop)
    return () => window.removeEventListener('popstate', handlePop)
  }, [])

  useEffect(() => {
    const handleKeys = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      if ((event.key === '/' || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) && !typing) {
        event.preventDefault();
        const searchField = document.getElementById('vault-chat-search') || document.getElementById('global-search')
        searchField?.focus()
      }
      if (event.key === 'Escape') setEditor({ open: false, record: null })
    }
    window.addEventListener('keydown', handleKeys)
    return () => window.removeEventListener('keydown', handleKeys)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = (message: string, tone: 'success' | 'error' | 'info' = 'success') => setToast({ message, tone })
  const navigate = (path: string) => {
    window.history.pushState({}, '', path)
    setPage(routePage(path))
    setSettingsTab(routeSettingsTab())
    setSidebarOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const logout = async () => {
    try {
      await request('/api/auth/logout', { method: 'POST' })
    } finally {
      setSession({ authenticated: false, setup_required: false, ready: true })
      window.location.assign('/login')
    }
  }

  const saveRecord = async (text: string, record: VaultRecord | null) => {
    if (record) await api.editMessage(record.id, text)
    else await api.createMessage(text)
    await queryClient.invalidateQueries()
    setEditor({ open: false, record: null })
  }

  if (!session.ready) return <div className="boot-screen"><div className="brand-mark"><Bookmark size={21} /></div><div className="boot-loader" /><span>Opening your private workspace…</span></div>
  if (!session.authenticated || window.location.pathname === '/login') {
    return <LoginScreen setupRequired={session.setup_required} onSuccess={() => { setSession({ authenticated: true, setup_required: false, ready: true }); window.location.assign('/app/chat') }} />
  }

  const settingsRoute = (tab: SettingsTab) => `/app/settings?tab=${tab}`
  const navigateSettings = (tab: SettingsTab) => { setSettingsTab(tab); navigate(settingsRoute(tab)) }

  return <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''} ${page === 'chat' ? 'chat-mode' : ''}`}>
    {sidebarOpen ? <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} /> : null}
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="sidebar-top">
        <div className="brand-lockup"><div className="brand-mark"><Bookmark size={20} strokeWidth={2.4} /></div><div className="brand-text"><strong>Personal Vault</strong><span>PRIVATE WORKSPACE</span></div></div>
        <button className="sidebar-collapse icon-button" onClick={() => setSidebarCollapsed((value) => !value)} aria-label="Toggle sidebar">{sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}</button>
      </div>
      <div className="workspace-chip"><span className="workspace-avatar">P</span><span><strong>My workspace</strong><small>Personal · Private</small></span><ChevronsUpDown size={14} className="workspace-chevron" /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="main-nav" aria-label="Main navigation">
        {navItems.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? 'nav-active' : ''}`} onClick={() => navigate(item.path)} title={item.label}><item.icon size={18} /><span>{item.label}</span>{item.id === 'trash' ? null : null}</button>)}
      </nav>
      <div className="nav-label nav-label-spaced">QUICK ACCESS</div>
      <button className="nav-item" onClick={() => { navigate('/app/library'); window.setTimeout(() => window.dispatchEvent(new Event('vault-open-filters')), 0) }}><Hash size={17} /><span>Hashtags</span></button>
      <button className="nav-item" onClick={() => { navigate('/app/library'); setGlobalSearch('https://') }}><ArrowUpRight size={17} /><span>Links & references</span></button>
      <div className="sidebar-spacer" />
      <div className="sidebar-storage"><div className="storage-mini-icon"><Cloud size={16} /></div><div><strong>Vault storage</strong><small>Connected workspace</small></div></div>
      <button className={`nav-item ${page === 'settings' ? 'nav-active' : ''}`} onClick={() => navigate(settingsRoute('storage'))}><Settings2 size={18} /><span>Settings & tools</span></button>
      <div className="sidebar-user"><div className="user-avatar">PV</div><div className="user-copy"><strong>Private Vault</strong><span>Personal account</span></div><button className="icon-button user-logout" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={16} /></button></div>
    </aside>

    <div className="main-column">
      <header className={`topbar ${page === 'chat' ? 'topbar-chat' : ''}`}>
        <div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu size={19} /></button><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{page === 'overview' ? 'Overview' : page === 'chat' ? 'Saved Messages' : page === 'library' ? 'All notes' : page === 'trash' ? 'Trash' : 'Settings'}</strong></div></div>
        <div className="topbar-actions"><div className="global-search-wrap"><Search size={16} /><input id="global-search" value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { navigate('/app/library'); window.dispatchEvent(new CustomEvent('vault-search', { detail: globalSearch })) } }} placeholder="Search…" /><kbd>/</kbd></div><button className="icon-button theme-toggle" aria-label="Toggle theme" onClick={() => { const next = theme === 'dark' ? 'light' : 'dark'; setTheme(next); document.documentElement.dataset.theme = next; localStorage.setItem('pv-theme', next); window.dispatchEvent(new CustomEvent('vault-theme-change', { detail: next })) }}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button><Button size="sm" onClick={() => setEditor({ open: true, record: null })}><Plus size={16} /> New note</Button></div>
      </header>
      <main className={`page-content ${page === 'chat' ? 'page-content-chat' : ''}`}>
        {page === 'overview' ? <OverviewPage onNavigate={navigate} onCreate={() => setEditor({ open: true, record: null })} onEdit={(record) => setEditor({ open: true, record })} onNotify={notify} /> : null}
        {page === 'chat' ? <ChatPage onEdit={(record) => setEditor({ open: true, record })} onNotify={notify} onMenu={() => setSidebarOpen(true)} onOpenSettings={() => navigate(settingsRoute('preferences'))} onOpenImport={() => navigate(settingsRoute('import'))} theme={theme} onToggleTheme={() => { const next = theme === 'dark' ? 'light' : 'dark'; setTheme(next); document.documentElement.dataset.theme = next; localStorage.setItem('pv-theme', next); window.dispatchEvent(new CustomEvent('vault-theme-change', { detail: next })) }} chatScale={chatScale} onChatScaleChange={(value) => { setChatScale(value); localStorage.setItem('pv-chat-scale', String(value)); document.documentElement.style.setProperty('--chat-scale', String(value)) }} /> : null}
        {page === 'library' || page === 'trash' ? <LibraryPage key={page} trash={page === 'trash'} initialSearch={globalSearch} onEdit={(record) => setEditor({ open: true, record })} onNotify={notify} /> : null}
        {page === 'settings' ? <SettingsPage activeTab={settingsTab} onTabChange={navigateSettings} onNotify={notify} /> : null}
      </main>
      <footer className={`app-footer ${page === 'chat' ? 'app-footer-chat' : ''}`}><span>Personal Vault</span><span><ShieldCheck size={13} /> Private by design</span><span>v2.4.1</span></footer>
    </div>

    <NoteEditor open={editor.open} record={editor.record} onClose={() => setEditor({ open: false, record: null })} onSave={saveRecord} />
    {toast ? <div className={`toast toast-${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={16} /> : toast.tone === 'error' ? <X size={16} /> : <CircleHelp size={16} />}</span>{toast.message}<button className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss"><X size={14} /></button></div> : null}
  </div>
}

function LoginScreen({ setupRequired, onSuccess }: { setupRequired: boolean; onSuccess: () => void }) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [setupKey, setSetupKey] = useState('')
  const [csrf, setCsrf] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [needsSetup, setNeedsSetup] = useState(setupRequired)

  useEffect(() => {
    loadSession().then((value) => {
      setCsrf(value.csrf_token)
      setNeedsSetup(value.setup_required)
      if (value.authenticated) onSuccess()
    }).catch(() => setError('Could not connect to the Vault service. Check the deployment and refresh.'))
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true); setError('')
    try {
      if (needsSetup && password !== confirmPassword) throw new Error('The passwords do not match.')
      if (needsSetup && !setupKey) throw new Error('Enter the one-time setup key configured in your hosting environment.')
      const endpoint = needsSetup ? '/api/auth/setup' : '/api/auth/login'
      const body = needsSetup
        ? { password, confirm_password: confirmPassword, setup_key: setupKey }
        : { password, csrf_token: csrf }
      const result = await request<{ ok: boolean; csrf_token: string }>(endpoint, { method: 'POST', body: JSON.stringify(body) })
      setCsrfToken(result.csrf_token)
      onSuccess()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not complete authentication.') }
    finally { setLoading(false) }
  }

  return <div className="login-screen">
    <div className="login-art"><div className="login-orbit orbit-one" /><div className="login-orbit orbit-two" /><div className="login-glow" /><div className="login-art-content"><div className="login-brand"><div className="brand-mark brand-mark-light"><Bookmark size={22} /></div><span>Personal Vault</span></div><div className="login-headline"><span className="eyebrow eyebrow-light"><Sparkles size={13} /> YOUR PRIVATE KNOWLEDGE SPACE</span><h1>Everything you<br />save, <em>in one place.</em></h1><p>A calm, searchable home for your ideas, notes and saved messages. Yours to organise. Yours to keep.</p></div><div className="login-art-foot"><span><LockKeyhole size={14} /> Private workspace</span><span><Cloud size={14} /> Your storage, your control</span></div></div></div>
    <div className="login-panel"><div className="login-form-wrap"><div className="mobile-login-brand"><div className="brand-mark"><Bookmark size={20} /></div><strong>Personal Vault</strong></div><div className="login-icon">{needsSetup ? <ShieldCheck size={22} /> : <LockKeyhole size={22} />}</div><span className="eyebrow">{needsSetup ? 'ONE-TIME SETUP' : 'WELCOME BACK'}</span><h2>{needsSetup ? 'Create your private workspace' : 'Sign in to your vault'}</h2><p className="login-subtitle">{needsSetup ? 'Enter the one-time setup key from your hosting settings, then choose a strong workspace password.' : 'Enter your private workspace password to continue.'}</p><form className="login-form" onSubmit={submit}><label htmlFor="vault-password">{needsSetup ? 'Create workspace password' : 'Workspace password'}</label><Input id="vault-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={needsSetup ? 'At least 16 characters' : 'Enter your password'} autoComplete={needsSetup ? 'new-password' : 'current-password'} autoFocus required minLength={needsSetup ? 16 : 1} />{needsSetup ? <><label htmlFor="vault-setup-key">One-time setup key</label><Input id="vault-setup-key" type="password" value={setupKey} onChange={(event) => setSetupKey(event.target.value)} placeholder="One-time deployment setup key" autoComplete="off" required /><label htmlFor="vault-password-confirm">Confirm password</label><Input id="vault-password-confirm" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Enter it again" autoComplete="new-password" required minLength={16} /></> : null}<div className="login-help"><span><ShieldCheck size={13} /> {needsSetup ? 'One-time deployment ownership check' : 'Server-validated private session'}</span><span>Private access</span></div>{error ? <div className="inline-error">{error}</div> : null}<Button type="submit" size="lg" loading={loading} disabled={!password || (needsSetup && (!confirmPassword || !setupKey))} className="login-submit">{needsSetup ? 'Secure workspace' : 'Continue'} <ArrowUpRight size={16} /></Button></form><p className="login-privacy">Your GitHub token stays on the server and is never requested by this page. The setup key is checked once and is not stored with your password verifier. Remove VAULT_SETUP_KEY from hosting settings after setup.</p></div><div className="login-panel-footer"><span>PERSONAL VAULT</span><span>{needsSetup ? 'Protected first-run setup · v2.4.1' : 'Secure access · v2.4.1'}</span></div></div>
  </div>
}

function OverviewPage({ onNavigate, onCreate, onEdit, onNotify }: { onNavigate: (path: string) => void; onCreate: () => void; onEdit: (record: VaultRecord) => void; onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void }) {
  const query = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })
  const data = query.data
  if (query.isLoading) return <PageLoading label="Loading your workspace" />
  if (query.isError || !data) return <ErrorPanel message="Your vault could not be loaded. Check your storage connection and refresh." onRetry={() => query.refetch()} />

  const stats = data.stats
  const dateLabel = new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())
  return <>
    <div className="welcome-row"><div><div className="eyebrow welcome-date">{dateLabel.toUpperCase()}</div><h1>{greeting()} <span className="wave">✦</span></h1><p>Your space is ready. Pick up where you left off.</p></div><div className="welcome-actions"><Button variant="secondary" onClick={() => onNavigate('/app/settings?tab=import')}><Upload size={16} /> Import</Button><Button onClick={onCreate}><Plus size={16} /> Create note</Button></div></div>
    <div className="stats-grid">
      <StatCard icon={<Bookmark size={18} />} label="Total saved" value={stats.total} detail="Everything in your vault" tone="blue" />
      <StatCard icon={<FileText size={18} />} label="Active notes" value={stats.active} detail="Ready when you need them" tone="green" />
      <StatCard icon={<Archive size={18} />} label="In trash" value={stats.deleted} detail="Recoverable, not removed" tone="amber" />
      <StatCard icon={<Database size={18} />} label="Storage" value={stats.primary_storage} detail={`${stats.shards} data ${stats.shards === 1 ? 'file' : 'files'}`} tone="violet" textValue />
    </div>

    <div className="dashboard-grid">
      <Card className="recent-card"><div className="card-heading"><div><span className="eyebrow">YOUR LATEST ACTIVITY</span><h2>Recently saved</h2><p>Your newest notes and messages.</p></div><button className="text-link" onClick={() => onNavigate('/app/library')}>View library <ArrowUpRight size={15} /></button></div>
        {data.recent.length ? <div className="recent-list">{data.recent.slice(0, 7).map((record, index) => <article className="recent-row" key={record.id}><div className={`recent-icon recent-icon-${index % 4}`}><FileText size={17} /></div><button className="recent-copy" onClick={() => onEdit(record)}><strong>{excerpt(record.text, 65)}</strong><span>{(record.hashtags || []).slice(0, 3).map((tag) => `#${tag}`).join('  ')}{record.hashtags?.length ? ' · ' : ''}{formatRelative(record.created_at)}</span></button><button className="icon-button row-open" title="Edit note" onClick={() => onEdit(record)}><ArrowUpRight size={16} /></button></article>)}</div> : <EmptyState title="Your vault is ready" description="Save your first note or import your Telegram Saved Messages archive." action={<Button onClick={onCreate}><Plus size={15} /> Create first note</Button>} />}
      </Card>
      <div className="dashboard-side">
        <Card className="storage-card"><div className="card-heading"><div><span className="eyebrow">CONNECTED STORAGE</span><h2>{stats.drive_pending > 0 ? 'Sync pending' : 'Storage'}</h2></div><span className={`status-indicator ${stats.drive_pending > 0 ? 'status-pending' : ''}`}><i /> {stats.drive_pending > 0 ? 'Pending' : stats.github_enabled || stats.drive_enabled ? 'Healthy' : 'Not configured'}</span></div><div className="storage-connection"><div className="provider-icon github-provider"><Database size={19} /></div><div className="provider-copy"><strong>GitHub</strong><span>{stats.github_enabled ? 'Primary storage connected' : 'Not configured'}</span></div><Badge tone={stats.github_enabled ? 'success' : 'neutral'}>{stats.github_enabled ? 'Connected' : 'Off'}</Badge></div><div className="storage-connection"><div className="provider-icon drive-provider"><HardDrive size={18} /></div><div className="provider-copy"><strong>Google Drive</strong><span>{stats.drive_enabled ? (stats.github_enabled ? 'Backup mirror' : 'Primary storage') : 'Not configured'}</span></div><Badge tone={stats.drive_enabled ? 'success' : 'neutral'}>{stats.drive_enabled ? 'Connected' : 'Off'}</Badge></div>{stats.drive_pending > 0 ? <div className="pending-note"><RefreshCw size={14} /> {stats.drive_pending} backup file(s) waiting to sync</div> : null}<button className="card-bottom-link" onClick={() => onNavigate('/app/settings?tab=storage')}>Manage storage <ArrowUpRight size={14} /></button></Card>
        <Card className="tags-card"><div className="card-heading"><div><span className="eyebrow">FIND YOUR WAY BACK</span><h2>Popular tags</h2></div><Hash size={17} className="muted-icon" /></div>{data.top_tags.length ? <div className="tag-cloud">{data.top_tags.map((item) => <button className="tag-pill" key={item.tag} onClick={() => { onNavigate('/app/library'); window.setTimeout(() => window.dispatchEvent(new CustomEvent('vault-tag', { detail: item.tag })), 0) }}><span>#{item.tag}</span><small>{item.count}</small></button>)}</div> : <p className="empty-inline">Your hashtags will appear here as you save notes.</p>}</Card>
      </div>
    </div>
    <div className="productivity-strip"><div className="productivity-icon"><Zap size={18} /></div><div><strong>Make your vault work for you</strong><span>Import your Telegram archive, search across everything, and keep a second copy in Google Drive.</span></div><button onClick={() => onNavigate('/app/settings?tab=import')}>Explore tools <ArrowUpRight size={15} /></button></div>
  </>
}

function StatCard({ icon, label, value, detail, tone, textValue = false }: { icon: ReactNode; label: string; value: number | string; detail: string; tone: string; textValue?: boolean }) {
  return <Card className="stat-card"><div className={`stat-icon stat-${tone}`}>{icon}</div><span className="stat-label">{label}</span><strong className={`stat-value ${textValue ? 'stat-text-value' : ''}`}>{typeof value === 'number' ? value.toLocaleString() : value}</strong><span className="stat-detail">{detail}</span></Card>
}

function ChatPage({ onEdit, onNotify, onMenu, onOpenSettings, onOpenImport, theme, onToggleTheme, chatScale, onChatScaleChange }: {
  onEdit: (record: VaultRecord) => void
  onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void
  onMenu: () => void
  onOpenSettings: () => void
  onOpenImport: () => void
  theme: string
  onToggleTheme: () => void
  chatScale: number
  onChatScaleChange: (value: number) => void
}) {
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState('')
  const [category, setCategory] = useState<'chat' | 'media' | 'files' | 'links'>('chat')
  const [menuOpen, setMenuOpen] = useState(false)
  const [sizeOpen, setSizeOpen] = useState(false)
  const [emojiOpen, setEmojiOpen] = useState(false)
  const threadRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const shouldScrollBottom = useRef(true)
  const queryClient = useQueryClient()

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 220)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    const field = composerRef.current
    if (!field) return
    field.style.height = 'auto'
    field.style.height = `${Math.min(field.scrollHeight, 160)}px`
  }, [draft])

  useEffect(() => { shouldScrollBottom.current = true }, [search, category])

  const feed = useInfiniteQuery({
    queryKey: ['chat-messages', search, category],
    initialPageParam: 1,
    enabled: category === 'chat' || category === 'links',
    queryFn: ({ pageParam }) => api.messages(new URLSearchParams({
      page: String(pageParam), per_page: '50', include_deleted: 'false',
      ...(search ? { q: search } : {}), ...(category === 'links' ? { kind: 'links' } : {}),
    })),
    getNextPageParam: (lastPage) => lastPage.page < lastPage.total_pages ? lastPage.page + 1 : undefined,
  })

  const sendMutation = useMutation({
    mutationFn: api.createMessage,
    onSuccess: async () => {
      setDraft('')
      shouldScrollBottom.current = true
      await queryClient.invalidateQueries({ queryKey: ['chat-messages'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => onNotify(error.message, 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteMessage,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['chat-messages'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => onNotify(error.message, 'error'),
  })

  const records = (feed.data?.pages.flatMap((page) => page.records) || []).slice().reverse()
  useEffect(() => {
    if (!threadRef.current || !shouldScrollBottom.current || feed.isFetchingNextPage) return
    const node = threadRef.current
    window.requestAnimationFrame(() => { node.scrollTop = node.scrollHeight; shouldScrollBottom.current = false })
  }, [records.length, feed.data?.pages.length, feed.dataUpdatedAt, category])

  const total = feed.data?.pages[0]?.total ?? 0
  const send = () => {
    if (draft.trim() && !sendMutation.isPending) {
      shouldScrollBottom.current = true
      sendMutation.mutate(draft.trim())
      setEmojiOpen(false)
    }
  }
  const submit = (event: FormEvent) => { event.preventDefault(); send() }
  const dayLabel = (iso: string) => {
    const date = new Date(iso)
    const today = new Date()
    const yesterday = new Date(); yesterday.setDate(today.getDate() - 1)
    const key = (value: Date) => `${value.getFullYear()}-${value.getMonth()}-${value.getDate()}`
    const shortDate = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date)
    if (key(date) === key(today)) return `Today, ${shortDate}`
    if (key(date) === key(yesterday)) return `Yesterday, ${shortDate}`
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined }).format(date)
  }
  const timeLabel = (iso: string) => new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(iso))
  let previousDay = ''
  const appendEmoji = (emoji: string) => {
    setDraft((value) => `${value}${emoji}`)
    setEmojiOpen(false)
    composerRef.current?.focus()
  }

  return <section className={`vault-chat-screen ${theme === 'light' ? 'vault-light-theme' : 'vault-dark-theme'}`} aria-label="Saved Messages">
    <header className="vault-chat-header">
      <button className="vault-header-icon" onClick={onMenu} aria-label="Open menu"><Menu /></button>
      <div className="vault-brand-mark"><LockKeyhole /></div>
      <strong className="vault-brand-title">Personal Vault</strong>
      <div className="vault-header-actions">
        <button className="vault-header-icon" onClick={() => document.getElementById('vault-chat-search')?.focus()} aria-label="Search"><Search /></button>
        <div className="vault-menu-wrap">
          <button className="vault-header-icon" onClick={() => setMenuOpen((value) => !value)} aria-label="More options"><MoreVertical /></button>
          {menuOpen ? <><button className="vault-menu-dismiss" onClick={() => setMenuOpen(false)} aria-label="Close menu" /><div className="vault-overflow-menu">
            <button onClick={() => { setMenuOpen(false); onOpenSettings() }}><Settings2 /> Settings</button>
            <button onClick={() => { setMenuOpen(false); onOpenImport() }}><Upload /> Import</button>
            <button onClick={() => { setMenuOpen(false); onToggleTheme() }}>{theme === 'dark' ? <Sun /> : <Moon />} Theme</button>
          </div></> : null}
        </div>
      </div>
    </header>

    <nav className="vault-category-tabs" aria-label="Saved content categories">
      <button className={category === 'chat' ? 'active' : ''} onClick={() => setCategory('chat')}><MessageCircle /> Chat</button>
      <button className="vault-tab-unavailable" disabled aria-disabled="true" title="Media storage is not available"><ImageIcon /> Media</button>
      <button className="vault-tab-unavailable" disabled aria-disabled="true" title="File storage is not available"><FileIcon /> Files</button>
      <button className={category === 'links' ? 'active' : ''} onClick={() => setCategory('links')}><Link2 /> Links</button>
    </nav>

    <div className="vault-search-bar">
      <Search />
      <input id="vault-chat-search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search…" aria-label="Search your saved messages" />
      {searchInput ? <button onClick={() => setSearchInput('')} aria-label="Clear search"><X /></button> : null}
    </div>

    <div className="vault-chat-thread" ref={threadRef}>
      {(category === 'chat' || category === 'links') ? <>
        {feed.hasNextPage ? <div className="vault-older"><button onClick={async () => {
          const node = threadRef.current
          const previousHeight = node?.scrollHeight ?? 0
          await feed.fetchNextPage()
          window.requestAnimationFrame(() => { if (node) node.scrollTop += node.scrollHeight - previousHeight })
        }} disabled={feed.isFetchingNextPage}>{feed.isFetchingNextPage ? <span className="mini-spinner" /> : 'Load older messages'}</button></div> : null}
        {feed.isLoading ? <PageLoading label="Loading" compact /> : feed.isError ? <ErrorPanel message="Messages could not be loaded." onRetry={() => feed.refetch()} /> : records.length ? records.map((record) => {
          const key = new Date(record.created_at).toDateString()
          const showDate = key !== previousDay
          previousDay = key
          return <div className="telegram-message-group" key={record.id}>
            {showDate ? <div className="telegram-date-separator"><span>{dayLabel(record.created_at)}</span></div> : null}
            <article className="telegram-message-row">
              <div className="telegram-message-bubble">
                <button className="telegram-message-content" onClick={() => onEdit(record)} aria-label="Edit saved message">
                  <span className="telegram-message-text">{record.text}</span>
                  {record.hashtags?.length ? <span className="telegram-message-tags">{record.hashtags.slice(0, 5).map((tag) => <span key={tag}>#{tag}</span>)}</span> : null}
                  <span className="telegram-message-meta">{record.edited_at ? 'edited · ' : ''}{timeLabel(record.created_at)} <Check /></span>
                </button>
                <div className="telegram-message-actions">
                  <button onClick={() => onEdit(record)} title="Edit" aria-label="Edit message"><Pencil /></button>
                  <button onClick={() => { if (window.confirm('Move this message to Trash?')) deleteMutation.mutate(record.id) }} title="Delete" aria-label="Delete message" disabled={deleteMutation.isPending}><Trash2 /></button>
                </div>
              </div>
            </article>
          </div>
        }) : <div className="vault-empty-state"><Bookmark /><strong>{search ? 'No results' : category === 'links' ? 'No links' : 'No saved messages'}</strong></div>}
      </> : null}
    </div>

    {category === 'chat' ? <form className="vault-composer" onSubmit={submit}>
      <button type="button" className="vault-composer-icon" onClick={onOpenImport} aria-label="Import Telegram messages" title="Import"><Paperclip /></button>
      <div className="vault-composer-input-wrap">
        <textarea ref={composerRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send() }
        }} placeholder="Message…" rows={1} maxLength={100000} aria-label="Type a message" />
        <div className="vault-emoji-wrap">
          <button type="button" className="vault-emoji-button" onClick={() => setEmojiOpen((value) => !value)} aria-label="Add emoji"><Smile /></button>
          {emojiOpen ? <div className="vault-emoji-picker">{['😀','😁','😂','😊','😍','🥰','😎','🤔','👍','🙏','❤️','🔥','✅','🎉','💡','📌'].map((emoji) => <button type="button" key={emoji} onClick={() => appendEmoji(emoji)}>{emoji}</button>)}</div> : null}
        </div>
      </div>
      <button type="submit" className="vault-send-button" disabled={!draft.trim() || sendMutation.isPending} aria-label="Save message" title="Save">{sendMutation.isPending ? <div className="mini-spinner" /> : <Send />}</button>
    </form> : null}

    <footer className="vault-bottom-dock">
      <div className="vault-dock-item vault-size-item">
        <button onClick={() => { setSizeOpen((value) => !value); setEmojiOpen(false) }} aria-expanded={sizeOpen}><span className="vault-aa">Aᴀ</span><span>Text Size</span><ChevronDown /></button>
        {sizeOpen ? <div className="vault-size-popover"><button onClick={() => onChatScaleChange(Math.max(0.9, Number((chatScale - 0.05).toFixed(2))))} aria-label="Decrease text size">A−</button><input type="range" min="0.9" max="1.6" step="0.05" value={chatScale} onChange={(event) => onChatScaleChange(Number(event.target.value))} aria-label="Chat text size" /><button onClick={() => onChatScaleChange(Math.min(1.6, Number((chatScale + 0.05).toFixed(2))))} aria-label="Increase text size">A+</button><output>{Math.round(chatScale * 100)}%</output></div> : null}
      </div>
      <div className="vault-dock-item"><button onClick={onToggleTheme}><span className="vault-dock-symbol">{theme === 'dark' ? <Sun /> : <Moon />}</span><span>Theme</span><ChevronDown /></button></div>
      <div className="vault-dock-item"><button onClick={onOpenSettings}><span className="vault-dock-symbol"><Settings2 /></span><span>Settings</span></button></div>
    </footer>
  </section>
}
function LibraryPage({ trash, initialSearch, onEdit, onNotify }: { trash: boolean; initialSearch: string; onEdit: (record: VaultRecord) => void; onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void }) {
  const [q, setQ] = useState(initialSearch)
  const [tag, setTag] = useState('')
  const [domain, setDomain] = useState('')
  const [date, setDate] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()

  useEffect(() => { const onSearch = (event: Event) => { setQ((event as CustomEvent<string>).detail || ''); setPage(1) }; const onTag = (event: Event) => { setTag((event as CustomEvent<string>).detail || ''); setPage(1) }; const onOpenFilters = () => setFiltersOpen(true); window.addEventListener('vault-search', onSearch); window.addEventListener('vault-tag', onTag); window.addEventListener('vault-open-filters', onOpenFilters); return () => { window.removeEventListener('vault-search', onSearch); window.removeEventListener('vault-tag', onTag); window.removeEventListener('vault-open-filters', onOpenFilters) } }, [])

  const params = useMemo(() => { const value = new URLSearchParams({ page: String(page), per_page: '24', include_deleted: String(trash) }); if (q.trim()) value.set('q', q.trim()); if (trash) value.set('only_deleted', 'true'); if (tag.trim()) value.set('tag', tag.trim()); if (domain.trim()) value.set('domain', domain.trim()); if (date) value.set('date', date); if (fromDate) value.set('from_date', fromDate); if (toDate) value.set('to_date', toDate); return value }, [q, tag, domain, date, fromDate, toDate, page, trash])
  const result = useQuery({ queryKey: ['messages', params.toString()], queryFn: () => api.messages(params) })

  const deleteMutation = useMutation({ mutationFn: api.deleteMessage, onSuccess: () => { queryClient.invalidateQueries(); onNotify('Moved to Trash. You can restore it anytime.') }, onError: (error) => onNotify(error.message, 'error') })
  const restoreMutation = useMutation({ mutationFn: api.restoreMessage, onSuccess: () => { queryClient.invalidateQueries(); onNotify('Note restored to your library.') }, onError: (error) => onNotify(error.message, 'error') })

  const data = result.data
  return <>
    <div className="page-title-row"><div><div className="eyebrow">{trash ? 'RECOVER OR REVIEW' : 'YOUR PERSONAL ARCHIVE'}</div><h1>{trash ? 'Trash' : 'All notes'}</h1><p>{trash ? 'Deleted items stay here until you restore them.' : 'Search, filter and manage everything you have saved.'}</p></div><div className="title-actions"><Button variant="secondary" onClick={() => { window.location.assign('/app/settings?tab=import') }}><Upload size={16} /> Import</Button></div></div>
    <Card className="library-card"><div className="library-toolbar"><div className="library-search"><Search size={17} /><input value={q} onChange={(event) => { setQ(event.target.value); setPage(1) }} placeholder="Search…" /><kbd>Enter</kbd>{q ? <button className="clear-search" onClick={() => setQ('')} aria-label="Clear search"><X size={14} /></button> : null}</div><Button variant={filtersOpen ? 'primary' : 'secondary'} onClick={() => setFiltersOpen((value) => !value)}><Filter size={16} /> Filters {(tag || domain || date || fromDate || toDate) ? <span className="filter-count">{[tag, domain, date, fromDate, toDate].filter(Boolean).length}</span> : null}</Button></div>
      {filtersOpen ? <div className="filter-panel"><label>Hashtag<Input value={tag} onChange={(event) => { setTag(event.target.value); setPage(1) }} placeholder="e.g. research" /></label><label>Link or domain<Input value={domain} onChange={(event) => { setDomain(event.target.value); setPage(1) }} placeholder="example.com" /></label><label>Exact date<input className="field" type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(1) }} /></label><label>From<input className="field" type="date" value={fromDate} onChange={(event) => { setFromDate(event.target.value); setPage(1) }} /></label><label>To<input className="field" type="date" value={toDate} onChange={(event) => { setToDate(event.target.value); setPage(1) }} /></label><Button variant="ghost" size="sm" onClick={() => { setTag(''); setDomain(''); setDate(''); setFromDate(''); setToDate(''); setPage(1) }}>Clear filters</Button></div> : null}
      <div className="library-summary"><span>{data ? `${data.total.toLocaleString()} ${trash ? 'items in Trash' : 'notes'} found` : 'Loading notes…'}</span><span className="sort-label"><ListFilter size={14} /> Most recent first</span></div>
      {result.isLoading ? <PageLoading label="Loading notes" compact /> : result.isError ? <ErrorPanel message="Could not load notes." onRetry={() => result.refetch()} /> : data && data.records.length ? <div className="note-list">{data.records.map((record) => <NoteRow key={record.id} record={record} onEdit={onEdit} onDelete={() => deleteMutation.mutate(record.id)} onRestore={() => restoreMutation.mutate(record.id)} trash={trash} busy={deleteMutation.isPending || restoreMutation.isPending} />)}</div> : <EmptyState title={trash ? 'Trash is empty' : 'Nothing here yet'} description={trash ? 'Notes you delete will appear here. You can restore them whenever you need.' : 'Start by creating a note or importing your Telegram Saved Messages archive.'} />}
      {data && data.total_pages > 1 ? <div className="pagination"><span>Page {data.page} of {data.total_pages}</span><div><Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={15} /> Previous</Button><Button variant="secondary" size="sm" disabled={page >= data.total_pages} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight size={15} /></Button></div></div> : null}
    </Card>
  </>
}

function NoteRow({ record, onEdit, onDelete, onRestore, trash, busy }: { record: VaultRecord; onEdit: (record: VaultRecord) => void; onDelete: () => void; onRestore: () => void; trash: boolean; busy: boolean }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return <article className="note-row"><div className="note-type-icon"><FileText size={18} /></div><button className="note-main" onClick={() => onEdit(record)}><strong>{excerpt(record.text, 105)}</strong><span className="note-meta">{formatDate(record.created_at)}{record.edited_at ? ' · Edited' : ''}{record.source === 'telegram' ? ' · Telegram import' : ''}</span>{record.hashtags?.length ? <span className="note-tags">{record.hashtags.slice(0, 4).map((tag) => <span key={tag}>#{tag}</span>)}</span> : null}</button><div className="note-row-actions">{trash ? <Badge tone="warning">In trash</Badge> : record.links?.length ? <Badge tone="brand">{record.links.length} {record.links.length === 1 ? 'link' : 'links'}</Badge> : <Badge>Note</Badge>}<div className="relative-menu"><button className="icon-button" onClick={() => setMenuOpen((value) => !value)} aria-label="More actions"><MoreHorizontal size={18} /></button>{menuOpen ? <><button className="menu-dismiss" onClick={() => setMenuOpen(false)} aria-label="Close menu" /><div className="action-menu">{trash ? <button onClick={() => { setMenuOpen(false); onRestore() }} disabled={busy}><RefreshCw size={14} /> Restore</button> : <><button onClick={() => { setMenuOpen(false); onEdit(record) }}><FileText size={14} /> Edit note</button><button className="menu-danger" onClick={() => { setMenuOpen(false); if (window.confirm('Move this note to Trash?')) onDelete() }} disabled={busy}><Trash2 size={14} /> Move to Trash</button></>}</div></> : null}</div></div></article>
}

function SettingsPage({ activeTab, onTabChange, onNotify }: { activeTab: SettingsTab; onTabChange: (tab: SettingsTab) => void; onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void }) {
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const queryClient = useQueryClient()
  const backupMutation = useMutation({ mutationFn: api.backup, onSuccess: (result) => { queryClient.invalidateQueries({ queryKey: ['settings'] }); onNotify(`Backup finished · ${result.success} synced, ${result.failed} pending`, result.failed ? 'info' : 'success') }, onError: (error) => onNotify(error.message, 'error') })
  const importMutation = useMutation({ mutationFn: api.importFile, onSuccess: (result) => { queryClient.invalidateQueries(); onNotify(`Import complete · ${result.added} new, ${result.updated} edited, ${result.skipped} duplicates skipped.`, 'success') }, onError: (error) => onNotify(error.message, 'error') })
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [appearance, setAppearance] = useState(() => localStorage.getItem('pv-theme') === 'light' ? 'light' : 'dark')
  const [density, setDensity] = useState(() => localStorage.getItem('pv-density') || 'comfortable')
  const [dashboardScale, setDashboardScale] = useState(() => readScale('pv-dashboard-scale', 1, 0.85, 1.3))
  const [chatScale, setChatScale] = useState(() => readScale('pv-chat-scale', 1.2, 0.9, 1.6))
  const data = settings.data

  const tabs: { id: SettingsTab; label: string; icon: typeof Database; description: string }[] = [
    { id: 'storage', label: 'Storage', icon: Database, description: 'Connected providers and data path' },
    { id: 'import', label: 'Import', icon: ArrowDownToLine, description: 'Bring your saved messages in' },
    { id: 'export', label: 'Export', icon: ArrowUpFromLine, description: 'Download a complete copy' },
    { id: 'backup', label: 'Backup', icon: Cloud, description: 'Sync your secondary copy' },
    { id: 'security', label: 'Security', icon: ShieldCheck, description: 'Login and session protection' },
    { id: 'preferences', label: 'Preferences', icon: Settings2, description: 'Appearance and workspace density' },
  ]

  const chooseFile = (file?: File) => {
    if (!file) return
    const extension = file.name.toLowerCase().split('.').pop()
    if (!['json', 'jsonl'].includes(extension || '')) { onNotify('Choose a .json or .jsonl file.', 'error'); return }
    setSelectedFile(file)
  }

  const runImport = () => { if (selectedFile) importMutation.mutate(selectedFile) }
  const setTheme = (value: string) => { setAppearance(value); document.documentElement.dataset.theme = value; localStorage.setItem('pv-theme', value); window.dispatchEvent(new CustomEvent('vault-theme-change', { detail: value })) }
  const setViewDensity = (value: string) => { setDensity(value); document.documentElement.dataset.density = value; localStorage.setItem('pv-density', value) }
  const updateDashboardScale = (value: number) => { setDashboardScale(value); localStorage.setItem('pv-dashboard-scale', String(value)); document.documentElement.style.setProperty('--dashboard-scale', String(value)) }
  const updateChatScale = (value: number) => { setChatScale(value); localStorage.setItem('pv-chat-scale', String(value)); document.documentElement.style.setProperty('--chat-scale', String(value)); window.dispatchEvent(new CustomEvent('vault-chat-scale-change', { detail: value })) }

  return <>
    <div className="page-title-row settings-title"><div><div className="eyebrow">MAKE IT YOURS</div><h1>Settings & tools</h1><p>Everything you need to configure, manage and protect your vault.</p></div></div>
    <div className="settings-layout"><aside className="settings-sidebar"><div className="settings-sidebar-label">PREFERENCES & TOOLS</div>{tabs.map((tab) => <button key={tab.id} className={`settings-tab ${activeTab === tab.id ? 'settings-tab-active' : ''}`} onClick={() => onTabChange(tab.id)}><tab.icon size={17} /><span><strong>{tab.label}</strong><small>{tab.description}</small></span>{activeTab === tab.id ? <ChevronRight size={15} /> : null}</button>)}</aside>
      <div className="settings-main">{settings.isLoading ? <PageLoading label="Loading settings" /> : settings.isError || !data ? <ErrorPanel message="Settings are unavailable." onRetry={() => settings.refetch()} /> : <>
        {activeTab === 'storage' ? <StorageSettings data={data} /> : null}
        {activeTab === 'import' ? <div className="settings-panel"><SectionHeading eyebrow="BRING YOUR DATA" title="Import your archive" description="Import Telegram Desktop Saved Messages or a previous Personal Vault export." /><div className="steps-grid"><div><span>01</span><strong>Export from Telegram</strong><p>Open Saved Messages → Export Chat History.</p></div><div><span>02</span><strong>Choose JSON</strong><p>Select Machine-readable JSON in Telegram Desktop.</p></div><div><span>03</span><strong>Upload here</strong><p>Choose your export file below to merge it into the Vault.</p></div></div><div className={`drop-zone ${dragging ? 'drop-zone-active' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]) }}><div className="drop-icon"><Upload size={22} /></div><strong>Drop your export file here</strong><span>or choose a file from your device</span><label className="file-picker-button">Browse files<input type="file" accept=".json,.jsonl,application/json,application/x-ndjson" onChange={(event) => { chooseFile(event.currentTarget.files?.[0]); event.currentTarget.value = '' }} /></label><small>JSON or JSONL · Up to {data.max_upload_mb} MB</small>{selectedFile ? <div className="selected-file"><FileJson size={17} /><span><strong>{selectedFile.name}</strong><small>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</small></span><button className="icon-button" onClick={() => setSelectedFile(null)} aria-label="Remove file"><X size={15} /></button></div> : null}</div><div className="merge-info"><div className="merge-check"><Check size={16} /></div><div><strong>Merge, never replace</strong><p>New messages are added, newer edits update their matching message, duplicates are skipped, and all unrelated existing records remain untouched.</p></div></div><div className="settings-actions"><Button onClick={runImport} disabled={!selectedFile || importMutation.isPending} loading={importMutation.isPending}><ArrowDownToLine size={16} /> Validate & import</Button></div></div> : null}
        {activeTab === 'export' ? <div className="settings-panel"><SectionHeading eyebrow="TAKE YOUR DATA WITH YOU" title="Export your entire vault" description="Download every active and trashed record, including its timestamps and metadata." /><div className="export-grid"><ExportCard icon={<FileJson size={21} />} title="JSON archive" desc="Readable, structured full export" extension="JSON" onClick={() => downloadExport('json')} /><ExportCard icon={<FileText size={21} />} title="JSON Lines" desc="Best for restore and automation" extension="JSONL" onClick={() => downloadExport('jsonl')} /><ExportCard icon={<FileSpreadsheet size={21} />} title="Spreadsheet" desc="Open in Excel or Google Sheets" extension="CSV" onClick={() => downloadExport('csv')} /></div><div className="tip-panel"><ShieldCheck size={18} /><div><strong>Keep an independent copy</strong><p>Download a JSON or JSONL export before making large imports or moving between storage providers.</p></div></div></div> : null}
        {activeTab === 'backup' ? <div className="settings-panel"><SectionHeading eyebrow="SECONDARY COPY" title="Backup & synchronisation" description="Keep your GitHub primary vault mirrored to Google Drive." /><div className="backup-summary"><div className="backup-icon"><Cloud size={24} /></div><div><strong>{data.github_enabled && data.drive_enabled ? 'Google Drive mirror' : data.drive_enabled ? 'Google Drive primary storage' : 'Drive backup is not configured'}</strong><p>{data.github_enabled && data.drive_enabled ? 'Every successful primary write is mirrored to Drive. Pending files can be retried below.' : data.drive_enabled ? 'Drive is your primary storage, so a secondary mirror is not available.' : 'Add Google Drive OAuth credentials to your hosting environment to enable a second copy.'}</p></div><Badge tone={data.drive_enabled ? 'success' : 'neutral'}>{data.drive_enabled ? 'Configured' : 'Not configured'}</Badge></div><div className="backup-stats"><div><span>Files pending</span><strong>{data.drive_pending}</strong></div><div><span>Primary storage</span><strong>{data.primary_storage}</strong></div><div><span>Data shards</span><strong>{data.stats.shards}</strong></div></div><div className="settings-actions"><Button onClick={() => backupMutation.mutate()} disabled={!data.drive_enabled || !data.github_enabled || backupMutation.isPending} loading={backupMutation.isPending}><RefreshCw size={16} /> Retry Drive backup</Button><span className="muted-hint">Available when both GitHub and Drive are connected.</span></div></div> : null}
        {activeTab === 'security' ? <div className="settings-panel"><SectionHeading eyebrow="ACCOUNT & PROTECTION" title="Security & access" description="Manage your private workspace password and review the protections enabled for this vault." /><div className="security-grid"><SecurityItem title="Password-protected access" desc="Your password verifier is stored in your private GitHub repository. The password itself is never stored." /><SecurityItem title="Signed HttpOnly session" desc="Every private request checks a server-side active-session allowlist; signed cookies are HttpOnly and Secure on HTTPS." /><SecurityItem title="CSRF protection" desc="Every state-changing request requires a session-bound token." /><SecurityItem title="Login throttling" desc="Five failed attempts per 15-minute window are rate-limited per IP." /><SecurityItem title="Secrets stay server-side" desc="GitHub credentials are never sent to the browser." /><SecurityItem title="HTTPS cookie policy" desc={data.cookie_secure ? 'Secure cookies are enabled for HTTPS.' : 'Secure cookie flag is disabled for local development.'} /></div><PasswordSettings onNotify={onNotify} /><div className="env-note"><LockKeyhole size={18} /><div><strong>Storage credentials stay with your host</strong><p>To change your GitHub PAT or repository, update GITHUB_TOKEN, GITHUB_OWNER or GITHUB_REPO in your hosting provider. The website password can be changed here without redeploying.</p></div></div><div className="security-meta"><div><span>Session lifetime</span><strong>{Math.round(data.session_max_age / 86400)} days</strong></div><div><span>Password managed by</span><strong>{data.password_managed_by}</strong></div><div><span>Secure cookies</span><strong>{data.cookie_secure ? 'Enabled' : 'Disabled'}</strong></div></div></div> : null}
        {activeTab === 'preferences' ? <div className="settings-panel"><SectionHeading eyebrow="MAKE IT COMFORTABLE" title="Workspace preferences" description="Adjust the visual environment to fit the way you work." /><div className="preference-block"><div><strong>Appearance</strong><p>Choose the theme used across your workspace.</p></div><div className="choice-row"><button className={`choice-card ${appearance === 'light' ? 'choice-active' : ''}`} onClick={() => setTheme('light')}><Sun size={19} /><span>Light</span>{appearance === 'light' ? <Check size={15} /> : null}</button><button className={`choice-card ${appearance === 'dark' ? 'choice-active' : ''}`} onClick={() => setTheme('dark')}><Moon size={19} /><span>Dark</span>{appearance === 'dark' ? <Check size={15} /> : null}</button></div></div><div className="preference-block"><div><strong>Interface density</strong><p>Choose more breathing room or fit more content on screen.</p></div><div className="choice-row"><button className={`choice-card ${density === 'comfortable' ? 'choice-active' : ''}`} onClick={() => setViewDensity('comfortable')}><PanelLeftOpen size={18} /><span>Comfortable</span>{density === 'comfortable' ? <Check size={15} /> : null}</button><button className={`choice-card ${density === 'compact' ? 'choice-active' : ''}`} onClick={() => setViewDensity('compact')}><ListFilter size={18} /><span>Compact</span>{density === 'compact' ? <Check size={15} /> : null}</button></div></div><div className="scale-setting"><div><strong>Dashboard size</strong><p>Adjust the dashboard layout and text size independently.</p></div><div className="scale-control"><input aria-label="Dashboard size" type="range" min="0.85" max="1.30" step="0.05" value={dashboardScale} onChange={(event) => updateDashboardScale(Number(event.target.value))} /><output>{Math.round(dashboardScale * 100)}%</output><button className="scale-reset" onClick={() => updateDashboardScale(1)}>Reset</button></div></div><div className="scale-setting"><div><strong>Chat UI & text size</strong><p>Change message bubbles, composer and chat controls without changing the dashboard.</p></div><div className="scale-control"><input aria-label="Chat UI and text size" type="range" min="0.9" max="1.6" step="0.05" value={chatScale} onChange={(event) => updateChatScale(Number(event.target.value))} /><output>{Math.round(chatScale * 100)}%</output><button className="scale-reset" onClick={() => updateChatScale(1.2)}>Reset</button></div></div><div className="tip-panel"><Sparkles size={18} /><div><strong>Preferences are saved on this device</strong><p>Appearance and density settings are stored locally in this browser and do not change your Vault data.</p></div></div></div> : null}
      </>}</div>
    </div>
  </>
}

function StorageSettings({ data }: { data: SettingsData }) {
  return <div className="settings-panel"><SectionHeading eyebrow="PERSISTENT DATA" title="Storage configuration" description="Your notes live in your own private GitHub repository. Optional Google Drive mirroring can be configured by an advanced deployment." /><div className="provider-grid"><ProviderCard icon={<Database size={23} />} name="GitHub" subtitle="Primary storage" connected={data.github_enabled} /><ProviderCard icon={<HardDrive size={22} />} name="Google Drive" subtitle={data.github_enabled ? 'Backup mirror' : 'Primary storage'} connected={data.drive_enabled} /></div><div className="storage-detail-grid"><div><span>Active mode</span><strong>{data.storage_mode}</strong></div><div><span>Primary provider</span><strong>{data.primary_storage}</strong></div><div><span>Data directory</span><strong className="mono-value">{data.data_dir}</strong></div><div><span>Shard capacity</span><strong>{data.max_records_per_shard.toLocaleString()} records / file</strong></div><div><span>Pending Drive sync</span><strong>{data.drive_pending}</strong></div><div><span>Import file limit</span><strong>{data.max_upload_mb} MB</strong></div></div><div className="env-note"><LockKeyhole size={18} /><div><strong>Credentials are managed by your host</strong><p>GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO are managed as hosting secrets. Add or change them in Render, Railway, Koyeb or your Docker host, then redeploy. Google Drive is optional and is not required for first deployment.</p></div></div><div className="tip-panel"><Check size={18} /><div><strong>Compatible with your Telegram Bot Vault</strong><p>The website reuses the same JSONL shard format and storage directory. Stop the old bot before running this website against the same Vault to avoid concurrent writes.</p></div></div></div>
}

function ProviderCard({ icon, name, subtitle, connected }: { icon: ReactNode; name: string; subtitle: string; connected: boolean }) {
  return <div className="provider-card"><div className={`provider-large-icon ${name === 'GitHub' ? 'provider-github' : 'provider-drive'}`}>{icon}</div><div className="provider-large-copy"><strong>{name}</strong><span>{subtitle}</span></div><Badge tone={connected ? 'success' : 'neutral'}>{connected ? 'Connected' : 'Not configured'}</Badge></div>
}

function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="section-heading"><div className="eyebrow">{eyebrow}</div><h2>{title}</h2><p>{description}</p></div>
}

function ExportCard({ icon, title, desc, extension, onClick }: { icon: ReactNode; title: string; desc: string; extension: string; onClick: () => void }) {
  return <button className="export-card" onClick={onClick}><div className="export-card-icon">{icon}</div><div><strong>{title}</strong><span>{desc}</span><small>{extension} FILE</small></div><ArrowDownToLine size={17} className="export-download" /></button>
}

function SecurityItem({ title, desc }: { title: string; desc: string }) {
  return <div className="security-item"><div className="security-check"><Check size={14} /></div><div><strong>{title}</strong><span>{desc}</span></div></div>
}

function PasswordSettings({ onNotify }: { onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (next.length < 16) { setError('Use at least 16 characters for your new password.'); return }
    if (next !== confirm) { setError('The new passwords do not match.'); return }
    setSaving(true)
    try {
      const result = await api.changePassword(current, next, confirm)
      setCsrfToken(result.csrf_token)
      setCurrent(''); setNext(''); setConfirm('')
      onNotify('Your workspace password has been updated.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not change your password.') }
    finally { setSaving(false) }
  }

  return <div className="password-settings-card"><div className="password-settings-heading"><div className="login-icon"><LockKeyhole size={18} /></div><div><strong>Change workspace password</strong><p>Update the password used to sign in. The new password verifier is saved in your private GitHub repository.</p></div></div><form className="password-settings-form" onSubmit={submit}><div className="password-fields"><label>Current password<Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" required /></label><label>New password<Input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" minLength={16} required /></label><label>Confirm new password<Input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" minLength={16} required /></label></div>{error ? <div className="inline-error">{error}</div> : null}<div className="settings-actions"><Button type="submit" loading={saving} disabled={!current || !next || !confirm}><ShieldCheck size={16} /> Update password</Button><span className="muted-hint">At least 16 characters</span></div></form></div>
}

function NoteEditor({ open, record, onClose, onSave }: { open: boolean; record: VaultRecord | null; onClose: () => void; onSave: (text: string, record: VaultRecord | null) => Promise<void> }) {
  const [text, setText] = useState(record?.text || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setText(record?.text || ''); setError('') }, [record, open])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) { setError('A note cannot be empty.'); return }
    setSaving(true); setError('')
    try { await onSave(text.trim(), record) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save note.') } finally { setSaving(false) }
  }
  return <Modal open={open} title={record ? 'Edit note' : 'Create a note'} description={record ? 'Your changes will be saved to your connected vault.' : 'Capture an idea, link or anything worth keeping.'} onClose={onClose} wide><form className="editor-form" onSubmit={submit}><textarea className="note-editor-input" value={text} onChange={(event) => setText(event.target.value)} placeholder="Start writing…" autoFocus rows={9} maxLength={100000} /><div className="editor-footer"><span>{text.length.toLocaleString()} characters · Hashtags and links are detected automatically</span><div>{error ? <span className="inline-error">{error}</span> : null}<Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={saving} disabled={!text.trim()}>Save note <Check size={15} /></Button></div></div></form></Modal>
}

function PageLoading({ label, compact = false }: { label: string; compact?: boolean }) { return <div className={`page-loading ${compact ? 'page-loading-compact' : ''}`}><div className="boot-loader" /><span>{label}…</span></div> }
function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) { return <div className="error-panel"><div className="error-icon"><X size={18} /></div><strong>Something didn’t load</strong><p>{message}</p><Button variant="secondary" size="sm" onClick={onRetry}><RefreshCw size={14} /> Try again</Button></div> }

export default App
