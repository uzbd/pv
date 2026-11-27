import type { MessageResult, VaultRecord } from '../types'

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
    if (response.status === 401 && !path.startsWith('/api/auth/login') && !path.startsWith('/api/auth/setup')) {
      window.location.assign('/login')
    }
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
  messages: (page = 1, perPage = 100) => {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
    return request<MessageResult>(`/api/messages?${params.toString()}`)
  },
  createMessage: (text: string) => request<{ ok: boolean; record: VaultRecord }>('/api/messages', {
    method: 'POST',
    body: JSON.stringify({ text }),
  }),
  importFile: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ ok: boolean; source: string; added: number; updated: number; skipped: number; ignored: number; storage?: string }>('/api/settings/import', {
      method: 'POST',
      body,
    })
  },
}

export function downloadExport() {
  window.location.assign('/api/settings/export.jsonl')
}
