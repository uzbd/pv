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

export type MessageResult = {
  records: VaultRecord[]
  total: number
  page: number
  per_page: number
  total_pages: number
}
