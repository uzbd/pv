export type VaultRecord = {
  id: string
  text: string
  created_at: string
  updated_at?: string
  edited_at?: string | null
  hashtags?: string[]
  links?: string[]
  is_deleted?: boolean
  deleted_at?: string | null
  source?: string
}

export type VaultStats = {
  total: number
  active: number
  deleted: number
  shards: number
  github_enabled: boolean
  drive_enabled: boolean
  primary_storage: string
  drive_pending: number
}

export type MessageResult = {
  records: VaultRecord[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export type DashboardData = {
  stats: VaultStats
  recent: VaultRecord[]
  top_tags: { tag: string; count: number }[]
}

export type SettingsData = {
  app_title: string
  storage_mode: string
  github_enabled: boolean
  drive_enabled: boolean
  primary_storage: string
  data_dir: string
  drive_pending: number
  max_records_per_shard: number
  max_upload_mb: number
  session_max_age: number
  cookie_secure: boolean
  app_env: string
  stats: VaultStats
  password_managed_by: string
}
