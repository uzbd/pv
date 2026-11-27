import type { DashboardData, MessageResult, SettingsData, VaultRecord } from '../types'

let csrfToken = ''

export function setCsrfToken(value: string) {
  csrfToken = value
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    const message = payload?.detail || `Request failed (${response.status})`
    if (response.status === 401 && !path.startsWith('/api/auth/login')) window.location.assign('/login')
    throw new Error(message)
  }
  return payload as T
}

export async function loadSession() {
  const response = await request<{ authenticated: boolean; setup_required: boolean; csrf_token: string }>('/api/auth/session')
  setCsrfToken(response.csrf_token)
  return response
}

export const api = {
  dashboard: () => request<DashboardData>('/api/dashboard'),
  settings: () => request<SettingsData>('/api/settings'),
  messages: (params: URLSearchParams) => request<MessageResult>(`/api/messages?${params.toString()}`),
  createMessage: (text: string) => request<{ ok: boolean; record: VaultRecord }>('/api/messages', { method: 'POST', body: JSON.stringify({ text }) }),
  editMessage: (id: string, text: string) => request<{ ok: boolean; record: VaultRecord }>(`/api/messages/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ text }) }),
  deleteMessage: (id: string) => request<{ ok: boolean }>(`/api/messages/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  restoreMessage: (id: string) => request<{ ok: boolean }>(`/api/messages/${encodeURIComponent(id)}/restore`, { method: 'POST' }),
  backup: () => request<{ ok: boolean; message: string; success: number; failed: number }>('/api/settings/backup', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string, confirm_password: string) => request<{ ok: boolean; csrf_token: string }>('/api/auth/password', { method: 'POST', body: JSON.stringify({ current_password, new_password, confirm_password }) }),
  importFile: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ ok: boolean; source: string; added: number; updated: number; skipped: number; ignored: number; storage?: string }>('/api/settings/import', { method: 'POST', body })
  },
}

export function downloadExport(format: 'json' | 'jsonl' | 'csv') {
  window.location.assign(`/api/settings/export.${format}`)
}
