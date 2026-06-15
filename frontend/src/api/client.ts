// Thin API client. Adds the X-UID header, parses the unified error envelope,
// and exposes typed endpoint helpers. No secrets ever live here.

export interface ApiError {
  error: string
  message: string
  detail?: string
  retryable?: boolean
}

export class ApiException extends Error {
  code: string
  retryable: boolean
  constructor(envelope: ApiError) {
    super(envelope.message)
    this.code = envelope.error
    this.retryable = !!envelope.retryable
  }
}

export interface Bot {
  id: string
  owner_uid: string
  name: string
  description: string
  persona: string
  player_term: string
  self_term: string
  tone: string
  enabled_skills: string[]
  enabled_mcp: string[]
  model: string
  // --- Facebook Messenger channel ---
  // Read back from the server:
  messenger_enabled?: boolean
  messenger_page_id?: string
  messenger_verify_token?: string
  messenger_page_token_set?: boolean
  messenger_app_secret_set?: boolean
  // Write-only (sent on save, never returned): leave blank to keep the stored secret.
  messenger_page_token?: string
  messenger_app_secret?: string
  created_at: string | null
  document_count?: number
  documents?: DocumentItem[]
}

export interface MessengerValidateResult {
  ok: boolean
  page_name?: string
  page_id?: string
  error?: string
}

export interface MessengerSimulateResult {
  reply: string
  category: string
  delay: number
}

export interface DocumentItem {
  id: string
  bot_id: string
  filename: string
  mime: string
  char_count: number
  status: string
  note: string
  created_at: string | null
}

export interface Sample {
  id: string
  filename: string
  title: string
  char_count: number
}

export interface SampleContent {
  id: string
  filename: string
  content: string
}

export interface ChatResult {
  reply: string
  category: string
  delay: number
  bot_id: string
}

const UID_KEY = 'cs-agent-studio-uid'

export function getUid(): string {
  let uid = localStorage.getItem(UID_KEY)
  if (!uid) {
    uid = 'u-' + Math.random().toString(36).slice(2, 10)
    localStorage.setItem(UID_KEY, uid)
  }
  return uid
}

export function setUid(uid: string): void {
  localStorage.setItem(UID_KEY, uid.trim() || getUid())
}

// Hard timeout so a hung request can never leave a button stuck in its loading/
// disabled state — on abort we reject like a network error and callers reset state.
const REQUEST_TIMEOUT_MS = 60_000

export async function fetchWithTimeout(input: string, init: RequestInit = {}): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(input, { ...init, signal: ctrl.signal })
  } catch {
    throw new ApiException({
      error: 'network',
      message: 'Máy chủ phản hồi quá lâu hoặc mất kết nối. Vui lòng thử lại.',
      retryable: true,
    })
  } finally {
    clearTimeout(timer)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetchWithTimeout(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-UID': getUid() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return parse<T>(resp)
}

async function parse<T>(resp: Response): Promise<T> {
  const text = await resp.text()
  const data = text ? JSON.parse(text) : {}
  if (!resp.ok) {
    throw new ApiException(
      (data as ApiError).message
        ? (data as ApiError)
        : { error: 'http_' + resp.status, message: 'Có lỗi xảy ra.', retryable: resp.status >= 500 },
    )
  }
  return data as T
}

export const api = {
  listBots: () => request<{ bots: Bot[] }>('GET', '/api/bots').then((r) => r.bots),
  createBot: (data: Partial<Bot>) =>
    request<{ bot: Bot }>('POST', '/api/bots', data).then((r) => r.bot),
  getBot: (id: string) => request<{ bot: Bot }>('GET', `/api/bots/${id}`).then((r) => r.bot),
  updateBot: (id: string, data: Partial<Bot>) =>
    request<{ bot: Bot }>('PATCH', `/api/bots/${id}`, data).then((r) => r.bot),
  deleteBot: (id: string) => request<{ deleted: boolean }>('DELETE', `/api/bots/${id}`),
  listDocuments: (botId: string) =>
    request<{ documents: DocumentItem[] }>('GET', `/api/bots/${botId}/documents`).then(
      (r) => r.documents,
    ),
  deleteDocument: (botId: string, docId: string) =>
    request<{ deleted: boolean }>('DELETE', `/api/bots/${botId}/documents/${docId}`),
  getDocument: (botId: string, docId: string) =>
    request<{ document: DocumentItem & { extracted_text: string } }>(
      'GET',
      `/api/bots/${botId}/documents/${docId}`,
    ).then((r) => r.document),
  listSamples: () => request<{ samples: Sample[] }>('GET', '/api/samples').then((r) => r.samples),
  getSample: (id: string) =>
    request<{ sample: SampleContent }>('GET', `/api/samples/${id}`).then((r) => r.sample),
  addSampleDocuments: (botId: string, sampleIds: string[]) =>
    request<{ documents: DocumentItem[] }>('POST', `/api/bots/${botId}/documents/samples`, {
      sample_ids: sampleIds,
    }).then((r) => r.documents),
  // Raw original-file URLs for preview (uid via query — img/iframe can't send headers).
  documentRawUrl: (botId: string, docId: string) =>
    `/api/bots/${botId}/documents/${docId}/raw?uid=${encodeURIComponent(getUid())}`,
  sampleRawUrl: (id: string) => `/api/samples/${id}/raw?uid=${encodeURIComponent(getUid())}`,
  chat: (botId: string, message: string) =>
    request<ChatResult>('POST', '/api/chat', { bot_id: botId, message }),
  // Dry-run the Messenger inbound pipeline (no Facebook call) — verify the bot replies.
  simulateMessenger: (botId: string, message: string) =>
    request<MessengerSimulateResult>('POST', `/api/bots/${botId}/messenger/simulate`, { message }),
  // Check a Page id + token against the Graph API so the operator can fix wrong keys.
  validateMessenger: (
    botId: string,
    creds: { page_id?: string; page_token?: string },
  ) => request<MessengerValidateResult>('POST', `/api/bots/${botId}/messenger/validate`, creds),
  // Auto-subscribe the Page to message events (skips the manual Meta dashboard step).
  subscribeMessenger: (botId: string, creds: { page_token?: string } = {}) =>
    request<MessengerValidateResult>('POST', `/api/bots/${botId}/messenger/subscribe`, creds),

  async uploadDocuments(botId: string, files: File[]): Promise<DocumentItem[]> {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const resp = await fetchWithTimeout(`/api/bots/${botId}/documents`, {
      method: 'POST',
      headers: { 'X-UID': getUid() },
      body: form,
    })
    const data = await parse<{ documents: DocumentItem[] }>(resp)
    return data.documents
  },
}
